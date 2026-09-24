"""Кто открыл мини-приложение: проверка подписи данных запуска от МАКС (initData).

Мини-приложение берёт строку window.WebApp.initData и шлёт её в заголовке X-Max-Init-Data.
МАКС подписывает эту строку токеном нашего бота, поэтому подделать пользователя или чат нельзя.
Алгоритм — https://dev.max.ru/docs/webapps/validation
"""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import unquote

from fastapi import Header, HTTPException

from . import config

log = logging.getLogger("auth")

MAX_AGE_SECONDS = 24 * 3600  # подпись старше суток не принимаем

DEV_USER = {"id": 1, "first_name": "Тест"}


def check_init_data(init_data: str, bot_token: str, *, now: float | None = None) -> dict:
    """Возвращает данные запуска (user, chat, start_param…), если подпись верна. Иначе — ValueError."""
    params = {}
    for part in init_data.split("&"):
        key, _, value = part.partition("=")
        # unquote, а не unquote_plus: так же, как decodeURIComponent в примере МАКС («+» остаётся «+»)
        params[unquote(key)] = unquote(value)

    received_hash = params.pop("hash", "")
    if not received_hash:
        raise ValueError("в данных нет подписи hash")

    launch_params = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash.lower()):
        raise ValueError("подпись не совпала")

    auth_date = int(params.get("auth_date") or 0)
    if (now or time.time()) - auth_date > MAX_AGE_SECONDS:
        raise ValueError("подпись устарела")

    # user и chat приходят как JSON-строки — превращаем их в словари
    return {key: _maybe_json(value) for key, value in params.items()}


def _maybe_json(value: str):
    if value[:1] in ("{", "["):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


async def launch_data(x_max_init_data: str | None = Header(default=None)) -> dict:
    """Зависимость FastAPI: данные запуска для эндпоинтов, которым важно, кто спрашивает."""
    if not x_max_init_data:
        if config.DEV_AUTH:
            chat = {"id": config.DEV_CHAT_ID, "type": "CHAT"} if config.DEV_CHAT_ID else None
            return {"user": DEV_USER, "chat": chat, "dev": True}
        raise HTTPException(401, "Нет подписи МАКС: откройте мини-приложение из бота")
    try:
        return check_init_data(x_max_init_data, config.BOT_TOKEN)
    except ValueError as error:
        log.warning("initData не прошла проверку: %s", error)
        raise HTTPException(401, f"Подпись МАКС не прошла проверку: {error}")
