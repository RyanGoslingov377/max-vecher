import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from server import bot, config
from server.main import app


class FlakyApi:
    """МАКС недоступен при первом обращении — как при перезапуске хостинга 24.09."""

    def __init__(self):
        self.me_calls = 0

    async def me(self):
        self.me_calls += 1
        if self.me_calls == 1:
            raise httpx.ConnectTimeout("МАКС не ответил")
        return {"username": "test_bot"}

    async def get_updates(self, marker=None, timeout=30):
        raise asyncio.CancelledError  # первый успешный шаг дошёл до опроса — выходим из цикла


@pytest.fixture(autouse=True)
def fresh_status(monkeypatch):
    monkeypatch.setattr(bot, "status", {"username": None, "last_poll": None})
    monkeypatch.setattr(bot, "RETRY_SECONDS", 0)


def test_bot_survives_network_error_at_start():
    api = FlakyApi()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bot.run_bot(api))
    assert api.me_calls == 2  # не умер после первой ошибки, а повторил
    assert bot.status["username"] == "test_bot"


def test_health_shows_dead_bot(monkeypatch):
    monkeypatch.setattr(config, "BOT_ENABLED", True)
    monkeypatch.setattr("server.main.bot_status", bot.status)
    body = TestClient(app).get("/api/health").json()
    assert body["ok"] is True
    assert body["bot"]["ok"] is False  # бот ни разу не получил события


def test_health_shows_live_bot(monkeypatch):
    monkeypatch.setattr("server.main.bot_status", {"username": "test_bot", "last_poll": time.time()})
    body = TestClient(app).get("/api/health").json()
    assert body["bot"]["ok"] is True
    assert body["bot"]["username"] == "test_bot"
