"""Точка входа: веб-сервер (API + мини-приложение) и бот в одном процессе.

Запуск: python -m uvicorn server.main:app --port 3000
"""
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db
from .auth import launch_data
from .bot import run_bot, send_invite
from .events import find_event, load_events
from .max_api import MaxApi
from .picker import DAYS, KAZAN_TZ, MOODS, WILD, pick, resolve_day

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # иначе каждые 30 сек строка про long polling

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.BOT_ENABLED and not config.BOT_TOKEN:
        raise SystemExit("Нет MAX_BOT_TOKEN: впиши токен в .env или поставь BOT_ENABLED=0, чтобы запустить сервер без бота")
    if config.DEV_AUTH:
        logging.getLogger("auth").warning("DEV_AUTH=1: запросы без подписи МАКС пускаются. Только для локальной разработки!")
    db.init_db()
    load_events()  # проверяем data/events.json сразу, чтобы ошибка куратора всплыла при запуске
    # Отправлять сообщения можно и без long polling, поэтому клиент есть везде, где есть токен
    api = MaxApi(config.BOT_TOKEN) if config.BOT_TOKEN else None
    app.state.max_api = api
    bot_task = None
    if config.BOT_ENABLED:
        bot_task = asyncio.create_task(run_bot(api))
    else:
        logging.getLogger("bot").info("Бот выключен (BOT_ENABLED=0), работают только API и мини-приложение")
    yield
    if bot_task:
        bot_task.cancel()
    if api:
        await api.close()


app = FastAPI(lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/pick")
async def api_pick(mood: str, day: str = "today", budget: bool = False):
    """Три события под настроение. Пример: /api/pick?mood=charged&day=saturday&budget=1"""
    if mood not in MOODS and mood != WILD:
        raise HTTPException(400, f"Неизвестное настроение. Можно: {', '.join([*MOODS, WILD])}")
    if day not in DAYS:
        raise HTTPException(400, f"Неизвестный день. Можно: {', '.join(DAYS)}")
    now = datetime.now(KAZAN_TZ)
    target_day = resolve_day(day, now)
    results = pick(load_events(), mood, target_day, budget_on=budget, now=now)
    return {"mood": mood, "day": target_day.isoformat(), "budget": budget, "results": results}


@app.get("/api/me")
async def api_me(launch: dict = Depends(launch_data)):
    """Кто и из какого чата открыл мини-приложение. Нужен заголовок X-Max-Init-Data."""
    return {"user": launch.get("user"), "chat": launch.get("chat"), "start_param": launch.get("start_param")}


class InviteIn(BaseModel):
    event_id: str


@app.post("/api/invites")
async def api_create_invite(body: InviteIn, launch: dict = Depends(launch_data)):
    """Позвать друзей: бот присылает карточку события в чат, из которого открыто мини-приложение."""
    if find_event(body.event_id) is None:
        raise HTTPException(404, "Нет такого события")
    user = launch.get("user") or {}
    chat_id = (launch.get("chat") or {}).get("id")
    user_id = user.get("id")
    if not chat_id and not user_id:
        raise HTTPException(400, "Не понятно, куда отправить приглашение")

    invite_id = secrets.token_hex(4)
    db.create_invite(invite_id, chat_id or 0, body.event_id, user_id)  # chat_id 0 — личка с ботом
    if user_id:
        db.set_answer(invite_id, user_id, user.get("first_name") or "Кто-то", "going")  # кто позвал — идёт

    api = getattr(app.state, "max_api", None)
    if api is None:
        return {"invite_id": invite_id, "sent": False}  # локально без токена: карточку отправить нечем
    try:
        await send_invite(api, invite_id, chat_id=chat_id, user_id=None if chat_id else user_id)
    except httpx.HTTPError as error:
        logging.getLogger("bot").warning("Не удалось отправить приглашение %s: %s", invite_id, error)
        raise HTTPException(502, "Бот не смог написать в чат. Проверьте, что бот добавлен в чат администратором")
    return {"invite_id": invite_id, "sent": True}


@app.get("/api/invites/{invite_id}")
async def api_get_invite(invite_id: str, launch: dict = Depends(launch_data)):
    """Событие и ответы друзей — для живого счётчика в мини-приложении."""
    invite = db.get_invite(invite_id)
    if invite is None:
        raise HTTPException(404, "Нет такого приглашения")
    event = find_event(invite["event_id"]) if invite["event_id"] else None
    answers = [{"name": name, "answer": answer} for name, answer in db.get_answers(invite_id)]
    return {"invite_id": invite_id, "event": event, "answers": answers}


# Всё остальное — файлы мини-приложения из папки web/
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
