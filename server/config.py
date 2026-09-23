"""Настройки из файла .env (шаблон — .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip()
PORT = int(os.environ.get("PORT", "3000"))

# 0 — сервер без бота: так работает фронт, чтобы не перехватывать события у бэкенда
BOT_ENABLED = os.environ.get("BOT_ENABLED", "1").strip() != "0"

if BOT_ENABLED and not BOT_TOKEN:
    raise SystemExit("Нет MAX_BOT_TOKEN: впиши токен в .env или поставь BOT_ENABLED=0, чтобы запустить сервер без бота")
