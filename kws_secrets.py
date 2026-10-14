"""Secret storage using Windows DPAPI (CryptProtectData).

Secrets are encrypted with the current user's Windows credentials and written
to ``%LOCALAPPDATA%\\KaliWindowsSubstitute\\secrets``. Nothing is ever written
in plain text, and nothing is ever committed to the repository.

On non-Windows platforms (which we do not ship) this falls back to an
in-process store so tests can still run. Nothing is persisted there.
"""
from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes
from pathlib import Path

import kws_paths

_IS_WINDOWS = os.name == "nt"
_MEMORY: dict[str, str] = {}


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


if _IS_WINDOWS:
    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32


def _to_blob(data: bytes) -> _Blob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _from_blob(blob: _Blob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _protect(data: bytes) -> bytes:
    blob_in = _to_blob(data)
    blob_out = _Blob()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    try:
        return _from_blob(blob_out)
    finally:
        _kernel32.LocalFree(blob_out.pbData)


def _unprotect(data: bytes) -> bytes:
    blob_in = _to_blob(data)
    blob_out = _Blob()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return _from_blob(blob_out)
    finally:
        _kernel32.LocalFree(blob_out.pbData)


def _path(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    return kws_paths.secrets_dir() / f"{safe}.bin"


def set_secret(name: str, value: str) -> None:
    if not _IS_WINDOWS:
        _MEMORY[name] = value
        return
    blob = _protect(value.encode("utf-8"))
    _path(name).write_bytes(base64.b64encode(blob))


def get_secret(name: str, default: str = "") -> str:
    if not _IS_WINDOWS:
        return _MEMORY.get(name, default)
    path = _path(name)
    if not path.exists():
        return default
    try:
        blob = base64.b64decode(path.read_bytes())
        return _unprotect(blob).decode("utf-8")
    except (OSError, ValueError):
        return default


def delete_secret(name: str) -> None:
    if not _IS_WINDOWS:
        _MEMORY.pop(name, None)
        return
    path = _path(name)
    if path.exists():
        path.unlink()


def has_secret(name: str) -> bool:
    if not _IS_WINDOWS:
        return name in _MEMORY
    return _path(name).exists()
