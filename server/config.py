"""Настройки из файла .env (шаблон — .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip()
PORT = int(os.environ.get("PORT", "3000"))

if not BOT_TOKEN:
    raise SystemExit("Нет MAX_BOT_TOKEN: скопируй .env.example в .env и впиши токен бота")
