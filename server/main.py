"""Точка входа: веб-сервер (API + мини-приложение) и бот в одном процессе.

Запуск: python -m uvicorn server.main:app --port 3000
"""
import asyncio
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import config, db
from .auth import launch_data
from .bot import run_bot, send_invite, status as bot_status
from .events import find_event, load_events
from .followup import run_followups
from .max_api import MaxApi
from .picker import KAZAN_TZ, MOODS, WILD, pick, resolve_day
from .schemas import HealthOut, InviteCreated, InviteIn, InviteOut, MeOut, PickOut, StatsOut

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
    tasks = []
    if config.BOT_ENABLED:
        # «Сходили?» рассылает только тот, у кого запущен бот, — иначе вопросы задублируются
        tasks = [asyncio.create_task(run_bot(api)), asyncio.create_task(run_followups(api))]
    else:
        logging.getLogger("bot").info("Бот выключен (BOT_ENABLED=0), работают только API и мини-приложение")
    yield
    for task in tasks:
        task.cancel()
    if api:
        await api.close()


app = FastAPI(
    lifespan=lifespan,
    title="Вечер по настроению — API",
    version="1.0.0",
    description=(
        "API мини-приложения для МАКС: подбор событий под настроение, приглашения друзей в чат "
        "и метрика «сходили ÷ собирались». Рабочий адрес: https://max-vecher-gosuslugov233.amvera.io. "
        "Адреса /api/me и /api/invites требуют заголовок X-Max-Init-Data — подпись МАКС, "
        "которую мини-приложение получает при запуске (window.WebApp.initData)."
    ),
)

SIGNED = {401: {"description": "Нет подписи МАКС (X-Max-Init-Data) или она неверна"}}


@app.get("/api/health", response_model=HealthOut, tags=["служебное"])
async def health():
    """Жив ли сервер и бот. bot.ok = false — бот давно не получал событий от МАКС: смотрим логи."""
    last_poll = bot_status["last_poll"]
    seconds_since_poll = round(time.time() - last_poll) if last_poll else None
    bot = {
        "enabled": config.BOT_ENABLED,
        "username": bot_status["username"],
        "seconds_since_poll": seconds_since_poll,
        "ok": seconds_since_poll is not None and seconds_since_poll < 120,  # опрос идёт каждые ≤30 сек
    }
    return {"ok": True, "bot": bot}


@app.get("/api/pick", response_model=PickOut, response_model_exclude_none=True, tags=["подбор"],
         responses={400: {"description": "Неизвестное настроение или день"}})
async def api_pick(mood: str, day: str = "today", budget: bool = False):
    """Три события под настроение. Пример: /api/pick?mood=charged&day=2026-10-05&budget=1"""
    if mood not in MOODS and mood != WILD:
        raise HTTPException(400, f"Неизвестное настроение. Можно: {', '.join([*MOODS, WILD])}")
    now = datetime.now(KAZAN_TZ)
    try:
        target_day = resolve_day(day, now)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    results = pick(load_events(), mood, target_day, budget_on=budget, now=now)
    return {"mood": mood, "day": target_day.isoformat(), "budget": budget, "results": results}


@app.get("/api/me", response_model=MeOut, tags=["пользователь"], responses=SIGNED)
async def api_me(launch: dict = Depends(launch_data)):
    """Кто и из какого чата открыл мини-приложение. Нужен заголовок X-Max-Init-Data."""
    return {"user": launch.get("user"), "chat": launch.get("chat"), "start_param": launch.get("start_param")}


def invite_chat_id(launch: dict) -> int | None:
    """Куда слать приглашение: групповой чат из данных МАКС, иначе чат из payload кнопки /вечер."""
    chat = launch.get("chat") or {}
    if chat.get("id") and chat.get("type") != "DIALOG":
        return chat["id"]
    match = re.fullmatch(r"chat(-?\d+)", str(launch.get("start_param") or ""))
    return int(match.group(1)) if match else None  # None — пришлём в личку с ботом


@app.post("/api/invites", response_model=InviteCreated, tags=["приглашения"], responses={
    **SIGNED,
    404: {"description": "Нет такого события"},
    502: {"description": "Бот не смог написать в чат (не добавлен или не администратор)"},
})
async def api_create_invite(body: InviteIn, launch: dict = Depends(launch_data)):
    """Позвать друзей: бот присылает карточку события в чат, из которого открыто мини-приложение."""
    if find_event(body.event_id) is None:
        raise HTTPException(404, "Нет такого события")
    user = launch.get("user") or {}
    chat_id = invite_chat_id(launch)
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
    if launch.get("dev") and not chat_id:
        # Тестовый пользователь выдуман: писать ему в личку нельзя — это мог бы оказаться чужой человек
        return {"invite_id": invite_id, "sent": False}
    try:
        await send_invite(api, invite_id, chat_id=chat_id, user_id=None if chat_id else user_id)
    except httpx.HTTPError as error:
        logging.getLogger("bot").warning("Не удалось отправить приглашение %s: %s", invite_id, error)
        raise HTTPException(502, "Бот не смог написать в чат. Проверьте, что бот добавлен в чат администратором")
    return {"invite_id": invite_id, "sent": True}


@app.get("/api/invites/{invite_id}", response_model=InviteOut, response_model_exclude_none=True,
         tags=["приглашения"], responses={**SIGNED, 404: {"description": "Нет такого приглашения"}})
async def api_get_invite(invite_id: str, launch: dict = Depends(launch_data)):
    """Событие и ответы друзей — для живого счётчика в мини-приложении."""
    invite = db.get_invite(invite_id)
    if invite is None:
        raise HTTPException(404, "Нет такого приглашения")
    event = find_event(invite["event_id"]) if invite["event_id"] else None
    answers = [{"name": name, "answer": answer} for name, answer in db.get_answers(invite_id)]
    return {"invite_id": invite_id, "event": event, "answers": answers}


@app.get("/api/stats", response_model=StatsOut, tags=["метрика"])
async def api_stats():
    """Главная метрика: доля выбранных вечеров, которые состоялись (сходили ÷ собирались)."""
    going, went = db.stats()
    return {"going": going, "went": went, "rate": round(went / going, 2) if going else None}


# Всё остальное — файлы мини-приложения из папки web/. Этот mount должен быть последним
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
