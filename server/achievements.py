"""Achievement system for KWS.

Provides achievement definitions, checking conditions, and unlocking tracking.
"""
from __future__ import annotations

from typing import Any

import server.db as db

#: Achievement definitions: key -> {name, description, condition_fn}
#: condition_fn(tool, target, rc, duration_ms) -> bool
ACHIEVEMENTS: dict[str, dict[str, Any]] = {
    "first_run": {
        "name": "First Blood",
        "description": "Run your first tool",
        "condition_fn": lambda tool, target, rc, duration_ms: True,
    },
    "port_scanner": {
        "name": "Port Scanner",
        "description": "Run nmap 5 times",
        "condition_fn": lambda tool, target, rc, duration_ms: tool == "nmap",
    },
    "web_scanner": {
        "name": "Web Scout",
        "description": "Run nikto or nuclei 5 times",
        "condition_fn": lambda tool, target, rc, duration_ms: tool in ("nikto", "nuclei"),
    },
    "password_cracker": {
        "name": "Hash Breaker",
        "description": "Run john or hashcat 3 times",
        "condition_fn": lambda tool, target, rc, duration_ms: tool in ("john", "hashcat"),
    },
    "vuln_hunter": {
        "name": "Vulnerability Hunter",
        "description": "Run sqlmap or nuclei with critical/high findings",
        "condition_fn": lambda tool, target, rc, duration_ms: tool in ("sqlmap", "nuclei")
            and rc == 0,
    },
    "forensics_expert": {
        "name": "Forensics Expert",
        "description": "Run volatility, sleuthkit, or foremost",
        "condition_fn": lambda tool, target, rc, duration_ms: tool in (
            "volatility", "sleuthkit", "foremost"),
    },
    "wireless_warrior": {
        "name": "Wireless Warrior",
        "description": "Run aircrack-ng, reaver, or wifite",
        "condition_fn": lambda tool, target, rc, duration_ms: tool in (
            "aircrack-ng", "reaver", "wifite"),
    },
    "osint_master": {
        "name": "OSINT Master",
        "description": "Run theharvester, amass, or dnsrecon 3 times",
        "condition_fn": lambda tool, target, rc, duration_ms: tool in (
            "theharvester", "amass", "dnsrecon"),
    },
    "speed_demon": {
        "name": "Speed Demon",
        "description": "Complete a tool run in under 1 second",
        "condition_fn": lambda tool, target, rc, duration_ms: duration_ms < 1000 and rc == 0,
    },
    "persistent": {
        "name": "Persistent",
        "description": "Run 10 different tools",
        "condition_fn": lambda tool, target, rc, duration_ms: True,
    },
}


def check_achievements(tool: str, target: str, rc: int, duration_ms: float) -> list[str]:
    """Check which achievements are triggered by a tool run.

    Args:
        tool: The tool ID that was run.
        target: The target of the run.
        rc: Return code (0 = success).
        duration_ms: Duration in milliseconds.

    Returns:
        List of achievement keys that were triggered.
    """
    triggered = []
    for key, ach in ACHIEVEMENTS.items():
        if key == "first_run" or key == "persistent":
            continue
        try:
            if ach["condition_fn"](tool, target, rc, duration_ms):
                triggered.append(key)
        except Exception:
            pass
    return triggered


def unlock_achievement(key: str) -> bool:
    """Unlock an achievement if not already unlocked.

    Args:
        key: Achievement key from ACHIEVEMENTS.

    Returns:
        True if newly unlocked, False if already unlocked or invalid key.
    """
    if key not in ACHIEVEMENTS:
        return False

    with db.connect() as conn:
        row = conn.execute(
            "SELECT unlocked FROM achievements WHERE key = ?", (key,)
        ).fetchone()
        if row and row["unlocked"]:
            return False

        conn.execute(
            "INSERT INTO achievements (key, name, description, unlocked, unlocked_at) "
            "VALUES (?,?,?,1,datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET unlocked=1, unlocked_at=datetime('now')",
            (key, ACHIEVEMENTS[key]["name"], ACHIEVEMENTS[key]["description"]),
        )
    return True


def list_achievements() -> list[dict[str, Any]]:
    """List all achievements with their unlock status.

    Returns:
        List of dicts with key, name, description, unlocked, unlocked_at.
    """
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT key, name, description, unlocked, unlocked_at FROM achievements ORDER BY key"
        ).fetchall()

    result = []
    for row in rows:
        key = row["key"]
        ach = ACHIEVEMENTS.get(key, {})
        result.append({
            "key": key,
            "name": row["name"] or ach.get("name", key),
            "description": row["description"] or ach.get("description", ""),
            "unlocked": bool(row["unlocked"]),
            "unlocked_at": row["unlocked_at"],
        })

    db_keys = {r["key"] for r in result}
    for key, ach in ACHIEVEMENTS.items():
        if key not in db_keys:
            result.append({
                "key": key,
                "name": ach["name"],
                "description": ach["description"],
                "unlocked": False,
                "unlocked_at": None,
            })

    return result
