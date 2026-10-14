"""SQLite-backed findings, audit trail and settings.

One small database in the user's profile. No ORM, no network.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

import kws_paths

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
"""


def _db_path() -> str:
    return str(kws_paths.user_data_dir() / "kws.sqlite3")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None) -> None:
    with sqlite3.connect(db_path or _db_path()) as conn:
        conn.executescript(_SCHEMA)


def audit(actor: str, action: str, target: str = "", result: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit (created, actor, action, target, result) VALUES (?,?,?,?,?)",
            (_now(), actor, action, target or "", result or ""),
        )


def add_finding(tool: str, target: str, severity: str, title: str,
                detail: str = "") -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO findings (created, tool, target, severity, title, detail) "
            "VALUES (?,?,?,?,?,?)",
            (_now(), tool, target or "", severity or "info", title, detail or ""),
        )
        return int(cur.lastrowid or 0)


def findings(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM findings ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def audits(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
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
