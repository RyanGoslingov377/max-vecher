"""Проверка data/events.json: запускайте после каждой правки событий."""
from datetime import date, datetime, time, timedelta

from server.events import load_events
from server.picker import EMOTIONAL, KAZAN_TZ, MOODS, WILD, pick


def test_events_file_is_valid():
    assert len(load_events()) > 0  # load_events сам падает с понятной ошибкой на кривом событии


def test_every_mood_has_candidates():
    events = load_events()
    assert any(e["growth"] for e in events), "Нет ни одного события для «Узнать новое»"
    for mood_id in EMOTIONAL:
        mood = MOODS[mood_id]
        close = [e for e in events if abs(e["nrg"] - mood.nrg) + abs(e["dep"] - mood.dep) <= 1]
        assert close, f"Нет подходящих событий для настроения «{mood.title}»"


def test_events_cover_every_mood_after_deadline_week():
    events = load_events()
    start = date(2026, 10, 5)  # после дедлайна и после последних разовых событий
    for offset in range(7):
        day = start + timedelta(days=offset)
        now = datetime.combine(day, time(12, 0), tzinfo=KAZAN_TZ)
        for mood_id in [*MOODS, WILD]:
            results = pick(events, mood_id, day, now=now)
            budget_results = pick(events, mood_id, day, budget_on=True, now=now)
            assert len(results) == 3, f"{mood_id} пустеет {day}"
            assert len(budget_results) == 3, f"{mood_id} с бюджетом пустеет {day}"
            assert any(r["event"]["price"] <= 300 for r in budget_results), f"{mood_id} без дешёвых вариантов {day}"
