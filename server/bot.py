"""Бот: получает события из МАКС (long polling) и отвечает на них."""
import asyncio
import logging
import secrets

from . import db
from .max_api import MaxApi, callback_button

log = logging.getLogger("bot")

HELP_TEXT = (
    "Привет! Я помогаю выбрать вечер по настроению и собрать друзей.\n\n"
    "Сейчас я в тестовом режиме. Команды:\n"
    "/вечер — прислать тестовую карточку «Иду / Может / Не могу»\n"
    "/help — эта подсказка\n\n"
    "В групповом чате сделайте меня администратором, иначе я не увижу команды."
)

ANSWERS = {"going": "Иду", "maybe": "Может", "no": "Не могу"}


async def run_bot(api: MaxApi) -> None:
    me = await api.me()
    log.info("Бот запущен: @%s", me.get("username"))
    marker = None
    while True:
        try:
            data = await api.get_updates(marker)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Не удалось получить события, повтор через 3 сек")
            await asyncio.sleep(3)
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


def card_text(invite_id: str) -> str:
    votes = db.get_answers(invite_id)
    lines = ["Тестовое приглашение", "Проверяем кнопки: нажмите, пойдёте ли вы.", ""]
    for key, label in ANSWERS.items():
        names = [name for name, answer in votes if answer == key]
        lines.append(f"{label} ({len(names)})" + (": " + ", ".join(names) if names else ""))
    return "\n".join(lines)


def card_buttons(invite_id: str) -> list:
    return [[callback_button(label, f"vote:{invite_id}:{key}") for key, label in ANSWERS.items()]]
