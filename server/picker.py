"""Подбор событий под настроение: расстояние по двум осям + бонус за совпадение тега.

Обоснование — в документе команды, раздел «Как работает подбор».
"""
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

KAZAN_TZ = timezone(timedelta(hours=3))  # в Казани UTC+3 круглый год
BUDGET_MAX = 300  # руб., порог тумблера «Бюджет поджимает»
TAG_BONUS = 0.6


@dataclass(frozen=True)
class Mood:
    id: str
    title: str
    nrg: int = 0
    dep: int = 0
    tags: frozenset[str] = frozenset()
    growth: bool = False  # «Узнать новое»: не оси, а фильтр по флагу события


MOODS = {
    mood.id: mood
    for mood in [
        Mood("charged", "Заряжен(а)", nrg=2, dep=0, tags=frozenset({"музыка", "танцы"})),
        Mood("release", "Выпустить пар", nrg=2, dep=2, tags=frozenset({"спорт", "юмор"})),
        Mood("exhale", "Хочу выдохнуть", nrg=0, dep=0, tags=frozenset({"природа", "тишина"})),
        Mood("blue", "Погрустить красиво", nrg=0, dep=2, tags=frozenset({"арт", "кино"})),
        Mood("learn", "Узнать новое", growth=True),
    ]
}
EMOTIONAL = ["charged", "release", "exhale", "blue"]
WILD = "wild"  # «Удиви меня»: по одному событию из трёх случайных настроений
DAYS = ("today", "tomorrow", "saturday")


def resolve_day(day: str, now: datetime) -> date:
    today = now.astimezone(KAZAN_TZ).date()
    if day == "today":
        return today
    if day == "tomorrow":
        return today + timedelta(days=1)
    if day == "saturday":
        return today + timedelta(days=(5 - today.weekday()) % 7)
    raise ValueError(f"Неизвестный день: {day}")


def starts_at(event: dict) -> datetime | None:
    raw = event.get("starts_at")
    if not raw:
        return None
    start = datetime.fromisoformat(raw)
    return start if start.tzinfo else start.replace(tzinfo=KAZAN_TZ)


def is_on_day(event: dict, day: date, now: datetime) -> bool:
    if event.get("anytime"):
        return True
    start = starts_at(event)
    if start.astimezone(KAZAN_TZ).date() != day:
        return False
    return start > now - timedelta(hours=1)  # началось больше часа назад — уже не предлагаем


def score(mood: Mood, event: dict) -> float:
    distance = math.hypot(mood.nrg - event["nrg"], mood.dep - event["dep"])
    if mood.tags & set(event["tags"]):
        distance -= TAG_BONUS
    return distance


def pick(
    events: list[dict],
    mood_id: str,
    day: date,
    *,
    budget_on: bool = False,
    now: datetime | None = None,
    rng: random.Random | None = None,
    limit: int = 3,
) -> list[dict]:
    now = now or datetime.now(KAZAN_TZ)
    if mood_id == WILD:
        return pick_wild(events, day, budget_on=budget_on, now=now, rng=rng or random.Random())

    mood = MOODS[mood_id]
    pool = [e for e in events if is_on_day(e, day, now)]
    if mood.growth:
        pool = [e for e in pool if e["growth"]]

    results = [
        {
            "event": event,
            "mood": mood.id,
            "score": 0.0 if mood.growth else round(score(mood, event), 3),
            "over_budget": budget_on and event["price"] > BUDGET_MAX,
        }
        for event in pool
    ]
    # Дешёвые выше дорогих (если включён бюджет), потом ближе по осям, потом раньше начало
    results.sort(key=lambda r: (r["over_budget"], r["score"], _start_sort_key(r["event"])))
    return results[:limit]


def pick_wild(events: list[dict], day: date, *, budget_on: bool, now: datetime, rng: random.Random) -> list[dict]:
    results, seen_ids = [], set()
    for mood_id in rng.sample(EMOTIONAL, 3):
        for result in pick(events, mood_id, day, budget_on=budget_on, now=now, limit=len(events)):
            if result["event"]["id"] not in seen_ids:
                seen_ids.add(result["event"]["id"])
                results.append(result)
                break
    return results


def _start_sort_key(event: dict) -> float:
    start = starts_at(event)
    return start.timestamp() if start else math.inf  # «в любое время» — после событий с точным временем
