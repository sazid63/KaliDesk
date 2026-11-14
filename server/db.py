"""SQLite-backed findings, audit trail and settings.

One small database in the user's profile. No ORM, no network.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

import kws.paths as kws_paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    created   TEXT NOT NULL,
    tool      TEXT NOT NULL,
    target    TEXT NOT NULL DEFAULT '',
    severity  TEXT NOT NULL DEFAULT 'info',
    title     TEXT NOT NULL DEFAULT '',
    detail    TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    created   TEXT NOT NULL,
    actor     TEXT NOT NULL DEFAULT 'user',
    action    TEXT NOT NULL,
    target    TEXT NOT NULL DEFAULT '',
    result    TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created       TEXT NOT NULL,
    tool          TEXT NOT NULL,
    target        TEXT NOT NULL DEFAULT '',
    argv          TEXT NOT NULL DEFAULT '[]',
    rc            INTEGER NOT NULL DEFAULT 0,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    output_preview TEXT NOT NULL DEFAULT '',
    success       INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS achievements (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    key       TEXT NOT NULL UNIQUE,
    name      TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    unlocked  INTEGER NOT NULL DEFAULT 0,
    unlocked_at TEXT
);
CREATE TABLE IF NOT EXISTS notebook (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    created   TEXT NOT NULL,
    type      TEXT NOT NULL DEFAULT 'note',
    content   TEXT NOT NULL DEFAULT '',
    tags      TEXT NOT NULL DEFAULT '[]'
);
"""


def _db_path() -> str:
    return str(kws_paths.db_path())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Connection(sqlite3.Connection):
    """``with connect() as conn`` commits (or rolls back) AND closes the connection.

    Plain sqlite3 connections only commit on ``with`` exit and stay open, which leaks a
    file handle on every call.
    """

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or _db_path(), factory=_Connection, timeout=10)
    conn.row_factory = sqlite3.Row
    # Per-connection settings (they are not stored in the database file).
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(db_path: str | None = None) -> None:
    with connect(db_path) as conn:
        # WAL lets the UI read while a job records its result; it persists in the file.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)


def audit(actor: str, action: str, target: str = "", result: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit (created, actor, action, target, result) VALUES (?,?,?,?,?)",
            (_now(), actor, action, target or "", result or ""),
        )


def add_finding(tool: str, target: str, severity: str, title: str, detail: str = "") -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO findings (created, tool, target, severity, title, detail) "
            "VALUES (?,?,?,?,?,?)",
            (_now(), tool, target or "", severity or "info", title, detail or ""),
        )
        return int(cur.lastrowid or 0)


def delete_finding(fid: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM findings WHERE id = ?", (fid,))
        return cur.rowcount > 0


def findings(limit: int | None = 200) -> list[dict[str, Any]]:
    """Newest findings first. ``limit=None`` returns every finding (used by the report)."""
    with connect() as conn:
        if limit is None:
            rows = conn.execute("SELECT * FROM findings ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM findings ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def audits(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
