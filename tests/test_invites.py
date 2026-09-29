import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from server import bot, config, db, events
from server.auth import launch_data
from server.main import app

EVENTS = [
    {"id": "party", "title": "DJ-сет", "place": "Крыша", "starts_at": "2026-09-26T22:00:00+03:00",
     "price": 500, "tags": ["музыка"], "nrg": 2, "dep": 0, "growth": False, "why": "Громко и весело",
     "ticket_url": "https://example.com/tickets"},
    {"id": "walk", "title": "Прогулка", "place": "Центр", "anytime": True,
     "price": 0, "tags": ["природа"], "nrg": 0, "dep": 0, "growth": False, "why": "Тихо"},
]


class FakeApi:
    """Вместо настоящего Bot API: запоминает, что бот отправил бы."""

    def __init__(self, fail: bool = False):
        self.sent = []
        self.answers = []
        self.fail = fail

    async def send_message(self, chat_id, text, buttons=None, *, user_id=None):
        if self.fail:
            raise httpx.HTTPError("бот не в чате")
        self.sent.append({"chat_id": chat_id, "user_id": user_id, "text": text, "buttons": buttons})
        return {}

    async def answer_callback(self, callback_id, *, text=None, buttons=None, notification=None):
        self.answers.append({"text": text, "buttons": buttons, "notification": notification})
        return {}


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    monkeypatch.setattr(events, "load_events", lambda: EVENTS)
    monkeypatch.setattr(config, "DEV_AUTH", True)
    monkeypatch.setattr(config, "DEV_CHAT_ID", -555)
    fake = FakeApi()
    monkeypatch.setattr(app.state, "max_api", fake, raising=False)
    return fake


@pytest.fixture
def client(api):
    return TestClient(app)


def test_invite_goes_to_chat_with_event_card(client, api):
    response = client.post("/api/invites", json={"event_id": "party"})
    assert response.status_code == 200
    assert response.json()["sent"] is True

    [message] = api.sent
    assert message["chat_id"] == -555
    assert "DJ-сет" in message["text"]
    assert "сб 26.09, 22:00 · Крыша · 500 ₽" in message["text"]
    assert "Иду (1): Тест" in message["text"]  # кто позвал, уже идёт
    assert [b["text"] for b in message["buttons"][0]] == ["Иду", "Может", "Не могу"]
    assert message["buttons"][1][0]["url"] == "https://example.com/tickets"


def test_invite_without_chat_goes_to_private_dialog(client, api):
    # Настоящий пользователь МАКС, открыл приложение не из группы
    app.dependency_overrides[launch_data] = lambda: {"user": {"id": 5, "first_name": "Аня"}, "chat": None}
    try:
        client.post("/api/invites", json={"event_id": "walk"})
    finally:
        app.dependency_overrides.clear()
    [message] = api.sent
    assert message["chat_id"] is None
    assert message["user_id"] == 5
    assert "в любое время · Центр · бесплатно" in message["text"]


def test_dev_user_without_chat_gets_nothing_sent(client, api, monkeypatch):
    # Тестового пользователя с id 1 не существует — в личку ему не пишем
    monkeypatch.setattr(config, "DEV_CHAT_ID", None)
    body = client.post("/api/invites", json={"event_id": "walk"}).json()
    assert body["sent"] is False
    assert api.sent == []


def test_unknown_event_is_404(client):
    assert client.post("/api/invites", json={"event_id": "nope"}).status_code == 404


def test_invite_requires_signature(client, monkeypatch):
    monkeypatch.setattr(config, "DEV_AUTH", False)
    assert client.post("/api/invites", json={"event_id": "party"}).status_code == 401


def test_without_bot_token_invite_is_saved_but_not_sent(client, monkeypatch):
    monkeypatch.setattr(app.state, "max_api", None)
    body = client.post("/api/invites", json={"event_id": "party"}).json()
    assert body["sent"] is False
    assert db.get_invite(body["invite_id"]) is not None


def test_bot_error_is_502(client, monkeypatch):
    monkeypatch.setattr(app.state, "max_api", FakeApi(fail=True))
    assert client.post("/api/invites", json={"event_id": "party"}).status_code == 502


def test_get_invite_returns_event_and_answers(client):
    invite_id = client.post("/api/invites", json={"event_id": "party"}).json()["invite_id"]
    db.set_answer(invite_id, 7, "Петя", "maybe")

    body = client.get(f"/api/invites/{invite_id}").json()
    assert body["event"]["id"] == "party"
    assert body["answers"] == [{"name": "Тест", "answer": "going"}, {"name": "Петя", "answer": "maybe"}]


def test_get_unknown_invite_is_404(client):
    assert client.get("/api/invites/nope").status_code == 404


def test_card_text_after_votes(client):
    invite_id = client.post("/api/invites", json={"event_id": "party"}).json()["invite_id"]
    db.set_answer(invite_id, 7, "Петя", "no")
    text = bot.card_text(invite_id)
    assert "Иду (1): Тест" in text
    assert "Не могу (1): Петя" in text


def test_invite_chat_id_prefers_group_then_payload():
    from server.main import invite_chat_id
    assert invite_chat_id({"chat": {"id": -1, "type": "CHAT"}, "start_param": "chat-2"}) == -1
    assert invite_chat_id({"chat": {"id": 5, "type": "DIALOG"}, "start_param": "chat-2"}) == -2
    assert invite_chat_id({"start_param": "chat-2"}) == -2
    assert invite_chat_id({"start_param": "что-то другое"}) is None
    assert invite_chat_id({}) is None


def vote(invite_id: str, answer: str) -> dict:
    """Нажатие кнопки на карточке — так его присылает МАКС."""
    return {"update_type": "message_callback",
            "callback": {"callback_id": "cb", "payload": f"vote:{invite_id}:{answer}",
                         "user": {"user_id": 7, "first_name": "Петя"}}}


def test_vote_button_updates_card(client, api):
    invite_id = client.post("/api/invites", json={"event_id": "party"}).json()["invite_id"]
    asyncio.run(bot.handle_update(api, vote(invite_id, "maybe")))
    asyncio.run(bot.handle_update(api, vote(invite_id, "no")))  # Петя передумал
    first, second = api.answers
    assert first["notification"] == "Записал: Может"
    assert "Может (1): Петя" in first["text"]
    assert "Не могу (1): Петя" in second["text"]
    assert "Может (0)" in second["text"]  # повторное нажатие меняет ответ, а не добавляет второй
    assert [b["text"] for b in second["buttons"][0]] == ["Иду", "Может", "Не могу"]


def test_vote_on_unknown_card_says_it_is_outdated(api):
    asyncio.run(bot.handle_update(api, vote("nope", "going")))
    [answer] = api.answers
    assert answer["text"] is None  # карточку не трогаем, только всплывающее сообщение
    assert "устарела" in answer["notification"]
