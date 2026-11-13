"""Back up and restore your data (replaces the old "portable mode").

A backup is one zip with your findings, history and settings (the SQLite database), the
evidence folder and the run transcripts. It deliberately leaves out:

* secrets: API keys are protected with Windows DPAPI for *this* user on *this* PC, so a
  copy could not be decrypted elsewhere anyway, and a backup should never contain keys;
* the runtime (the WSL virtual disk) and downloaded images: they are rebuilt with
  *Set up runtime*.

Restoring is strict: only the three known locations are accepted, names are checked for
path tricks, links are refused, sizes are capped, and the current database is kept as a
``.before-restore`` copy.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kws.paths as kws_paths
from kws.__about__ import __version__

DB_NAME = "kws.sqlite3"
FOLDERS = ("evidence", "recordings")
MAX_ZIP = 500 * 1024 * 1024
MAX_UNPACKED = 2 * 1024 * 1024 * 1024
MAX_FILES = 20000


def _snapshot_db(dest: Path) -> None:
    """A consistent copy of the live database (safe while the app is writing to it)."""
    source = sqlite3.connect(str(kws_paths.db_path()))
    target = sqlite3.connect(str(dest))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def export_zip() -> bytes:
    root = kws_paths.user_data_dir()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps({
            "app": "kali-windows-substitute", "version": __version__,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }))
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / DB_NAME
            _snapshot_db(snap)
            bundle.write(snap, DB_NAME)
        for folder in FOLDERS:
            base = root / folder
            for path in sorted(base.rglob("*")) if base.exists() else []:
                if path.is_file() and not path.is_symlink():
                    bundle.write(path, f"{folder}/{path.relative_to(base).as_posix()}")
    return buffer.getvalue()


def _safe_member(name: str) -> bool:
    if name in ("manifest.json", DB_NAME):
        return True
    parts = name.split("/")
    return (
        len(parts) >= 2 and parts[0] in FOLDERS and all(p and p not in (".", "..") for p in parts)
        and "\\" not in name and ":" not in name and not name.startswith("/")
    )


def import_zip(data: bytes) -> dict[str, Any]:
    """Restore a backup. Returns {"ok": bool, "message": str}; never raises on bad input."""
    if len(data) > MAX_ZIP:
        return {"ok": False, "message": "that file is too large to be a backup"}
    try:
        bundle = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return {"ok": False, "message": "that is not a zip file"}
    infos = [i for i in bundle.infolist() if not i.is_dir()]
    names = {i.filename for i in infos}
    if DB_NAME not in names or "manifest.json" not in names:
        return {"ok": False, "message": "that zip is not a backup from this app"}
    if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_UNPACKED:
        return {"ok": False, "message": "the backup is larger than allowed"}
    for info in infos:
        mode = info.external_attr >> 16
        if not _safe_member(info.filename) or stat.S_ISLNK(mode):
            return {"ok": False, "message": f"the backup contains a file that is not allowed: "
                                            f"{info.filename[:80]}"}
    try:
        manifest = json.loads(bundle.read("manifest.json"))
    except ValueError:
        manifest = {}
    if manifest.get("app") != "kali-windows-substitute":
        return {"ok": False, "message": "that zip is not a backup from this app"}

    root = kws_paths.user_data_dir()
    db_path = kws_paths.db_path()
    try:
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            # Stage everything first; nothing in the live data changes until all of it is ready.
            stage = Path(tmp) / "stage"
            staged_db = stage / DB_NAME
            stage.mkdir()
            staged_db.write_bytes(bundle.read(DB_NAME))
            if not _database_ok(staged_db):
                return {"ok": False, "message": "the database inside the backup is damaged"}
            _keep_live_ai_settings(staged_db, db_path)  # sqlite3.Error is handled below

            staged_files: list[tuple[Path, Path]] = []
            for index, info in enumerate(infos):
                if info.filename in ("manifest.json", DB_NAME):
                    continue
                dest = (root / info.filename).resolve()
                dest.relative_to(root.resolve())  # raises if it would land outside
                temp = stage / f"file-{index}"
                temp.write_bytes(bundle.read(info))
                staged_files.append((temp, dest))

            for temp, dest in staged_files:
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(temp, dest)
            if db_path.exists():
                os.replace(db_path, db_path.with_name(DB_NAME + ".before-restore"))
            for suffix in ("-wal", "-shm"):
                stale = Path(str(db_path) + suffix)
                if stale.exists():
                    stale.unlink()
            os.replace(staged_db, db_path)
    except sqlite3.Error:
        return {"ok": False, "message": "the database inside the backup is damaged"}
    except OSError as exc:
        return {"ok": False, "message": f"could not write the restored files: {exc}"}
    return {"ok": True, "message": f"Restored {len(infos) - 2} files and the database "
                                   "(the previous database was kept as .before-restore)."}


def _database_ok(path: Path) -> bool:
    """True if ``path`` is a readable SQLite database."""
    check = sqlite3.connect(str(path))
    try:
        check.execute("PRAGMA schema_version").fetchone()
        check.execute("SELECT count(*) FROM sqlite_master").fetchone()
        check.execute("SELECT count(*) FROM settings").fetchone()
        return True
    except sqlite3.DatabaseError:
        return False
    finally:
        check.close()


def _keep_live_ai_settings(staged_db: Path, live_db: Path) -> None:
    """Replace the ai_* settings in the staged database with this PC's current ones.

    AI provider settings and the (DPAPI-protected) key are per machine and per user, so a
    backup must never change them. Rows are copied from the live database when it exists.
    """
    live: list[tuple[str, str]] = []
    if live_db.exists():
        try:
            conn = sqlite3.connect(str(live_db))
            try:
                live = conn.execute(
                    "SELECT key, value FROM settings WHERE key LIKE 'ai\\_%' ESCAPE '\\'"
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            live = []
    conn = sqlite3.connect(str(staged_db))
    try:
        conn.execute("DELETE FROM settings WHERE key LIKE 'ai\\_%' ESCAPE '\\'")
        conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", live)
        conn.commit()
    finally:
        conn.close()
