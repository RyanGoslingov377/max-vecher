"""Проверка data/events.json: запускайте после каждой правки событий."""
from server.events import load_events
from server.picker import EMOTIONAL, MOODS


def test_events_file_is_valid():
    assert len(load_events()) > 0  # load_events сам падает с понятной ошибкой на кривом событии


def test_every_mood_has_candidates():
    events = load_events()
    assert any(e["growth"] for e in events), "Нет ни одного события для «Узнать новое»"
    for mood_id in EMOTIONAL:
        mood = MOODS[mood_id]
        close = [e for e in events if abs(e["nrg"] - mood.nrg) + abs(e["dep"] - mood.dep) <= 1]
        assert close, f"Нет подходящих событий для настроения «{mood.title}»"
