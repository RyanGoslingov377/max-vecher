import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from server import bot, config, db, events, followup
from server.main import app
from server.picker import KAZAN_TZ

EVENTS = [
    {"id": "party", "title": "DJ-сет", "place": "Крыша", "starts_at": "2026-09-26T22:00:00+03:00",
     "price": 500, "tags": ["музыка"], "nrg": 2, "dep": 0, "growth": False, "why": "Громко"},
    {"id": "walk", "title": "Прогулка", "place": "Центр", "anytime": True,
     "price": 0, "tags": ["природа"], "nrg": 0, "dep": 0, "growth": False, "why": "Тихо"},
]


class FakeApi:
    def __init__(self):
        self.sent = []
        self.answers = []

    async def send_message(self, chat_id, text, buttons=None, *, user_id=None):
        self.sent.append({"chat_id": chat_id, "user_id": user_id, "text": text, "buttons": buttons})
        return {}

    async def answer_callback(self, callback_id, *, text=None, buttons=None, notification=None):
        self.answers.append({"text": text, "notification": notification})
        return {}


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    monkeypatch.setattr(events, "load_events", lambda: EVENTS)
    monkeypatch.setattr(config, "FOLLOWUP_DELAY_MIN", None)


def make_invite(invite_id="inv1", chat_id=-555, event_id="party"):
    db.create_invite(invite_id, chat_id, event_id, creator_user_id=1)
    db.set_answer(invite_id, 1, "Аня", "going")
    db.set_answer(invite_id, 7, "Петя", "maybe")
    return invite_id


def test_due_next_day_noon_after_event():
    invite = {"created_at": "2026-09-24T10:00:00+00:00"}
    assert followup.due_at(invite, EVENTS[0], None) == datetime(2026, 9, 27, 12, 0, tzinfo=KAZAN_TZ)


def test_due_for_anytime_event_is_next_day_after_invite():
    invite = {"created_at": "2026-09-24T10:00:00+00:00"}
    assert followup.due_at(invite, EVENTS[1], None) == datetime(2026, 9, 25, 12, 0, tzinfo=KAZAN_TZ)


def test_due_in_demo_mode():
    invite = {"created_at": "2026-09-24T10:00:00+00:00"}
    assert followup.due_at(invite, EVENTS[0], 2) == datetime(2026, 9, 24, 10, 2, tzinfo=timezone.utc)


def test_asks_once_in_the_invite_chat_when_due():
    make_invite()
    api = FakeApi()
    asyncio.run(followup.send_due_followups(api, datetime(2026, 9, 27, 11, 0, tzinfo=KAZAN_TZ)))
    assert api.sent == []  # ещё рано

    asyncio.run(followup.send_due_followups(api, datetime(2026, 9, 27, 12, 1, tzinfo=KAZAN_TZ)))
    [message] = api.sent
    assert message["chat_id"] == -555
    assert "«DJ-сет»" in message["text"]
    assert "Собирались: Аня" in message["text"]  # Петя сказал «Может» — его не спрашиваем
    assert [b["payload"] for b in message["buttons"][0]] == ["went:inv1:1", "went:inv1:0"]

    asyncio.run(followup.send_due_followups(api, datetime(2026, 9, 28, 12, 0, tzinfo=KAZAN_TZ)))
    assert len(api.sent) == 1  # повторно не спрашиваем


def test_private_invite_is_asked_in_private_dialog():
    make_invite(chat_id=0)
    api = FakeApi()
    asyncio.run(followup.send_due_followups(api, datetime(2026, 9, 28, 12, 0, tzinfo=KAZAN_TZ)))
    assert api.sent[0]["chat_id"] is None
    assert api.sent[0]["user_id"] == 1


def test_test_card_without_event_is_not_asked():
    db.create_invite("test", -555)
    db.set_answer("test", 1, "Аня", "going")
    api = FakeApi()
    asyncio.run(followup.send_due_followups(api, datetime(2030, 1, 1, tzinfo=KAZAN_TZ)))
    assert api.sent == []


def went_callback(user_id, went="1"):
    return {"update_type": "message_callback",
            "callback": {"callback_id": "cb", "payload": f"went:inv1:{went}", "user": {"user_id": user_id}}}


def test_going_user_answers_and_card_updates():
    make_invite()
    api = FakeApi()
    asyncio.run(bot.handle_update(api, went_callback(1, "1")))
    assert db.get_outcomes("inv1") == {1: True}
    assert "Сходили: Аня" in api.answers[0]["text"]


def test_user_who_was_not_going_is_not_counted():
    make_invite()
    api = FakeApi()
    asyncio.run(bot.handle_update(api, went_callback(7, "1")))
    assert db.get_outcomes("inv1") == {}
    assert api.answers[0]["text"] is None
    assert "собирался" in api.answers[0]["notification"]


def test_stats_endpoint():
    make_invite()
    db.set_answer("inv1", 8, "Оля", "going")
    db.mark_followup_sent("inv1")
    db.set_outcome("inv1", 1, True)
    db.set_outcome("inv1", 8, False)
    assert TestClient(app).get("/api/stats").json() == {"going": 2, "went": 1, "rate": 0.5}


def test_demo_note_in_text(monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUP_DELAY_MIN", 2)
    make_invite()
    assert "демо" in followup.followup_text("inv1")
