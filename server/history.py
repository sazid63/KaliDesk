"""Run history tracking for KWS tool executions.

Provides recording, listing, and deletion of tool execution history.
Uses the existing DB connection pattern from server.db.
"""
from __future__ import annotations

import json
from typing import Any

import server.db as db


def record_run(tool: str, target: str, argv: dict[str, Any],
               rc: int, duration_ms: float, output_preview: str,
               success: bool) -> int:
    """Record a tool execution into the run_history table.

    Trims the table to the last 500 rows after insert.
    Returns the inserted row id.
    """
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO run_history "
            "(tool, target, argv, rc, duration_ms, output_preview, success, created) "
            "VALUES (?,?,?,?,?,?,?, datetime('now'))",
            (tool, target, json.dumps(argv), rc, duration_ms, output_preview, success),
        )
        run_id = int(cur.lastrowid or 0)

    # Trim to last 500 rows
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM run_history WHERE id "
            "NOT IN (SELECT id FROM run_history ORDER BY id DESC LIMIT 500)"
        )

    return run_id


def list_history(limit: int = 100, tool: str | None = None,
                 success: bool | None = None) -> list[dict[str, Any]]:
    """List run_history entries with optional filtering.

    Args:
        limit: Maximum number of entries to return.
        tool: Optional filter by tool id.
        success: Optional filter by success flag (True/None for all).

    Returns:
        List of dicts with run history rows.
    """
    with db.connect() as conn:
        if tool is not None and success is not None:
            rows = conn.execute(
                "SELECT * FROM run_history "
                "WHERE tool = ? AND success = ? "
                "ORDER BY id DESC LIMIT ?",
                (tool, success, limit),
            ).fetchall()
        elif tool is not None:
            rows = conn.execute(
                "SELECT * FROM run_history WHERE tool = ? ORDER BY id DESC LIMIT ?",
                (tool, limit),
            ).fetchall()
        elif success is not None:
            rows = conn.execute(
                "SELECT * FROM run_history WHERE success = ? ORDER BY id DESC LIMIT ?",
                (success, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM run_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def delete_history(id: int) -> bool:
    """Delete a single run_history entry by id."""
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM run_history WHERE id = ?", (id,))
        return cur.rowcount > 0


def clear_history() -> bool:
    """Delete all run_history entries."""
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM run_history")
        return cur.rowcount > 0