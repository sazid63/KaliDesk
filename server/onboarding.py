"""Onboarding wizard for KWS.

Manages first-run onboarding flow with steps for WSL, runtime, AI setup.
"""
from __future__ import annotations

from typing import Any

import server.db as db

_ONBOARDING_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


#: Onboarding step definitions
ONBOARDING_STEPS = [
    {
        "id": "welcome",
        "title": "Welcome to Kali Desktop Substitute",
        "description": "A Kali Linux toolset running natively on Windows via WSL2.",
        "check_fn": lambda: True,
    },
    {
        "id": "wsl",
        "title": "WSL2 & KaliSubstitute",
        "description": "Verify WSL2 is installed and the KaliSubstitute distro is running.",
        "check_fn": lambda: True,  # Runtime check in frontend
    },
    {
        "id": "runtime",
        "title": "Agent Runtime",
        "description": "Start the KWS agent inside WSL2 for tool execution.",
        "check_fn": lambda: True,  # Runtime check in frontend
    },
    {
        "id": "ai",
        "title": "AI Provider Setup",
        "description": (
            "Configure an AI provider (OpenAI, Anthropic, Ollama, etc.)"
            " for the cybersecurity chat."
        ),
        "check_fn": lambda: True,  # Runtime check in frontend
    },
]


def _init_settings_table() -> None:
    with db.connect() as conn:
        conn.executescript(_ONBOARDING_SCHEMA)


def finish_onboarding() -> bool:
    """Mark onboarding as complete.

    Returns:
        True if successfully marked complete.
    """
    _init_settings_table()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('onboarding_complete', '1') "
            "ON CONFLICT(key) DO UPDATE SET value='1'",
        )
    return True


def is_onboarding_needed() -> bool:
    """Check if onboarding is needed (not completed).

    Returns:
        True if onboarding should be shown.
    """
    _init_settings_table()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'onboarding_complete'"
        ).fetchone()
        return row is None or row["value"] != "1"


def onboarding_steps() -> list[dict[str, Any]]:
    """Get the list of onboarding step definitions.

    Returns:
        List of step dicts with id, title, description.
    """
    return [
        {"id": s["id"], "title": s["title"], "description": s["description"]}
        for s in ONBOARDING_STEPS
    ]
