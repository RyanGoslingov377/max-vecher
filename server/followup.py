"""«Сходили?»: после события бот спрашивает тех, кто собирался. Это наша главная метрика.

Вопрос уходит в тот же чат, что и приглашение: писать первым в личку человеку, который
сам не писал боту, скорее всего нельзя, а в чат с приглашением бот писать точно может.
"""
import asyncio
import logging
from datetime import datetime, time, timedelta

import httpx

from . import config, db
from .events import find_event
from .max_api import MaxApi, callback_button
from .picker import KAZAN_TZ, starts_at

log = logging.getLogger("followup")

CHECK_EVERY_SECONDS = 30
ASK_AT = time(12, 0)  # в полдень следующего дня после события


def due_at(invite, event: dict | None, delay_min: int | None) -> datetime:
    """Когда спрашивать: в демо — через delay_min минут после приглашения, иначе — назавтра после события."""
    created = datetime.fromisoformat(invite["created_at"])
    if delay_min is not None:
        return created + timedelta(minutes=delay_min)
    start = starts_at(event) if event else None
    day = (start or created).astimezone(KAZAN_TZ).date()
    return datetime.combine(day + timedelta(days=1), ASK_AT, tzinfo=KAZAN_TZ)


async def run_followups(api: MaxApi) -> None:
    """Фоновая задача: раз в 30 секунд проверяет, кого пора спросить."""
    while True:
        try:
            await send_due_followups(api, datetime.now(KAZAN_TZ))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Ошибка при рассылке «Сходили?»")
        await asyncio.sleep(CHECK_EVERY_SECONDS)


async def send_due_followups(api: MaxApi, now: datetime) -> None:
    for invite in db.invites_awaiting_followup():
        event = find_event(invite["event_id"])
        if now < due_at(invite, event, config.FOLLOWUP_DELAY_MIN):
            continue
        db.mark_followup_sent(invite["id"])  # отмечаем до отправки: при ошибке не будем спрашивать по кругу
        chat_id = invite["chat_id"] or None  # 0 — приглашение было в личке с ботом
        try:
            await api.send_message(
                chat_id,
                followup_text(invite["id"]),
                followup_buttons(invite["id"]),
                user_id=None if chat_id else invite["creator_user_id"],
            )
            log.info("Спросил «Сходили?» по приглашению %s", invite["id"])
        except httpx.HTTPError as error:
            log.warning("Не удалось спросить «Сходили?» по приглашению %s: %s", invite["id"], error)


def followup_text(invite_id: str) -> str:
    invite = db.get_invite(invite_id)
    event = find_event(invite["event_id"]) if invite and invite["event_id"] else None
    going = db.get_going(invite_id)
    outcomes = db.get_outcomes(invite_id)
    went = [name for user_id, name in going if outcomes.get(user_id) is True]
    missed = [name for user_id, name in going if outcomes.get(user_id) is False]
    lines = [
        f"Как прошёл вечер? «{event['title'] if event else 'Вечер'}»",
        "Собирались: " + ", ".join(name for _, name in going),
        "Сходили: " + (", ".join(went) or "—"),
        "Не получилось: " + (", ".join(missed) or "—"),
    ]
    if config.FOLLOWUP_DELAY_MIN is not None:
        lines += ["", "(демо: в жизни этот вопрос приходит на следующий день после события)"]
    return "\n".join(lines)


def followup_buttons(invite_id: str) -> list:
    return [[callback_button("Сходил(а)", f"went:{invite_id}:1"), callback_button("Не получилось", f"went:{invite_id}:0")]]


async def on_went(api: MaxApi, callback: dict) -> None:
    # payload кнопки: "went:<id приглашения>:1" или "...:0"
    parts = (callback.get("payload") or "").split(":")
    if len(parts) != 3 or parts[2] not in ("0", "1"):
        return
    _, invite_id, went = parts
    user_id = callback.get("user", {}).get("user_id")
    if db.get_answer(invite_id, user_id) != "going":
        await api.answer_callback(callback["callback_id"], notification="Этот вопрос для тех, кто собирался")
        return
    db.set_outcome(invite_id, user_id, went == "1")
    await api.answer_callback(
        callback["callback_id"],
        text=followup_text(invite_id),
        buttons=followup_buttons(invite_id),
        notification="Спасибо, записал!",
    )
