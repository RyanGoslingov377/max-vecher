"""Форматы ответов API. Нужны, чтобы OpenAPI (/docs, /openapi.json) точно описывал, что возвращает сервер."""
from pydantic import BaseModel, Field


class Weekly(BaseModel):
    days: list[str] = Field(description="Дни недели: пн, вт, ср, чт, пт, сб, вс")
    time: str = Field(description="Время начала, например 20:00")


class Event(BaseModel):
    id: str = Field(description="id события; у регулярного в конкретный день — вида quiz@2026-10-02")
    title: str
    place: str
    starts_at: str | None = Field(None, description="Начало, ISO 8601 с +03:00. Нет — событие «в любое время»")
    anytime: bool | None = Field(None, description="true — можно прийти в любое время")
    weekly: Weekly | None = Field(None, description="Расписание регулярного события")
    price: int = Field(description="Цена в рублях, 0 — бесплатно")
    tags: list[str]
    nrg: int = Field(description="Энергия 0–2: 0 — тихо, 2 — громко и активно")
    dep: int = Field(description="Глубина 0–2: 0 — легко, 2 — сильно трогает")
    growth: bool = Field(description="Событие для настроения «Узнать новое»")
    why: str = Field(description="Почему подходит — короткая фраза для карточки")
    ticket_url: str | None = None


class PickResult(BaseModel):
    event: Event
    mood: str = Field(description="Настроение, под которое подобрано (в «Удиви меня» у каждого своё)")
    score: float = Field(description="Расстояние до настроения по осям: чем меньше, тем лучше")
    over_budget: bool = Field(description="Дороже 300 ₽ при включённом «Бюджет поджимает»")


class PickOut(BaseModel):
    mood: str
    day: str = Field(description="Дата, на которую подобрано, YYYY-MM-DD")
    budget: bool
    results: list[PickResult] = Field(description="До трёх событий, лучшее — первое")


class MeOut(BaseModel):
    user: dict | None = Field(None, description="Пользователь МАКС: id, first_name, …")
    chat: dict | None = Field(None, description="Чат, из которого открыто мини-приложение: id, type")
    start_param: str | dict | None = Field(None, description="payload кнопки, которой открыли приложение")


class InviteIn(BaseModel):
    event_id: str = Field(description="id события из /api/pick")


class InviteCreated(BaseModel):
    invite_id: str
    sent: bool = Field(description="false — приглашение сохранено, но бот карточку не отправлял (локальный запуск)")


class Answer(BaseModel):
    name: str
    answer: str = Field(description="going / maybe / no")


class InviteOut(BaseModel):
    invite_id: str
    event: Event | None = None
    answers: list[Answer]


class StatsOut(BaseModel):
    going: int = Field(description="Сколько человек собирались (по приглашениям, где уже спросили «Сходили?»)")
    went: int = Field(description="Сколько ответили «Сходил(а)»")
    rate: float | None = Field(description="went ÷ going — главная метрика продукта")


class BotHealth(BaseModel):
    enabled: bool
    username: str | None
    seconds_since_poll: int | None = Field(description="Сколько секунд назад бот последний раз получил события")
    ok: bool = Field(description="false — бот больше 2 минут не получал событий от МАКС")


class HealthOut(BaseModel):
    ok: bool
    bot: BotHealth
