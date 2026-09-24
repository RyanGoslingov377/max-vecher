"""SQLite: приглашения в чатах и ответы на них. Файл базы — data/app.db (в git не попадает)."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# В Docker база лежит в отдельном томе (DB_PATH задаёт docker-compose.yml), чтобы переживать пересборку
DB_PATH = Path(os.environ.get("DB_PATH") or Path(__file__).resolve().parent.parent / "data" / "app.db")

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
CREATE TABLE IF NOT EXISTS followups (  -- по каким приглашениям уже спросили «Сходили?»
    invite_id TEXT PRIMARY KEY REFERENCES invites(id),
    sent_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes (   -- ответы на «Сходили?»: основа метрики
    invite_id   TEXT NOT NULL REFERENCES invites(id),
    user_id     INTEGER NOT NULL,
    went        INTEGER NOT NULL,       -- 1 — сходил, 0 — не получилось
    answered_at TEXT NOT NULL,
    PRIMARY KEY (invite_id, user_id)
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
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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


def get_answer(invite_id: str, user_id: int) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT answer FROM rsvps WHERE invite_id = ? AND user_id = ?", (invite_id, user_id)).fetchone()
    return row["answer"] if row else None


def get_going(invite_id: str) -> list[tuple[int, str]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_id, user_name FROM rsvps WHERE invite_id = ? AND answer = 'going' ORDER BY updated_at",
            (invite_id,),
        ).fetchall()
    return [(row["user_id"], row["user_name"]) for row in rows]


def invites_awaiting_followup() -> list[sqlite3.Row]:
    """Приглашения на настоящие события, где кто-то собрался и «Сходили?» ещё не спрашивали."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM invites i
            WHERE i.event_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM followups f WHERE f.invite_id = i.id)
              AND EXISTS (SELECT 1 FROM rsvps r WHERE r.invite_id = i.id AND r.answer = 'going')
            """
        ).fetchall()


def mark_followup_sent(invite_id: str) -> None:
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO followups (invite_id, sent_at) VALUES (?, ?)", (invite_id, _now()))


def set_outcome(invite_id: str, user_id: int, went: bool) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO outcomes (invite_id, user_id, went, answered_at) VALUES (?, ?, ?, ?)
            ON CONFLICT (invite_id, user_id) DO UPDATE SET went = excluded.went, answered_at = excluded.answered_at
            """,
            (invite_id, user_id, int(went), _now()),
        )


def get_outcomes(invite_id: str) -> dict[int, bool]:
    with connect() as conn:
        rows = conn.execute("SELECT user_id, went FROM outcomes WHERE invite_id = ?", (invite_id,)).fetchall()
    return {row["user_id"]: bool(row["went"]) for row in rows}


def stats() -> tuple[int, int]:
    """Метрика: сколько человек собирались (там, где уже спросили «Сходили?») и сколько сходили."""
    with connect() as conn:
        going = conn.execute(
            "SELECT COUNT(*) FROM rsvps r JOIN followups f ON f.invite_id = r.invite_id WHERE r.answer = 'going'"
        ).fetchone()[0]
        went = conn.execute("SELECT COUNT(*) FROM outcomes WHERE went = 1").fetchone()[0]
    return going, went
