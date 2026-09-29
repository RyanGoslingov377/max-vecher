"""Настройки из файла .env (шаблон — .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
PORT = int(os.environ.get("PORT", "3000"))

# 0 — сервер без бота: локальная разработка, чтобы не перехватывать события у бота на хостинге
BOT_ENABLED = os.environ.get("BOT_ENABLED", "1").strip() != "0"

# 1 — пускать запросы без подписи МАКС от тестового пользователя. Только для локальной разработки!
DEV_AUTH = os.environ.get("DEV_AUTH", "0").strip() == "1"
# В dev-режиме — чат, куда слать приглашения (id можно взять из логов бота). Пусто — без чата.
DEV_CHAT_ID = int(os.environ["DEV_CHAT_ID"]) if os.environ.get("DEV_CHAT_ID", "").strip() else None

# «Сходили?»: пусто — в полдень следующего дня после события; число — через столько минут (для демо)
FOLLOWUP_DELAY_MIN = int(os.environ["FOLLOWUP_DELAY_MIN"]) if os.environ.get("FOLLOWUP_DELAY_MIN", "").strip() else None
