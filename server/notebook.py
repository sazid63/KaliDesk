"""OSINT Notebook for KWS.

Stores and manages OSINT entries (URLs, IPs, findings, notes) with tags and search.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import server.db as db

# The notebook table is created in server/db.py.
MAX_CONTENT = 20000


def add_entry(type: str, content: str, tags: list[str] | None = None) -> int:
    """Add a new notebook entry.

    Args:
        type: Entry type - 'url', 'ip', 'finding', or 'note'.
        content: The entry content.
        tags: Optional list of tags.

    Returns:
        The inserted row ID.
    """
    if not isinstance(type, str) or not isinstance(content, str):
        raise ValueError("type and content must be text")
    if len(content) > MAX_CONTENT:
        raise ValueError(f"an entry can be at most {MAX_CONTENT} characters")
    valid_types = {"url", "ip", "finding", "note"}
    if type not in valid_types:
        type = "note"

    # Tags must be strings: export joins them, so a number or object would raise TypeError.
    clean_tags = [str(t) for t in tags] if isinstance(tags, list) else []
    tag_json = json.dumps(clean_tags)

    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO notebook (created, type, content, tags) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), type, content, tag_json),
        )
        return int(cur.lastrowid or 0)


def list_entries(
    type: str | None = None,
    tags: list[str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List notebook entries with optional filtering.

    Args:
        type: Filter by entry type.
        tags: Filter by tags (matches if entry has ANY of the given tags).
        limit: Maximum entries to return.

    Returns:
        List of entry dicts.
    """
    with db.connect() as conn:
        if type is not None and tags is not None and len(tags) > 0:
            # Filter by type and tags
            tag_conditions = " OR ".join(["tags LIKE ?"] * len(tags))
            params = [type] + [f"%{t}%" for t in tags] + [limit]
            query = (
                "SELECT * FROM notebook WHERE type = ? AND ("
                f"{tag_conditions}) ORDER BY created DESC LIMIT ?"
            )
            rows = conn.execute(query, params).fetchall()
        elif type is not None:
            rows = conn.execute(
                "SELECT * FROM notebook WHERE type = ? ORDER BY created DESC LIMIT ?",
                (type, limit),
            ).fetchall()
        elif tags is not None and len(tags) > 0:
            tag_conditions = " OR ".join(["tags LIKE ?"] * len(tags))
            params = [f"%{t}%" for t in tags] + [limit]
            query = f"SELECT * FROM notebook WHERE ({tag_conditions}) ORDER BY created DESC LIMIT ?"
            rows = conn.execute(query, params).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notebook ORDER BY created DESC LIMIT ?",
                (limit,),
            ).fetchall()

    result = []
    for row in rows:
        entry = dict(row)
        entry["tags"] = json.loads(entry["tags"])
        result.append(entry)
    return result


def delete_entry(id: int) -> bool:
    """Delete a notebook entry by ID."""
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM notebook WHERE id = ?", (id,))
        return cur.rowcount > 0


def export_notebook() -> str:
    """Export all notebook entries as markdown.

    Returns:
        Markdown string with all entries.
    """
    entries = list_entries(limit=10000)  # All entries

    lines = ["# OSINT Notebook Export", "", f"Generated: {datetime.now().isoformat()}", ""]

    for entry in entries:
        lines.append(f"## {entry['type'].upper()} - {entry['created']}")
        if entry["tags"]:
            lines.append(f"**Tags:** {', '.join(entry['tags'])}")
        lines.append("")
        lines.append(entry["content"])
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def search_notebook(query: str) -> list[dict[str, Any]]:
    """Search notebook entries by content.

    Args:
        query: Search query (case-insensitive, matches content).

    Returns:
        List of matching entry dicts.
    """
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM notebook WHERE content LIKE ? ORDER BY created DESC",
            (f"%{query}%",),
        ).fetchall()

    result = []
    for row in rows:
        entry = dict(row)
        entry["tags"] = json.loads(entry["tags"])
        result.append(entry)
    return result
