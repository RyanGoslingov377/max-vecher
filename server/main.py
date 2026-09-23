"""Точка входа: веб-сервер (API + мини-приложение) и бот в одном процессе.

Запуск: python -m uvicorn server.main:app --port 3000
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import config, db
from .bot import run_bot
from .events import load_events
from .max_api import MaxApi
from .picker import DAYS, KAZAN_TZ, MOODS, WILD, pick, resolve_day

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # иначе каждые 30 сек строка про long polling

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    load_events()  # проверяем data/events.json сразу, чтобы ошибка куратора всплыла при запуске
    api = MaxApi(config.BOT_TOKEN)
    bot_task = asyncio.create_task(run_bot(api))
    yield
    bot_task.cancel()
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


# Всё остальное — файлы мини-приложения из папки web/
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
