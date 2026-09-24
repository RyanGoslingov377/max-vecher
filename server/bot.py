"""Бот: получает события из МАКС (long polling) и отвечает на них."""
import asyncio
import logging
import secrets
import time

from . import db
from .events import find_event
from .max_api import MaxApi, callback_button, link_button
from .picker import KAZAN_TZ, starts_at

log = logging.getLogger("bot")

HELP_TEXT = (
    "Привет! Я помогаю выбрать вечер по настроению и собрать друзей.\n\n"
    "Сейчас я в тестовом режиме. Команды:\n"
    "/вечер — прислать тестовую карточку «Иду / Может / Не могу»\n"
    "/help — эта подсказка\n\n"
    "В групповом чате сделайте меня администратором, иначе я не увижу команды."
)

ANSWERS = {"going": "Иду", "maybe": "Может", "no": "Не могу"}
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


# Когда бот последний раз успешно получил события от МАКС — показывается в /api/health
status = {"username": None, "last_poll": None}

RETRY_SECONDS = 5


async def run_bot(api: MaxApi) -> None:
    """Бесконечный цикл: любая ошибка связи — запись в лог и повтор, бот никогда не останавливается молча."""
    marker = None
    while True:
        try:
            if status["username"] is None:
                me = await api.me()
                status["username"] = me.get("username")
                log.info("Бот запущен: @%s", status["username"])
            data = await api.get_updates(marker)
            status["last_poll"] = time.time()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Нет связи с МАКС, повтор через %s сек", RETRY_SECONDS)
            await asyncio.sleep(RETRY_SECONDS)
            continue
        marker = data.get("marker", marker)
        for update in data.get("updates", []):
            try:
                await handle_update(api, update)
            except Exception:
                log.exception("Ошибка при обработке события %s", update.get("update_type"))


async def handle_update(api: MaxApi, update: dict) -> None:
    kind = update.get("update_type")
    log.info("Событие: %s", kind)

    if kind == "message_created":
        message = update["message"]
        if message.get("sender", {}).get("is_bot"):
            return
        chat_id = message["recipient"]["chat_id"]
        log.info("Сообщение в чате %s", chat_id)  # отсюда берут DEV_CHAT_ID для локальной проверки
        text = (message.get("body", {}).get("text") or "").strip().lower()
        if text.startswith(("/start", "/help")):
            await api.send_message(chat_id, HELP_TEXT)
        elif text.startswith(("/вечер", "/vecher")):
            await send_test_card(api, chat_id)

    elif kind in ("bot_started", "bot_added"):
        # bot_started — нажали «Начать» в личке, bot_added — бота добавили в группу
        await api.send_message(update["chat_id"], HELP_TEXT)

    elif kind == "message_callback":
        await on_vote(api, update["callback"])


async def send_test_card(api: MaxApi, chat_id: int) -> None:
    invite_id = secrets.token_hex(4)
    db.create_invite(invite_id, chat_id)
    await api.send_message(chat_id, card_text(invite_id), card_buttons(invite_id))


async def on_vote(api: MaxApi, callback: dict) -> None:
    # payload кнопки выглядит так: "vote:<id приглашения>:<ответ>"
    parts = (callback.get("payload") or "").split(":")
    if len(parts) != 3 or parts[0] != "vote" or parts[2] not in ANSWERS:
        return
    _, invite_id, answer = parts
    if db.get_invite(invite_id) is None:
        await api.answer_callback(callback["callback_id"], notification="Карточка устарела, пришлите /вечер заново")
        return

    user = callback.get("user", {})
    name = user.get("first_name") or user.get("name") or "Кто-то"
    db.set_answer(invite_id, user["user_id"], name, answer)

    await api.answer_callback(
        callback["callback_id"],
        text=card_text(invite_id),
        buttons=card_buttons(invite_id),
        notification=f"Записал: {ANSWERS[answer]}",
    )


async def send_invite(api: MaxApi, invite_id: str, *, chat_id: int | None, user_id: int | None) -> None:
    """Карточка приглашения на событие: в групповой чат, а если чата нет — в личку с ботом."""
    await api.send_message(chat_id, card_text(invite_id), card_buttons(invite_id), user_id=user_id)


def invite_event(invite_id: str) -> dict | None:
    invite = db.get_invite(invite_id)
    return find_event(invite["event_id"]) if invite and invite["event_id"] else None


def event_lines(event: dict) -> list[str]:
    start = starts_at(event)
    if start:
        start = start.astimezone(KAZAN_TZ)
        when = f"{WEEKDAYS[start.weekday()]} {start:%d.%m, %H:%M}"
    else:
        when = "в любое время"
    price = f"{event['price']} ₽" if event["price"] else "бесплатно"
    return [event["title"], f"{when} · {event['place']} · {price}", event["why"]]


def card_text(invite_id: str) -> str:
    event = invite_event(invite_id)
    if event:
        lines = [*event_lines(event), "", "Кто идёт?"]
    else:
        lines = ["Тестовое приглашение", "Проверяем кнопки: нажмите, пойдёте ли вы.", ""]
    votes = db.get_answers(invite_id)
    for key, label in ANSWERS.items():
        names = [name for name, answer in votes if answer == key]
        lines.append(f"{label} ({len(names)})" + (": " + ", ".join(names) if names else ""))
    return "\n".join(lines)


def card_buttons(invite_id: str) -> list:
    rows = [[callback_button(label, f"vote:{invite_id}:{key}") for key, label in ANSWERS.items()]]
    event = invite_event(invite_id)
    if event and event.get("ticket_url"):
        rows.append([link_button("Билеты", event["ticket_url"])])
    return rows
