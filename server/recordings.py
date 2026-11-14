"""Run transcripts ("recordings").

Every finished tool run saves its full output here automatically, so a result is still
there after the output panel is closed (History only keeps a short preview). Each
transcript is two small files in ``<user data>/recordings``:

    <id>.meta.json   tool, target, command, state, exit code, timing, size
    <id>.log         the output text

Ids look like ``nmap_20261110_140620_ab12cd34`` and are validated strictly, so an id
taken from a URL can never reach outside the folder.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kws.paths as kws_paths

MAX_KEPT = 200
MAX_LOG_BYTES = 1024 * 1024
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}_\d{8}_\d{6}_[0-9a-f]{8}$")


def _dir() -> Path:
    return kws_paths.sub_dir("recordings")


_SECRET_FLAG = re.compile(
    r"^-{1,2}(password|passwords|passwd|passphrase|hash|hashes|token|secret)$", re.IGNORECASE
)


def redact_argv(argv: list[str]) -> list[str]:
    """Blank the value of a secret-bearing flag (``--password x`` or ``--password=x``).

    The same secret fields that History hides; the transcript keeps the rest of the command.
    """
    out: list[str] = []
    redact_next = False
    for arg in argv:
        if redact_next:
            out.append("[redacted]")
            redact_next = False
            continue
        flag, sep, _value = arg.partition("=")
        if sep and _SECRET_FLAG.match(flag):
            out.append(f"{flag}=[redacted]")
            continue
        out.append(arg)
        redact_next = bool(_SECRET_FLAG.match(arg))
    return out


def valid_id(recording_id: str) -> bool:
    return isinstance(recording_id, str) and bool(_ID_RE.match(recording_id))


def _paths(recording_id: str) -> tuple[Path, Path]:
    return _dir() / f"{recording_id}.meta.json", _dir() / f"{recording_id}.log"


def save_transcript(
    tool: str,
    target: str,
    argv: list[str] | None,
    output: str,
    rc: int | None,
    state: str,
    elapsed: float,
) -> str:
    """Store one finished run and return its id."""
    safe_tool = re.sub(r"[^a-z0-9-]", "-", (tool or "run").lower()).strip("-")[:40] or "run"
    now = datetime.now(timezone.utc)
    recording_id = f"{safe_tool}_{now:%Y%m%d_%H%M%S}_{secrets.token_hex(4)}"
    meta_path, log_path = _paths(recording_id)
    data = output.encode("utf-8", errors="replace")[:MAX_LOG_BYTES]
    log_path.write_bytes(data)
    meta = {
        "id": recording_id,
        "tool": tool,
        "target": target or "",
        "argv": redact_argv(list(argv or [])),
        "state": state,
        "rc": rc,
        "started": now.isoformat(timespec="seconds"),
        "duration_ms": int(elapsed * 1000),
        "size_bytes": len(data),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _prune()
    return recording_id


def _prune() -> None:
    metas = sorted(_dir().glob("*.meta.json"), key=lambda p: p.name.split("_", 1)[-1])
    for meta in metas[: max(0, len(metas) - MAX_KEPT)]:
        delete_recording(meta.name.removesuffix(".meta.json"))


def list_recordings(limit: int = 100) -> list[dict[str, Any]]:
    rows = []
    for meta_file in _dir().glob("*.meta.json"):
        try:
            rows.append(json.loads(meta_file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    rows.sort(key=lambda m: m.get("started", ""), reverse=True)
    return rows[: max(1, min(int(limit), 500))]


def load_recording(recording_id: str) -> dict[str, Any] | None:
    if not valid_id(recording_id):
        return None
    meta_path, log_path = _paths(recording_id)
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    except (OSError, ValueError):
        return None
    return {"meta": meta, "text": text}


def delete_recording(recording_id: str) -> bool:
    if not valid_id(recording_id):
        return False
    deleted = False
    for path in _paths(recording_id):
        if path.exists():
            path.unlink()
            deleted = True
    return deleted
