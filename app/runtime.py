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

First-run flow (``ensure``): find or download a root filesystem (an image you
placed locally, a pinned ``KWS_ROOTFS_URL`` + SHA-256, or the official Kali WSL
image, verified against Kali's published ``SHA256SUMS``), import it as the private
distribution, push the agent and the tool manifest into it, install the baseline
tools with apt, and start the agent. Because the agent and manifest are pushed on
every run, catalog changes never require rebuilding an image.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import kws.paths as kws_paths
import kws.secrets as kws_secrets

AGENT_TOKEN_SECRET = "agent_token"
CREATE_NO_WINDOW = 0x08000000
AGENT_PORT = 5055

OFFICIAL_BASE = "https://kali.download/wsl-images/current/"
OFFICIAL_NAME = re.compile(r"^kali-linux-([0-9][0-9.]*)-wsl-rootfs-amd64\.wsl$")
PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.\-]{0,80}$")
# Always installed in addition to the catalog's baseline tools.
EXTRA_BASELINE = ("python3", "ca-certificates", "wordlists")
BASELINE_MARKER = "/etc/kalisub/.baseline-done"

_PROVISION_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()
_PROVISION_STATUS: dict[str, Any] = {}

_STATUS_TTL = 5.0
_STATUS_CACHE: dict[str, Any] = {"at": 0.0, "value": None}
_AUTOSTART = {"at": 0.0, "running": False}
_AUTOSTART_LOCK = threading.Lock()  # guards the check-and-set in autostart()
_KEEPALIVE: dict[str, Any] = {"proc": None}


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


def _env() -> dict[str, str]:
    # Newer WSL builds then print UTF-8; older ones still print UTF-16, which
    # _decode() handles.
    return {**os.environ, "WSL_UTF8": "1"}


def _decode(data: bytes | None) -> str:
    """Decode wsl.exe output, which may be UTF-16LE (older builds) or UTF-8."""
    if not data:
        return ""
    if b"\x00" in data[:400]:
        text = data.decode("utf-16-le", errors="replace")
    else:
        text = data.decode("utf-8", errors="replace")
    return text.lstrip("﻿").replace("\x00", "")


def _run(
    args: list[str], timeout: int = 60, stdin_text: str | bytes | None = None
) -> tuple[int, str, str]:
    """Run ``wsl.exe <args>`` and return (rc, stdout, stderr). Never raises."""
    if isinstance(stdin_text, str):
        payload: bytes | None = stdin_text.encode("utf-8")
    else:
        payload = stdin_text
    try:
        proc = subprocess.run(  # noqa: S603
            [_wsl_exe(), *args],
            input=payload,
            capture_output=True,
            timeout=timeout,
            env=_env(),
            **_popen_kwargs(),
        )
    except FileNotFoundError:
        return 127, "", "wsl.exe was not found on PATH"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return proc.returncode, _decode(proc.stdout), _decode(proc.stderr)


def _in_distro(cfg, argv: list[str], timeout: int = 60, stdin_text=None) -> tuple[int, str, str]:
    # --exec runs the argv directly. Without it wsl.exe hands the command line to the distro's
    # shell, which expands $1, $(...) and quotes before our script ever sees them.
    return _run(["-d", cfg.runtime_distro, "-u", "root", "--exec", *argv], timeout, stdin_text)


def in_distro(cfg, argv: list[str], timeout: int = 60, stdin_text=None) -> tuple[int, str, str]:
    """Run an argv list as root inside our private distro. Returns (rc, stdout, stderr)."""
    return _in_distro(cfg, argv, timeout, stdin_text)


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
    names = []
    for line in (out + err).splitlines():
        cleaned = line.strip().lstrip("*").strip()
        if cleaned:
            names.append(cleaned)
    return names


def distro_exists(cfg) -> bool:
    return cfg.runtime_distro in list_distros()


def _image_names() -> tuple[str, ...]:
    return ("kalisub-rootfs.tar", "kalisub-rootfs.tar.gz", "rootfs.tar")


