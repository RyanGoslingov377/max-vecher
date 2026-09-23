import random
from datetime import date, datetime

from server.picker import KAZAN_TZ, pick, resolve_day

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=KAZAN_TZ)  # суббота, полдень
SATURDAY = date(2026, 9, 26)


def event(id, nrg, dep, tags=(), price=0, growth=False, starts_at=None):
    ev = {"id": id, "title": id, "place": "-", "price": price, "tags": list(tags),
          "nrg": nrg, "dep": dep, "growth": growth, "why": "-"}
    if starts_at:
        ev["starts_at"] = starts_at
    else:
        ev["anytime"] = True
    return ev


EVENTS = [
    event("dj", 2, 0, ["музыка", "танцы"], price=500),
    event("quiz", 2, 0, ["игры"], price=300),
    event("boxing", 2, 2, ["спорт"]),
    event("walk", 0, 0, ["природа"]),
    event("popart", 0, 0, ["арт"], price=200),
    event("voices", 0, 2, ["арт"], price=200),
    event("cello", 0, 2, ["музыка"], price=900),
    event("lecture", 0, 1, ["лекция"], growth=True),
    event("tour", 1, 1, ["экскурсия"], growth=True),
]


def ids(results):
    return [r["event"]["id"] for r in results]


def test_charged_prefers_music_and_dance():
    assert ids(pick(EVENTS, "charged", SATURDAY, now=NOW))[0] == "dj"


def test_same_format_lands_in_different_moods():
    # Две выставки одного формата: лёгкая — в «Хочу выдохнуть», тяжёлая — в «Погрустить красиво»
    assert "popart" in ids(pick(EVENTS, "exhale", SATURDAY, now=NOW))
    assert "voices" not in ids(pick(EVENTS, "exhale", SATURDAY, now=NOW))
    assert ids(pick(EVENTS, "blue", SATURDAY, now=NOW))[0] == "voices"


def test_learn_returns_only_growth_events():
    assert set(ids(pick(EVENTS, "learn", SATURDAY, now=NOW))) == {"lecture", "tour"}


def test_budget_puts_cheap_first_and_marks_expensive():
    results = pick(EVENTS, "charged", SATURDAY, budget_on=True, now=NOW)
    assert ids(results)[0] == "quiz"  # dj ближе по осям, но дороже 300 ₽
    dj = next(r for r in pick(EVENTS, "charged", SATURDAY, budget_on=True, now=NOW, limit=99) if r["event"]["id"] == "dj")
    assert dj["over_budget"] is True


def test_budget_off_marks_nothing():
    assert not any(r["over_budget"] for r in pick(EVENTS, "blue", SATURDAY, now=NOW))


def test_day_filter():
    events = EVENTS + [
        event("sat-party", 2, 0, ["танцы"], starts_at="2026-09-26T22:00:00+03:00"),
        event("sun-party", 2, 0, ["танцы"], starts_at="2026-09-27T22:00:00+03:00"),
        event("sat-morning", 2, 0, ["танцы"], starts_at="2026-09-26T09:00:00+03:00"),  # уже прошло
    ]
    found = ids(pick(events, "charged", SATURDAY, now=NOW, limit=99))
    assert "sat-party" in found
    assert "sun-party" not in found
    assert "sat-morning" not in found


def test_wild_gives_three_different_events():
    results = pick(EVENTS, "wild", SATURDAY, now=NOW, rng=random.Random(1))
    assert len(results) == 3
    assert len(set(ids(results))) == 3


def test_resolve_day():
    wednesday = datetime(2026, 9, 23, 20, 0, tzinfo=KAZAN_TZ)
    assert resolve_day("today", wednesday) == date(2026, 9, 23)
    assert resolve_day("tomorrow", wednesday) == date(2026, 9, 24)
    assert resolve_day("saturday", wednesday) == date(2026, 9, 26)
    assert resolve_day("saturday", NOW) == SATURDAY  # в субботу «суббота» — это сегодня
