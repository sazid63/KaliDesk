"""Application paths.

Works both when running from source and when frozen by PyInstaller.
Nothing here writes secrets: see ``app/secrets.py`` for that.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

USER_DIR_NAME = "KaliWindowsSubstitute"


def resource_root() -> Path:
    """Directory that holds ``server/``, ``ui/``, ``catalog/`` and ``runtime/``."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


def resource(*parts: str) -> str:
    """Absolute path to a bundled resource."""
    return str(Path(resource_root(), *parts))


def user_data_dir() -> Path:
    """Per-user writable directory (LOCALAPPDATA on Windows)."""
    base = os.environ.get("KWS_DATA_DIR") or os.environ.get("LOCALAPPDATA") \
        or os.path.expanduser("~")
    path = Path(base) / USER_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def sub_dir(name: str) -> Path:
    path = user_data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def evidence_dir() -> Path:
    return sub_dir("evidence")


def work_dir() -> Path:
    return sub_dir("work")


def secrets_dir() -> Path:
    return sub_dir("secrets")


def db_path() -> Path:
    return user_data_dir() / "toolkit.sqlite3"


def to_wsl_path(path: str | Path) -> str:
    """Best-effort conversion of a Windows path to its WSL ``/mnt`` form."""
    p = str(path).replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:]
        if not rest.startswith("/"):
            rest = "/" + rest
        return f"/mnt/{drive}{rest}"
    return p
