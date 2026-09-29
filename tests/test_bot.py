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
    monkeypatch.setattr(bot, "status", {"username": None, "user_id": None, "last_poll": None})
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


class RecordingApi:
    """Запоминает отправленные сообщения; может отклонить первое, как МАКС отклонил бы кнопку."""

    def __init__(self, reject_first: bool = False):
        self.sent = []
        self.reject_first = reject_first

    async def send_message(self, chat_id, text, buttons=None, *, user_id=None):
        if self.reject_first and not self.sent:
            self.sent.append(None)
            request = httpx.Request("POST", "https://platform-api.max.ru/messages")
            raise httpx.HTTPStatusError("400", request=request, response=httpx.Response(400, request=request))
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {}


def evening_update(chat_id: int, text: str = "/вечер") -> dict:
    return {"update_type": "message_created",
            "message": {"sender": {"user_id": 7}, "recipient": {"chat_id": chat_id}, "body": {"text": text}}}


def test_evening_command_sends_open_app_button(monkeypatch):
    monkeypatch.setattr(bot, "status", {"username": "test_bot", "user_id": 99, "last_poll": None})
    api = RecordingApi()
    asyncio.run(bot.handle_update(api, evening_update(-123)))
    [button] = api.sent[0]["buttons"][0]
    assert button == {"type": "open_app", "text": "Подобрать вечер", "web_app": "test_bot",
                      "contact_id": 99, "payload": "chat-123"}


def test_evening_falls_back_to_deeplink(monkeypatch):
    monkeypatch.setattr(bot, "status", {"username": "test_bot", "user_id": 99, "last_poll": None})
    api = RecordingApi(reject_first=True)
    asyncio.run(bot.handle_update(api, evening_update(-123)))
    [button] = api.sent[1]["buttons"][0]
    assert button["type"] == "link"
    assert button["url"] == "https://max.ru/test_bot?startapp=chat-123"


def test_start_sends_help_with_open_app_button(monkeypatch):
    monkeypatch.setattr(bot, "status", {"username": "test_bot", "user_id": 99, "last_poll": None})
    api = RecordingApi()
    asyncio.run(bot.handle_update(api, evening_update(5, "/start")))
    [message] = api.sent
    assert message["text"] == bot.HELP_TEXT
    assert message["buttons"][0][0]["type"] == "open_app"  # не нужно набирать /вечер


def test_bot_started_sends_open_app_button(monkeypatch):
    # Эксперт нажал «Начать» в личке с ботом — сразу видит кнопку мини-приложения
    monkeypatch.setattr(bot, "status", {"username": "test_bot", "user_id": 99, "last_poll": None})
    api = RecordingApi()
    asyncio.run(bot.handle_update(api, {"update_type": "bot_started", "chat_id": 5}))
    [button] = api.sent[0]["buttons"][0]
    assert button["type"] == "open_app"
    assert button["payload"] == "chat5"
