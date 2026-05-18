"""SQLite database layer for the hub server."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DEFAULT_DB = Path.home() / ".chenedusys" / "hub.db"


class Database:
    """Thin wrapper around SQLite for users and meetings."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = Path(db_path) if db_path else _DEFAULT_DB
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Idempotent schema migrations for existing databases."""
        cursor = self._conn.execute("PRAGMA table_info(users)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "status" not in columns:
            self._conn.execute(
                "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )
            self._conn.commit()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          TEXT PRIMARY KEY,
                username    TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role        TEXT NOT NULL DEFAULT 'student',
                status      TEXT NOT NULL DEFAULT 'active',
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS meetings (
                id              TEXT PRIMARY KEY,
                teacher_id      TEXT NOT NULL REFERENCES users(id),
                title           TEXT NOT NULL DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'waiting',
                max_participants INTEGER NOT NULL DEFAULT 5,
                p2p_host        TEXT,
                p2p_port        INTEGER,
                created_at      TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS meeting_participants (
                meeting_id  TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                user_id     TEXT NOT NULL REFERENCES users(id),
                joined_at   TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (meeting_id, user_id)
            );
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def create_user(
        self, user_id: str, username: str, password_hash: str,
        role: str = "student", status: str = "pending",
    ) -> None:
        self._conn.execute(
            "INSERT INTO users (id, username, password_hash, role, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, password_hash, role, status),
        )
        self._conn.commit()

    def get_user_by_username(self, username: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_pending_users(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, username, role, status, created_at FROM users WHERE status = 'pending' ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_all_users(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, username, role, status, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_user_status(self, user_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE users SET status = ? WHERE id = ?",
            (status, user_id),
        )
        self._conn.commit()

    def update_user_role(self, user_id: str, role: str) -> None:
        self._conn.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (role, user_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Meetings
    # ------------------------------------------------------------------

    def create_meeting(
        self,
        meeting_id: str,
        teacher_id: str,
        title: str = "",
        max_participants: int = 5,
        p2p_host: str | None = None,
        p2p_port: int | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO meetings (id, teacher_id, title, max_participants, p2p_host, p2p_port)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (meeting_id, teacher_id, title, max_participants, p2p_host, p2p_port),
        )
        self._conn.commit()

    def get_meeting(self, meeting_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_active_meetings(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM meetings WHERE status != 'ended' ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_meeting_status(self, meeting_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE meetings SET status = ? WHERE id = ?",
            (status, meeting_id),
        )
        self._conn.commit()

    def delete_meeting(self, meeting_id: str) -> None:
        self._conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Participants
    # ------------------------------------------------------------------

    def add_participant(self, meeting_id: str, user_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO meeting_participants (meeting_id, user_id) VALUES (?, ?)",
            (meeting_id, user_id),
        )
        self._conn.commit()

    def remove_participant(self, meeting_id: str, user_id: str) -> None:
        self._conn.execute(
            "DELETE FROM meeting_participants WHERE meeting_id = ? AND user_id = ?",
            (meeting_id, user_id),
        )
        self._conn.commit()

    def get_participants(self, meeting_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT u.id, u.username, u.role, mp.joined_at
               FROM meeting_participants mp
               JOIN users u ON mp.user_id = u.id
               WHERE mp.meeting_id = ?""",
            (meeting_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def participant_count(self, meeting_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM meeting_participants WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
