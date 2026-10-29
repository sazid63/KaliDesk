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
CREATE TABLE IF NOT EXISTS conversations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    created   TEXT NOT NULL,
    tool      TEXT NOT NULL DEFAULT '',
    target    TEXT NOT NULL DEFAULT '',
    role      TEXT NOT NULL DEFAULT 'user',
    content   TEXT NOT NULL DEFAULT '',
    encrypted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mcp_servers (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,
    type      TEXT NOT NULL,
    config    TEXT NOT NULL DEFAULT '{}',
    enabled   INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS skills (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    category  TEXT NOT NULL DEFAULT 'general',
    enabled   INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS scan_profiles (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    tool      TEXT NOT NULL,
    config    TEXT NOT NULL DEFAULT '{}',
    created   TEXT NOT NULL
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
CREATE TABLE IF NOT EXISTS workspaces (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS local_models (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    path          TEXT NOT NULL,
    size_mb       REAL NOT NULL DEFAULT 0,
    quantization  TEXT NOT NULL DEFAULT '',
    capabilities  TEXT NOT NULL DEFAULT 'chat',
    loaded        INTEGER NOT NULL DEFAULT 0
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
