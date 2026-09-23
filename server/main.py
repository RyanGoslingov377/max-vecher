"""Точка входа: веб-сервер (API + мини-приложение) и бот в одном процессе.

Запуск: python -m uvicorn server.main:app --port 3000
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .bot import run_bot
from .max_api import MaxApi

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # иначе каждые 30 сек строка про long polling

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    api = MaxApi(config.BOT_TOKEN)
    bot_task = asyncio.create_task(run_bot(api))
    yield
    bot_task.cancel()
    await api.close()


app = FastAPI(lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"ok": True}


# Всё остальное — файлы мини-приложения из папки web/
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