def image_path() -> Path | None:
    """A root filesystem already on disk (bundled, built, or downloaded earlier)."""
    folders = [Path(kws_paths.resource("runtime", "dist"))]
    try:
        folders.append(Path(kws_paths.user_data_dir()))
    except OSError:
        pass
    for folder in folders:
        for name in _image_names():
            candidate = folder / name
            if candidate.exists():
                return candidate
    return None


# --- provisioning state ---------------------------------------------------


def _set(**fields: Any) -> None:
    with _STATE_LOCK:
        _PROVISION_STATUS.update(fields)
        _STATUS_CACHE["at"] = 0.0


def provisioning_status(cfg=None) -> dict[str, Any] | None:
    """Return current provisioning status or None if it never ran."""
    with _STATE_LOCK:
        return dict(_PROVISION_STATUS) if _PROVISION_STATUS else None


# --- image download -------------------------------------------------------


def _fetch_text(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse ``sha256sum`` output into {filename: hex digest}."""
    sums: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            sums[parts[1].strip().lstrip("*")] = parts[0].lower()
    return sums


def official_image(base: str | None = None) -> tuple[str, str]:
    """Return (url, sha256) of the newest official Kali WSL image."""
    base = base or os.environ.get("KWS_ROOTFS_BASE") or OFFICIAL_BASE
    if not base.endswith("/"):
        base += "/"
    sums = parse_sha256sums(_fetch_text(base + "SHA256SUMS"))
    names = [name for name in sums if OFFICIAL_NAME.match(name)]
    if not names:
        raise RuntimeError("the Kali download page lists no WSL root filesystem")
    # Compare versions as numbers: "2025.10" is newer than "2025.4" (a plain string sort says not).
    newest = max(names, key=lambda name: _version_key(OFFICIAL_NAME.match(name).group(1)))
    return base + newest, sums[newest]


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def download_image(url: str, sha256: str, dest: Path) -> tuple[bool, str]:
    """Stream ``url`` to ``dest`` with progress, verifying SHA-256. Resumes nothing:
    a partial file is discarded, a complete verified file is reused."""
    if not sha256:
        return False, "refusing to use a download without a SHA-256 checksum"
    if dest.exists() and _sha256_file(dest) == sha256.lower():
        _set(progress={"done": dest.stat().st_size, "total": dest.stat().st_size})
        return True, str(dest)
    part = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            last = 0.0
            with open(part, "wb") as handle:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - last > 0.5:
                        _set(progress={"done": done, "total": total})
                        last = now
            _set(progress={"done": done, "total": total})
    except Exception as exc:  # noqa: BLE001
        part.unlink(missing_ok=True)
        return False, f"download failed: {exc}"
    if digest.hexdigest() != sha256.lower():
        part.unlink(missing_ok=True)
        return False, "the downloaded image failed its SHA-256 check and was discarded"
    part.replace(dest)
    return True, str(dest)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def obtain_image(cfg) -> tuple[Path | None, str]:
    """Find or download a root filesystem. Returns (path, message)."""
    local = image_path()
    if local is not None:
        return local, f"using local image {local.name}"
    dest_dir = Path(kws_paths.user_data_dir())
    if cfg.rootfs_url:
        _set(phase="downloading", message="Downloading the runtime image...")
        name = cfg.rootfs_url.rsplit("/", 1)[-1] or "rootfs.tar"
        ok, detail = download_image(cfg.rootfs_url, cfg.rootfs_sha256, dest_dir / name)
        return (Path(detail), "downloaded") if ok else (None, detail)
    _set(phase="downloading", message="Looking up the official Kali WSL image...")
    try:
        url, sha = official_image()
    except Exception as exc:  # noqa: BLE001
        return None, (
            f"could not reach the Kali download server ({exc}). Check your internet "
            "connection, or place a root filesystem named kalisub-rootfs.tar in "
            f"{dest_dir} and press Set up runtime again."
        )
    _set(message=f"Downloading {url.rsplit('/', 1)[-1]}...")
    ok, detail = download_image(url, sha, dest_dir / url.rsplit("/", 1)[-1])
    return (Path(detail), "downloaded") if ok else (None, detail)


# --- distro setup ---------------------------------------------------------


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


def _push(cfg, local: Path, remote: str, mode: str) -> tuple[bool, str]:
    script = 'mkdir -p "$(dirname "$1")" && cat > "$1" && chmod "$2" "$1"'
    rc, out, err = _in_distro(
        cfg, ["sh", "-c", script, "sh", remote, mode], timeout=120, stdin_text=local.read_bytes()
    )
    if rc != 0:
        return False, f"could not write {remote}: {(err or out).strip()[:300]}"
    return True, remote


def _runtime_files() -> list[tuple[Path, str, str]]:
    def res(*parts: str) -> Path:
        return Path(kws_paths.resource(*parts))

    return [
        (res("runtime", "agent", "agent.py"), "/usr/local/lib/kalisub/agent.py", "755"),
        (
            res("runtime", "rootfs", "etc", "kalisub", "tools.json"),
            "/etc/kalisub/tools.json",
            "644",
        ),
        (
            res("runtime", "rootfs", "usr", "local", "bin", "kalisub-agent-start"),
            "/usr/local/bin/kalisub-agent-start",
            "755",
        ),
    ]


def baseline_packages() -> list[str]:
    """Packages of every ``baseline`` tool in the manifest, plus the essentials."""
    names: list[str] = list(EXTRA_BASELINE)
    manifest = Path(kws_paths.resource("runtime", "rootfs", "etc", "kalisub", "tools.json"))
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    for tool in data.get("tools", []):
        if tool.get("baseline"):
            names.extend(tool.get("packages") or [])
    seen: dict[str, None] = {}
    for name in names:
        if PACKAGE_NAME.match(name):
            seen.setdefault(name)
    return list(seen)


def _push_runtime_files(cfg) -> tuple[bool, str]:
    for local, remote, mode in _runtime_files():
        if not local.exists():
            return False, f"missing bundled file {local.name}"
        ok, detail = _push(cfg, local, remote, mode)
        if not ok:
            return False, detail
    return True, "agent files installed"


def _apply_wsl_conf(cfg) -> None:
    """Install the private-distro wsl.conf and restart *our own* distro so it applies."""
    conf = Path(kws_paths.resource("runtime", "rootfs", "etc", "wsl.conf"))
    if conf.exists() and _push(cfg, conf, "/etc/wsl.conf", "644")[0]:
        _run(["--terminate", cfg.runtime_distro], timeout=60)


APT_COMPONENTS = "main contrib non-free non-free-firmware"


def _ensure_apt_components(cfg) -> None:
    """Make sure the Kali mirror line also enables contrib and non-free.

    Found on a real distro: metasploit-framework depends on oracle-instantclient-basic, which
    lives in non-free, so installs failed when only ``main`` was enabled. Idempotent.
    """
    # Raw string: \1 must reach sed as a backreference, not become a control character.
    script = (
        r"f=/etc/apt/sources.list; [ -f $f ] || exit 0; "
        r"sed -i -E 's#^(deb(-src)? +[^ ]*kali[^ ]* +kali-rolling) +main( +.*)?$#\1 "
        + APT_COMPONENTS + "#' $f"
    )
    _in_distro(cfg, ["sh", "-c", script], timeout=30)


def _install_baseline(cfg) -> tuple[bool, str]:
    packages = baseline_packages()
    _ensure_apt_components(cfg)
    env = ["env", "DEBIAN_FRONTEND=noninteractive"]
    rc, out, err = _in_distro(cfg, [*env, "apt-get", "update", "-qq"], timeout=900)
    if rc != 0:
        return False, f"apt-get update failed: {(err or out).strip()[-300:]}"
    rc, out, err = _in_distro(
        cfg, [*env, "apt-get", "install", "-y", "--no-install-recommends", *packages], timeout=3600
    )
    if rc != 0:
        return False, f"installing the baseline tools failed: {(err or out).strip()[-400:]}"
    # rockyou ships compressed; the password tools expect the plain file.
    _in_distro(
        cfg,
        [
            "sh",
            "-c",
            "f=/usr/share/wordlists/rockyou.txt; [ -f $f ] || "
            "{ [ -f $f.gz ] && gunzip -k $f.gz; }; true",
        ],
        timeout=300,
    )
    return True, "baseline tools installed"


def _write_agent_env(cfg, token: str) -> tuple[bool, str]:
    body = f"AGENT_TOKEN={token}\nKALISUB_PORT={AGENT_PORT}\n"
    script = (
        "mkdir -p /etc/kalisub && cat > /etc/kalisub/agent.env "
        "&& chmod 600 /etc/kalisub/agent.env"
    )
    rc, out, err = _in_distro(cfg, ["sh", "-c", script], timeout=60, stdin_text=body)
    return rc == 0, (err or out).strip()[:300]


def _stop_agent(cfg) -> None:
    script = (
        "kill $(cat /run/kalisub-agent.pid 2>/dev/null) 2>/dev/null; "
        "rm -f /run/kalisub-agent.pid; true"
    )
    _in_distro(cfg, ["sh", "-c", script], timeout=30)


def _start_agent(cfg) -> tuple[bool, str]:
    rc, out, err = _in_distro(cfg, ["/usr/local/bin/kalisub-agent-start"], timeout=180)
    if rc != 0:
        return False, f"agent start failed: {(err or out).strip()[:400]}"
    return True, "agent started"


def _agent_up(cfg) -> bool:
    from server import tools as tool_api

    return tool_api.agent_online(cfg)


def keepalive(cfg) -> None:
    """Hold one ``wsl`` session open so WSL does not stop the distro (and the agent in it)."""
    proc = _KEEPALIVE["proc"]
    if proc is not None and proc.poll() is None:
        return
    try:
        _KEEPALIVE["proc"] = subprocess.Popen(  # noqa: S603
            [_wsl_exe(), "-d", cfg.runtime_distro, "-u", "root", "--", "sleep", "infinity"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_env(),
            **_popen_kwargs(),
        )
    except OSError:
        _KEEPALIVE["proc"] = None


@atexit.register
def _release_keepalive() -> None:
    proc = _KEEPALIVE.get("proc")
    if proc is not None and proc.poll() is None:
        proc.terminate()


def autostart(cfg) -> bool:
    """If the distro exists but its agent is down, bring it back (throttled, background).

    This starts processes, so it is only called from an explicit POST (never from a GET).
    Returns True when a start was launched.
    """
    now = time.time()
    with _AUTOSTART_LOCK:
        if _AUTOSTART["running"] or now - _AUTOSTART["at"] < 30 or _PROVISION_LOCK.locked():
            return False
        _AUTOSTART["at"] = now
        _AUTOSTART["running"] = True

    def work() -> None:
        try:
            keepalive(cfg)
            _start_agent(cfg)
        finally:
            _AUTOSTART["running"] = False
            _STATUS_CACHE["at"] = 0.0

    threading.Thread(target=work, daemon=True).start()
    return True


# --- terminal -------------------------------------------------------------

CREATE_NEW_CONSOLE = 0x00000010


def open_terminal(cfg, command: list[str] | None = None) -> tuple[bool, str]:
    """Open a console window with a root shell in the private runtime.

    ``command`` must come from the server's own allowlist (never from a request).
    The window stays open until Enter is pressed after the command finishes.
    """
    if os.name != "nt":
        return False, "terminals can only be opened on Windows"
    argv = [_wsl_exe(), "-d", cfg.runtime_distro, "-u", "root"]
    if command:
        script = '"$@"; echo; echo "[finished - press Enter to close]"; read _unused'
        argv += ["--", "sh", "-c", script, "sh", *command]
    try:
        subprocess.Popen(  # noqa: S603
            argv, creationflags=CREATE_NEW_CONSOLE, env=_env(), stdin=None
        )
    except OSError as exc:
        return False, f"could not open a terminal: {exc}"
    return True, "terminal opened"


# --- status ---------------------------------------------------------------


def status(cfg) -> dict[str, Any]:
    """Runtime status. Read-only: it never starts anything (see ``autostart``).

    Cached for a few seconds so polling does not spawn wsl.exe.
    """
    now = time.time()
    cached = _STATUS_CACHE["value"]
    if cached is not None and now - _STATUS_CACHE["at"] < _STATUS_TTL:
        return dict(cached)
    available = wsl_available()
    installed = distro_exists(cfg) if available else False
    agent = _agent_up(cfg) if installed else False
    if not available:
        message = (
            "WSL2 is not available. Enable it (see docs/PREREQUISITES.md), restart, then try again."
        )
    elif not installed:
        message = "The private runtime is not installed yet. Press 'Set up runtime' to install it."
    elif not agent:
        message = "The runtime exists but its tool agent is not answering. Start it to continue."
    else:
        message = "Runtime online."
    value = {
        "wsl": available,
        "installed": installed,
        "agent": agent,
        "distro": cfg.runtime_distro,
        "image": bool(image_path()),
        "message": message,
    }
    _STATUS_CACHE.update(at=now, value=value)
    return dict(value)


# --- ensure ---------------------------------------------------------------


def ensure(cfg) -> dict[str, Any]:
    """Provision and start the private runtime in the background. Safe to call repeatedly."""
    if not _PROVISION_LOCK.acquire(blocking=False):
        return {"ok": True, "provisioning": True, "message": "Setup is already in progress."}
    with _STATE_LOCK:
        _PROVISION_STATUS.clear()
        _PROVISION_STATUS.update(
            phase="preparing", ok=False, done=False, error=False,
            message="Preparing...", progress=None,
        )

    def fail(message: str) -> None:
        _set(phase="failed", ok=False, done=True, error=True, message=message)

    def worker() -> None:
        try:
            _provision(cfg, fail)
        except Exception as exc:  # noqa: BLE001
            fail(f"Setup failed: {exc}")
        finally:
            _PROVISION_LOCK.release()

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "provisioning": True, "message": "Setting up the runtime..."}


def _provision(cfg, fail) -> None:
    if not wsl_available():
        fail(
            "WSL2 is not available on this machine. Enable it (see docs/PREREQUISITES.md), "
            "restart Windows, then try again."
        )
        return

    fresh = False
    if not distro_exists(cfg):
        image, detail = obtain_image(cfg)
        if image is None:
            fail(detail)
            return
        _set(phase="importing", message="Importing the runtime (this takes a minute)...",
             progress=None)
        ok, detail = _import_distro(cfg, image)
        if not ok:
            fail(detail)
            return
        fresh = True

    _set(phase="configuring", message="Installing the tool agent...")
    _ensure_apt_components(cfg)
    ok, detail = _push_runtime_files(cfg)
    if not ok:
        fail(detail)
        return
    if fresh:
        _apply_wsl_conf(cfg)
    # The marker lets a retry after a failed install pick up where it stopped.
    if fresh or _in_distro(cfg, ["test", "-f", BASELINE_MARKER], timeout=30)[0] != 0:
        _set(phase="installing", message="Installing the baseline tools (a few minutes)...")
        ok, detail = _install_baseline(cfg)
        if not ok:
            fail(detail)
            return
        _in_distro(cfg, ["touch", BASELINE_MARKER], timeout=30)

    _set(phase="starting", message="Starting the tool agent...")
    ok, detail = _write_agent_env(cfg, _token())
    if not ok:
        fail(f"could not write the agent token: {detail}")
        return
    _stop_agent(cfg)  # make sure a stale agent never keeps an old token
    keepalive(cfg)
    ok, detail = _start_agent(cfg)
    if not ok:
        fail(detail)
        return

    _set(phase="waiting", message="Waiting for the agent to answer...")
    deadline = time.time() + 90
    while time.time() < deadline:
        if _agent_up(cfg):
            _set(phase="ready", ok=True, done=True, error=False, message="Runtime ready.",
                 progress=None)
            return
        time.sleep(2)
    fail(
        "The runtime started but the tool agent did not answer. Look at "
        "/var/log/kalisub-agent.log inside the runtime (see runtime/README.md)."
    )
