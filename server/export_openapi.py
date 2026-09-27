"""Сохраняет описание API в openapi.json (для экспертов и DATA-API.yaml).

Запуск после любого изменения API: python -m server.export_openapi
"""
import json
from pathlib import Path

from .main import app

OPENAPI_FILE = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> None:
    OPENAPI_FILE.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Сохранено: {OPENAPI_FILE}")


if __name__ == "__main__":
    main()
