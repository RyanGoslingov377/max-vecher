"""События от куратора: читаем data/events.json и проверяем, что всё заполнено.

Файл читается при каждом запросе, так что правки куратора видны сразу, без перезапуска.

Когда проходит событие — ровно одно из трёх полей:
- "starts_at": "2026-10-03T20:00:00+03:00" — разовое;
- "weekly": {"days": ["пт", "сб"], "time": "20:00"} — регулярное, по дням недели;
- "anytime": true — в любое время (прогулки, выставки).
"""
import json
import re
from datetime import date, datetime
from pathlib import Path

from .picker import WEEKDAY_NAMES, occurrence_on

EVENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "events.json"

REQUIRED_FIELDS = ("id", "title", "place", "price", "tags", "nrg", "dep", "growth", "why")


def load_events(path: Path = EVENTS_FILE) -> list[dict]:
    events = json.loads(path.read_text(encoding="utf-8"))
    seen_ids = set()
    for event in events:
        check_event(event)
        if event["id"] in seen_ids:
            raise ValueError(f"Повторяется id события: {event['id']}")
        seen_ids.add(event["id"])
    return events


def check_event(event: dict) -> None:
    name = event.get("id", "<без id>")
    missing = [field for field in REQUIRED_FIELDS if field not in event]
    if missing:
        raise ValueError(f"Событие {name}: не заполнены поля {', '.join(missing)}")
    if "@" in event["id"]:
        raise ValueError(f"Событие {name}: в id не должно быть «@»")
    for axis in ("nrg", "dep"):
        if event[axis] not in (0, 1, 2):
            raise ValueError(f"Событие {name}: {axis} должно быть 0, 1 или 2")
    if not isinstance(event["price"], int) or event["price"] < 0:
        raise ValueError(f"Событие {name}: price — целое число рублей, 0 = бесплатно")

    kinds = [kind for kind in ("starts_at", "weekly", "anytime") if event.get(kind)]
    if len(kinds) != 1:
        raise ValueError(f"Событие {name}: нужно ровно одно из starts_at, weekly или \"anytime\": true")
    if event.get("starts_at"):
        datetime.fromisoformat(event["starts_at"])  # упадёт, если дата записана неправильно
    if event.get("weekly"):
        weekly = event["weekly"]
        days = weekly.get("days") or []
        if not days or any(day not in WEEKDAY_NAMES for day in days):
            raise ValueError(f"Событие {name}: weekly.days — дни из {', '.join(WEEKDAY_NAMES)}")
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", weekly.get("time", "")):
            raise ValueError(f"Событие {name}: weekly.time — время вида 20:00")


def find_event(event_id: str) -> dict | None:
    """Событие по id. Регулярное в конкретный день приходит как «quiz@2026-10-02» — возвращаем его с датой."""
    base_id, _, day = event_id.partition("@")
    event = next((event for event in load_events() if event["id"] == base_id), None)
    if event is None or not day:
        return event
    try:
        start = occurrence_on(event, date.fromisoformat(day))
    except ValueError:
        return None
    if start is None:
        return None  # в этот день событие не проходит
    return {**event, "id": event_id, "starts_at": start.isoformat()}
