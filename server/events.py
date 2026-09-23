"""События от куратора: читаем data/events.json и проверяем, что всё заполнено.

Файл читается при каждом запросе, так что правки куратора видны сразу, без перезапуска.
"""
import json
from datetime import datetime
from pathlib import Path

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
    for axis in ("nrg", "dep"):
        if event[axis] not in (0, 1, 2):
            raise ValueError(f"Событие {name}: {axis} должно быть 0, 1 или 2")
    if not isinstance(event["price"], int) or event["price"] < 0:
        raise ValueError(f"Событие {name}: price — целое число рублей, 0 = бесплатно")
    if event.get("starts_at"):
        datetime.fromisoformat(event["starts_at"])  # упадёт, если дата записана неправильно
    elif not event.get("anytime"):
        raise ValueError(f"Событие {name}: нужна дата starts_at или \"anytime\": true")
