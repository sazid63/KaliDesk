"""Achievements: small goals that reward trying the toolkit.

Progress is computed from the run history, so it can't be faked and survives a restart.
``evaluate()`` runs after every finished tool run and unlocks whatever has been reached;
there is no way to unlock one by clicking.
"""

from __future__ import annotations

from typing import Any

import server.db as db

# key -> definition. ``tools`` limits the count to those tool ids (empty = any tool);
# ``goal`` is how many runs are needed; ``ok_only`` counts only successful runs;
# ``distinct`` counts different tools instead of runs; ``fast`` needs a run under a second.
ACHIEVEMENTS: dict[str, dict[str, Any]] = {
    "first_run": {
        "name": "First Blood", "description": "Run your first tool", "goal": 1,
    },
    "port_scanner": {
        "name": "Port Scanner", "description": "Run nmap or masscan 5 times", "goal": 5,
        "tools": ("nmap", "masscan"),
    },
    "web_scout": {
        "name": "Web Scout", "description": "Run 5 web scans (nikto, nuclei, whatweb, wapiti)",
        "goal": 5, "tools": ("nikto", "nuclei", "whatweb", "wapiti", "gobuster", "ffuf"),
    },
    "hash_breaker": {
        "name": "Hash Breaker", "description": "Run john or hashcat 3 times", "goal": 3,
        "tools": ("john", "hashcat"),
    },
    "vuln_hunter": {
        "name": "Vulnerability Hunter", "description": "Finish a sqlmap or nuclei run successfully",
        "goal": 1, "tools": ("sqlmap", "nuclei"), "ok_only": True,
    },
    "forensics_expert": {
        "name": "Forensics Expert", "description": "Analyse evidence with a forensics tool",
        "goal": 1,
        "tools": ("volatility3", "sleuthkit", "foremost", "photorec", "binwalk", "exiftool",
                  "steghide"),
    },
    "wireless_warrior": {
        "name": "Wireless Warrior", "description": "Run aircrack-ng, hcxtools or wifite",
        "goal": 1, "tools": ("aircrack-ng", "hcxtools", "wifite"),
    },
    "osint_master": {
        "name": "OSINT Master", "description": "Run theharvester, dnsrecon, dig or whois 3 times",
        "goal": 3, "tools": ("theharvester", "dnsrecon", "dns", "whois"),
    },
    "speed_demon": {
        "name": "Speed Demon", "description": "Finish a run successfully in under 1 second",
        "goal": 1, "ok_only": True, "fast": True,
    },
    "persistent": {
        "name": "Persistent", "description": "Run 10 different tools", "goal": 10,
        "distinct": True,
    },
}


def _progress(key: str) -> int:
    ach = ACHIEVEMENTS[key]
    clauses, params = [], []
    tools = ach.get("tools")
    if tools:
        clauses.append(f"tool IN ({','.join('?' * len(tools))})")
        params += list(tools)
    if ach.get("ok_only"):
        clauses.append("success = 1")
    if ach.get("fast"):
        clauses.append("duration_ms < 1000")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    what = "COUNT(DISTINCT tool)" if ach.get("distinct") else "COUNT(*)"
    with db.connect() as conn:
        return int(conn.execute(f"SELECT {what} FROM run_history{where}", params).fetchone()[0])


def _unlocked_keys() -> set[str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT key FROM achievements WHERE unlocked = 1").fetchall()
    return {r["key"] for r in rows}


def _unlock(key: str) -> None:
    ach = ACHIEVEMENTS[key]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO achievements (key, name, description, unlocked, unlocked_at) "
            "VALUES (?,?,?,1,datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET unlocked=1, unlocked_at=datetime('now')",
            (key, ach["name"], ach["description"]),
        )


def evaluate() -> list[str]:
    """Unlock everything whose goal has been reached. Returns the names newly unlocked."""
    done = _unlocked_keys()
    newly = []
    for key, ach in ACHIEVEMENTS.items():
        if key not in done and _progress(key) >= ach["goal"]:
            _unlock(key)
            newly.append(ach["name"])
    return newly


def list_achievements() -> list[dict[str, Any]]:
    done = _unlocked_keys()
    with db.connect() as conn:
        when = {r["key"]: r["unlocked_at"] for r in conn.execute(
            "SELECT key, unlocked_at FROM achievements WHERE unlocked = 1")}
    out = []
    for key, ach in ACHIEVEMENTS.items():
        unlocked = key in done
        out.append({
            "key": key,
            "name": ach["name"],
            "description": ach["description"],
            "unlocked": unlocked,
            "unlocked_at": when.get(key),
            "goal": ach["goal"],
            "progress": ach["goal"] if unlocked else min(_progress(key), ach["goal"]),
        })
    return out
