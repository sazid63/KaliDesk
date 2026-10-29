"""Private WSL2 runtime lifecycle.

Hard rules, learned the hard way:

* The app only ever touches **its own** distribution (``cfg.runtime_distro``).
  It never terminates, unregisters or exports another distribution.
* It never runs ``wsl --shutdown``. WSL2 runs every distribution in one shared
  VM, so shutting that VM down would disturb Docker Desktop and the user's own
  distributions. We do not do that.
* If the runtime is not provisioned, we say so plainly instead of guessing.
* Nothing here runs a shell on the Windows side. We pass argv lists to
  ``wsl.exe`` directly.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import kws_paths
import kws_secrets

AGENT_TOKEN_SECRET = "agent_token"
CREATE_NO_WINDOW = 0x08000000
AGENT_PORT = 5055

# Provisioning lock to prevent concurrent ensure() calls
_PROVISION_LOCK = None
_PROVISION_STATUS: dict[str, Any] = {}


# --- low level: talking to wsl.exe ----------------------------------------

def _wsl_exe() -> str:
    return os.environ.get("KWS_WSL_EXE") or "wsl.exe"


def _startupinfo() -> Any:
    if os.name != "nt":
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return info


def _popen_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    return {"creationflags": CREATE_NO_WINDOW, "startupinfo": _startupinfo()}


def _run(args: list[str], timeout: int = 60,
         stdin_text: str | None = None) -> tuple[int, str, str]:
    """Run ``wsl.exe <args>`` and return (rc, stdout, stderr). Never raises."""
    payload = stdin_text.encode("utf-8") if stdin_text is not None else None
    try:
        proc = subprocess.run(  # noqa: S603
            [_wsl_exe(), *args],
            input=payload,
            capture_output=True,
            timeout=timeout,
            **_popen_kwargs(),
        )
    except FileNotFoundError:
        return 127, "", "wsl.exe was not found on PATH"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")
    return proc.returncode, out, err


# --- discovery ------------------------------------------------------------

def wsl_available() -> bool:
    if os.name != "nt":
        return False
    rc, out, err = _run(["--status"], timeout=25)
    text = (out + err).lower()
    if rc == 0:
        return True
    # Older builds return non-zero with a useful message.
    return "wsl" in text and "not installed" not in text and "n'est pas" not in text


def list_distros() -> list[str]:
    rc, out, err = _run(["--list", "--quiet"], timeout=20)
    text = (out + err).replace("\x00", "")
    names = []
    for line in text.splitlines():
        cleaned = line.strip().lstrip("*").strip()
        if cleaned:
            names.append(cleaned)
    return names


def distro_exists(cfg) -> bool:
    return cfg.runtime_distro in list_distros()


def image_path() -> Path | None:
    base = Path(kws_paths.resource("runtime", "dist"))
    for name in ("kalisub-rootfs.tar", "kalisub-rootfs.tar.gz", "rootfs.tar"):
        candidate = base / name
        if candidate.exists():
            return candidate
    # Fallback: installer may drop the image under the user's data directory.
    # The CLI-only install uses %LOCALAPPDATA%\KaliWindowsSubstitute; also check
    # that location for a packaged image.
    try:
        user_data = Path(kws_paths.user_data_dir())
        for name in ("kalisub-rootfs.tar", "kalisub-rootfs.tar.gz", "rootfs.tar"):
            candidate = user_data / name
            if candidate.exists():
                return candidate
        # Some installers put it alongside the install dir? Unlikely. Also check
        # one level up from user_data if it's nested.
    except Exception:
        pass
    return None


# --- provisioning ---------------------------------------------------------

def _download_image(cfg) -> tuple[bool, str]:
    if not cfg.rootfs_url:
        return False, "no local image and no download URL is configured"
    dest = Path(kws_paths.user_data_dir()) / "kalisub-rootfs.tar"
    try:
        with urllib.request.urlopen(cfg.rootfs_url, timeout=300) as resp:  # noqa: S310
            data = resp.read()
    except Exception as exc:  # noqa: BLE001
        return False, f"download failed: {exc}"
    if cfg.rootfs_sha256:
        digest = hashlib.sha256(data).hexdigest()
        if digest.lower() != cfg.rootfs_sha256.lower():
            return False, "the downloaded image failed its SHA-256 check"
    dest.write_bytes(data)
    return True, str(dest)


def _token() -> str:
    token = kws_secrets.get_secret(AGENT_TOKEN_SECRET)
    if not token:
        token = secrets.token_urlsafe(32)
        kws_secrets.set_secret(AGENT_TOKEN_SECRET, token)
    return token


def _import_distro(cfg, image: Path) -> tuple[bool, str]:
    install_dir = Path(kws_paths.user_data_dir()) / "wsl"
    install_dir.mkdir(parents=True, exist_ok=True)
    rc, out, err = _run(
        ["--import", cfg.runtime_distro, str(install_dir), str(image), "--version", "2"],
        timeout=3600,
    )
    if rc != 0:
        return False, f"import failed: {(err or out).strip()[:400]}"
    return True, "runtime imported"


def _write_agent_env(cfg, token: str) -> None:
    body = f"AGENT_TOKEN={token}\nKALISUB_PORT={AGENT_PORT}\n"
    _run(["-d", cfg.runtime_distro, "-u", "root", "--",
          "mkdir", "-p", "/etc/kalisub"], timeout=60)
    _run(["-d", cfg.runtime_distro, "-u", "root", "--",
          "tee", "/etc/kalisub/agent.env"], timeout=60, stdin_text=body)


def _start_agent(cfg) -> tuple[bool, str]:
    rc, out, err = _run(
        ["-d", cfg.runtime_distro, "-u", "root", "--",
         "/usr/local/bin/kalisub-agent-start"],
        timeout=180,
    )
    if rc != 0:
        return False, f"agent start failed: {(err or out).strip()[:400]}"
    return True, "agent started"


def _agent_up(cfg) -> bool:
    from server import tools as tool_api

    return tool_api.agent_online(cfg)


def provisioning_status(cfg) -> dict[str, Any] | None:
    """Return current provisioning status or None if idle."""
    return _PROVISION_STATUS.copy() if _PROVISION_STATUS else None


def status(cfg) -> dict[str, Any]:
    available = wsl_available()
    installed = distro_exists(cfg) if available else False
    agent = _agent_up(cfg) if installed else False
    if not available:
        message = ("WSL2 is not available. Enable it (see docs/PREREQUISITES.md), "
                   "restart, then try again.")
    elif not installed:
        message = ("The private runtime is not installed yet. "
                   "Press 'Set up runtime' to import it.")
    elif not agent:
        message = "The runtime exists but its tool agent is not answering."
    else:
        message = "Runtime online."
    return {
        "wsl": available,
        "installed": installed,
        "agent": agent,
        "distro": cfg.runtime_distro,
        "image": bool(image_path()),
        "message": message,
    }


def ensure(cfg) -> dict[str, Any]:
    """Provision and start the private runtime. Safe to call repeatedly.
    
    If a provision is already running, returns a provisional success response.
    """
    global _PROVISION_LOCK
    if _PROVISION_LOCK is None:
        _PROVISION_LOCK = threading.Lock()
    
    if _PROVISION_LOCK.locked():
        return {"ok": True, "provisioning": True,
                "message": "Provision already in progress. Please wait."}
    
    # Start provisioning in a daemon thread so Flask requests don't block
    def _provision_worker():
        global _PROVISION_STATUS
        _PROVISION_STATUS = {}
        try:
            with _PROVISION_LOCK:
                _PROVISION_STATUS["phase"] = "preparing"
                _PROVISION_STATUS["ok"] = False
                _PROVISION_STATUS["message"] = "Preparing runtime..."
                
                if not wsl_available():
                    _PROVISION_STATUS["message"] = (
                        "WSL2 is not available on this machine. Enable it (see "
                        "docs/PREREQUISITES.md), restart Windows, then try again.")
                    return
                
                _PROVISION_STATUS["phase"] = "importing"
                _PROVISION_STATUS["message"] = "Importing runtime..."
                
                if not distro_exists(cfg):
                    image = image_path()
                    if image is None:
                        ok, detail = _download_image(cfg)
                        if not ok:
                            _PROVISION_STATUS["message"] = (
                                "The runtime image was not found and could not be downloaded. "
                                "Build it with runtime/build-rootfs.sh, or set KWS_ROOTFS_URL "
                                f"and KWS_ROOTFS_SHA256. ({detail})")
                            return
                        image = Path(kws_paths.user_data_dir()) / "kalisub-rootfs.tar"
                    ok, message = _import_distro(cfg, image)
                    if not ok:
                        _PROVISION_STATUS["message"] = message
                        return
                
                _PROVISION_STATUS["phase"] = "configuring"
                _PROVISION_STATUS["message"] = "Configuring agent..."
                
                token = _token()
                _write_agent_env(cfg, token)
                
                _PROVISION_STATUS["phase"] = "starting"
                _PROVISION_STATUS["message"] = "Starting agent..."
                
                ok, message = _start_agent(cfg)
                if not ok:
                    _PROVISION_STATUS["message"] = message
                    return
                
                _PROVISION_STATUS["phase"] = "waiting"
                _PROVISION_STATUS["message"] = "Waiting for agent to be ready..."
                
                deadline = time.time() + 90
                while time.time() < deadline:
                    if _agent_up(cfg):
                        _PROVISION_STATUS["ok"] = True
                        _PROVISION_STATUS["message"] = "Runtime ready."
                        return
                    time.sleep(2)
                _PROVISION_STATUS["message"] = (
                    "The runtime started but the tool agent did not answer. Check "
                    "runtime/README.md for troubleshooting.")
        except Exception as exc:
            _PROVISION_STATUS["message"] = f"Provisioning failed: {exc}"
    
    # Start worker thread
    threading.Thread(target=_provision_worker, daemon=True).start()
    return {"ok": True, "provisioning": True, "message": "Starting runtime provisioning..."}
