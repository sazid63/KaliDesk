"""Add files to the evidence folder from the browser.

The tool forms pick their input from the evidence folder. Before this module the
only way to get a file there was to copy it in by hand, so the picker often showed
nothing useful. Uploads are streamed to disk (a disk image can be gigabytes), capped
in size, reduced to a plain file name, and never overwrite an existing file.
"""
from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import BinaryIO

from kws import paths as kws_paths

MAX_UPLOAD = 2 * 1024 * 1024 * 1024  # 2 GiB: enough for typical disk images and captures
MAX_NAME = 120
TEMP_PREFIX = ".upload-"
_BAD_CHARS = re.compile(r"[^A-Za-z0-9._()\-+=,@]")


class UploadError(ValueError):
    """A refused upload. The message is safe to show the user."""


def safe_name(raw: str) -> str:
    """Reduce a client-supplied file name to a plain name inside the evidence folder.

    Keeps only the last path component, replaces anything outside a conservative set
    of characters, and refuses names that are empty, hidden or dot-only.
    """
    if not isinstance(raw, str):
        raise UploadError("the file name must be text")
    base = raw.replace("\\", "/").rsplit("/", 1)[-1].strip()
    base = _BAD_CHARS.sub("_", base).lstrip(".").strip(" ")
    if not base or base in (".", ".."):
        raise UploadError("choose a file with a usable name")
    if len(base) > MAX_NAME:
        stem, dot, ext = base.rpartition(".")
        keep = MAX_NAME - (len(ext) + 1 if dot else 0)
        base = stem[:keep] + (dot + ext if dot else "")
    return base


def _unique_path(folder: Path, name: str) -> Path:
    """A path for ``name`` in ``folder`` that does not exist yet ("x (2).txt", ...)."""
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    candidate = folder / name
    counter = 2
    while candidate.exists():
        suffix = f" ({counter})"
        candidate = folder / (f"{stem}{suffix}.{ext}" if ext else f"{name}{suffix}")
        counter += 1
    return candidate


def store(stream: BinaryIO, raw_name: str, limit: int = MAX_UPLOAD) -> str:
    """Write the upload to the evidence folder and return the name it was saved under.

    Raises UploadError for a bad name or a file over ``limit``. Nothing is left behind
    on failure: the partial file is removed.
    """
    name = safe_name(raw_name)
    folder = kws_paths.evidence_dir()
    temp = folder / f"{TEMP_PREFIX}{secrets.token_hex(8)}"
    total = 0
    try:
        with open(temp, "xb") as handle:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise UploadError(f"that file is larger than {limit // (1024 * 1024)} MB")
                handle.write(chunk)
        if total == 0:
            raise UploadError("the file is empty")
        final = _unique_path(folder, name)
        os.replace(temp, final)
        return final.name
    finally:
        if temp.exists():
            temp.unlink()


def is_listed(path: Path) -> bool:
    """Whether a file in the evidence folder should be offered to the tool forms."""
    return path.is_file() and not path.is_symlink() and not path.name.startswith(".")
