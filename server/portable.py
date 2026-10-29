"""Portable mode management for KaliDesk.

Handles switching between installed mode and portable USB mode.
Move configuration, secrets, and user data to a USB drive.
"""
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

import server.security as security

# Blueprint
portable_bp = Blueprint("portable", __name__)

# Default user data directory (in DSH home)
DEFAULT_USER_DATA_DIR = Path(os.getenv("LOCALAPPDATA", "")) / "KaliWindowsSubstitute"
DEFAULT_CONFIG_DIR = DEFAULT_USER_DATA_DIR / "config"
DEFAULT_DATA_DIR = DEFAULT_USER_DATA_DIR / "data"
DEFAULT_SECRETS_DIR = DEFAULT_USER_DATA_DIR / "secrets"
DEFAULT_KWS_SECRETS_DIR = DEFAULT_USER_DATA_DIR / "kws_secrets"

# Portable mode marker file
PORTABLE_MARKER = "kws_portable.json"


@portable_bp.get("/drives")
@security.require_auth
def api_portable_drives():
    """List available USB/removable drives."""
    drives = []

    if sys.platform == "win32":
        try:
            import ctypes
            import string

            for letter in string.ascii_uppercase:
                drive = f"{letter}:"
                if ctypes.windll.kernel32.GetDriveTypeW(drive) == 2:  # DRIVE_REMOVABLE
                    try:
                        import psutil

                        usage = psutil.disk_usage(drive)
                        drives.append({
                            "path": drive,
                            "label": f"Drive {letter}",
                            "total_gb": round(usage.total / (1024**3), 1),
                            "free_gb": round(usage.free / (1024**3), 1),
                            "filesystem": "",
                        })
                    except Exception:
                        pass
        except Exception:
            pass
    else:
        # Linux - check /media, /mnt
        try:
            import psutil

            for base in ["/media", "/mnt"]:
                if os.path.exists(base):
                    for entry in os.listdir(base):
                        path = os.path.join(base, entry)
                        if os.path.ismount(path):
                            try:
                                usage = psutil.disk_usage(path)
                                drives.append({
                                    "path": path,
                                    "label": entry,
                                    "total_gb": round(usage.total / (1024**3), 1),
                                    "free_gb": round(usage.free / (1024**3), 1),
                                    "filesystem": "",
                                })
                            except Exception:
                                pass
        except Exception:
            pass

    return jsonify({"drives": drives})


@portable_bp.post("/switch")
@security.require_auth
@security.require_csrf
def api_portable_switch():
    """Switch to portable mode on selected USB drive."""
    data = request.get_json(silent=True) or {}
    path = str(data.get("path", "")).strip()

    if not path:
        return jsonify({"error": "Drive path required"}), 400

    if not os.path.exists(path):
        return jsonify({"error": "Drive not found"}), 400

    try:
        portable_root = Path(path) / "KaliWindowsSubstitute"
        portable_root.mkdir(parents=True, exist_ok=True)

        # Create portable marker
        marker = portable_root / PORTABLE_MARKER
        marker.write_text(json.dumps({
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "original_data_dir": str(DEFAULT_USER_DATA_DIR)
        }))

        # Move directories
        dirs_to_move = [
            ("config", DEFAULT_CONFIG_DIR),
            ("data", DEFAULT_DATA_DIR),
            ("secrets", DEFAULT_SECRETS_DIR),
            ("kws_secrets", DEFAULT_KWS_SECRETS_DIR),
        ]

        for name, src in dirs_to_move:
            if src.exists():
                dst = portable_root / name
                if dst.exists():
                    shutil.rmtree(dst)
                # Verify dst is not a symlink
                if dst.is_symlink():
                    dst.unlink()
                shutil.move(str(src), str(dst))
                # Create symlink back to original location
                src.parent.mkdir(parents=True, exist_ok=True)
                src.symlink_to(dst)
                # Verify symlink target is within portable_root
                resolved = src.resolve()
                if not str(resolved).startswith(str(portable_root)):
                    raise RuntimeError(f"Symlink escape detected: {resolved}")

        return jsonify({"ok": True, "message": f"Switched to portable mode at {portable_root}"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@portable_bp.get("/status")
@security.require_auth
def api_portable_status():
    """Check if running in portable mode."""
    marker = DEFAULT_USER_DATA_DIR / PORTABLE_MARKER
    if marker.exists():
        try:
            data = json.loads(marker.read_text())
            return jsonify({
                "portable": True,
                "location": str(marker.parent),
                "created": data.get("created"),
                "original_data_dir": data.get("original_data_dir")
            })
        except Exception:
            pass

    return jsonify({"portable": False})