"""Terminal recordings for KWS.

Manages JSONL recording files for tool execution sessions.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import kws.paths as kws_paths

_RECORDINGS_DIR = kws_paths.user_data_dir() / "recordings"


def _ensure_recordings_dir() -> Path:
    _RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return _RECORDINGS_DIR


def start_recording(tool: str, argv: dict[str, Any]) -> str:
    """Start a new recording session.

    Args:
        tool: The tool being recorded.
        argv: The tool arguments.

    Returns:
        Recording ID (timestamp-based).
    """
    _ensure_recordings_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    recording_id = f"{tool}_{timestamp}"

    rec_file = _RECORDINGS_DIR / f"{recording_id}.jsonl"
    meta_file = _RECORDINGS_DIR / f"{recording_id}.meta.json"

    # Write metadata
    meta = {
        "id": recording_id,
        "tool": tool,
        "argv": argv,
        "started": datetime.now().isoformat(),
        "ended": None,
        "lines": 0,
        "size_bytes": 0,
    }
    meta_file.write_text(json.dumps(meta, indent=2))

    # Create empty recording file
    rec_file.write_text("")

    return recording_id


def append_recording(recording_id: str, line: str) -> None:
    """Append a line to an active recording.

    Args:
        recording_id: The recording ID from start_recording.
        line: The line to append (will be stored as JSON object with timestamp).
    """
    _ensure_recordings_dir()
    rec_file = _RECORDINGS_DIR / f"{recording_id}.jsonl"
    meta_file = _RECORDINGS_DIR / f"{recording_id}.meta.json"

    if not rec_file.exists():
        return

    entry = {
        "timestamp": datetime.now().isoformat(),
        "line": line,
    }
    with rec_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    # Update metadata line count
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            meta["lines"] = meta.get("lines", 0) + 1
            meta["size_bytes"] = rec_file.stat().st_size
            meta_file.write_text(json.dumps(meta, indent=2))
        except Exception:
            pass


def stop_recording(recording_id: str) -> bool:
    """Stop a recording session.

    Args:
        recording_id: The recording ID to stop.

    Returns:
        True if recording was found and stopped.
    """
    _ensure_recordings_dir()
    meta_file = _RECORDINGS_DIR / f"{recording_id}.meta.json"

    if not meta_file.exists():
        return False

    try:
        meta = json.loads(meta_file.read_text())
        meta["ended"] = datetime.now().isoformat()
        rec_file = _RECORDINGS_DIR / f"{recording_id}.jsonl"
        if rec_file.exists():
            meta["size_bytes"] = rec_file.stat().st_size
        meta_file.write_text(json.dumps(meta, indent=2))
        return True
    except Exception:
        return False


def list_recordings() -> list[dict[str, Any]]:
    """List all recordings with metadata.

    Returns:
        List of recording metadata dicts.
    """
    _ensure_recordings_dir()
    recordings = []

    for meta_file in _RECORDINGS_DIR.glob("*.meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            recordings.append(meta)
        except Exception:
            pass

    # Sort by started desc
    recordings.sort(key=lambda x: x.get("started", ""), reverse=True)
    return recordings


def load_recording(id: str) -> list[str]:
    """Load all lines from a recording.

    Args:
        id: The recording ID.

    Returns:
        List of line strings (the 'line' field from JSONL).
    """
    _ensure_recordings_dir()
    # Sanitize recording_id to prevent path traversal
    safe_id = "".join(c for c in id if c.isalnum() or c in "-_.")
    if not safe_id:
        return []
    rec_file = _RECORDINGS_DIR / f"{safe_id}.jsonl"

    if not rec_file.exists():
        return []

    lines = []
    for line in rec_file.read_text().splitlines():
        try:
            entry = json.loads(line)
            lines.append(entry.get("line", ""))
        except Exception:
            lines.append(line)
    return lines


def delete_recording(id: str) -> bool:
    """Delete a recording and its metadata.

    Args:
        id: The recording ID.

    Returns:
        True if files were deleted.
    """
    _ensure_recordings_dir()
    rec_file = _RECORDINGS_DIR / f"{id}.jsonl"
    meta_file = _RECORDINGS_DIR / f"{id}.meta.json"

    deleted = False
    if rec_file.exists():
        rec_file.unlink()
        deleted = True
    if meta_file.exists():
        meta_file.unlink()
        deleted = True
    return deleted
