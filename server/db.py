"""SQLite: приглашения в чатах и ответы на них. Файл базы — data/app.db (в git не попадает)."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    id              TEXT PRIMARY KEY,
    event_id        TEXT,               -- NULL у тестовой карточки
    chat_id         INTEGER NOT NULL,
    creator_user_id INTEGER,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rsvps (
    invite_id  TEXT NOT NULL REFERENCES invites(id),
    user_id    INTEGER NOT NULL,
    user_name  TEXT NOT NULL,
    answer     TEXT NOT NULL,           -- going / maybe / no
    updated_at TEXT NOT NULL,
    PRIMARY KEY (invite_id, user_id)    -- повторное нажатие меняет ответ, а не добавляет новый
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_invite(invite_id: str, chat_id: int, event_id: str | None = None, creator_user_id: int | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO invites (id, event_id, chat_id, creator_user_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (invite_id, event_id, chat_id, creator_user_id, _now()),
        )


def get_invite(invite_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()


def set_answer(invite_id: str, user_id: int, user_name: str, answer: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO rsvps (invite_id, user_id, user_name, answer, updated_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (invite_id, user_id)
            DO UPDATE SET user_name = excluded.user_name, answer = excluded.answer, updated_at = excluded.updated_at
            """,
            (invite_id, user_id, user_name, answer, _now()),
        )


def get_answers(invite_id: str) -> list[tuple[str, str]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_name, answer FROM rsvps WHERE invite_id = ? ORDER BY updated_at", (invite_id,)
        ).fetchall()
    return [(row["user_name"], row["answer"]) for row in rows]
