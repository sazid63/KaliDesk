"""Strix Process Manager.

Manages the Strix AI Pentest agent running in the WSL2 runtime.
Strix is a separate Python package installed in an isolated venv.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import kws_secrets
import server.config as config

STRIX_VENV = Path("/opt/strix/venv")
STRIX_PORT = 8080
STRIX_LOG = "/var/log/strix.log"
STRIX_API_BASE = f"http://127.0.0.1:{STRIX_PORT}"


def _wsl_exe() -> str:
    return os.environ.get("KWS_WSL_EXE") or "wsl.exe"


def _run_wsl(args: list[str], timeout: int = 60,
             stdin_text: str | None = None) -> tuple[int, str, str]:
    """Run wsl.exe with args, return (rc, stdout, stderr)."""
    payload = stdin_text.encode("utf-8") if stdin_text else None
    try:
        proc = subprocess.run(  # noqa: S603
            [_wsl_exe(), *args],
            input=payload,
            capture_output=True,
            timeout=timeout,
            creationflags=0x08000000,
        )
    except FileNotFoundError:
        return 127, "", "wsl.exe was not found on PATH"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")
    return proc.returncode, out, err


def install_strix() -> tuple[bool, str]:
    """Install Strix agent in WSL2 runtime using pip3 in isolated venv."""
    if not os.path.exists(STRIX_VENV):
        # Create venv
        rc, out, err = _run_wsl(
            ["python3", "-m", "venv", str(STRIX_VENV)],
            timeout=30,
        )
        if rc != 0:
            return False, f"Failed to create venv: {(err or out).strip()[:400]}"

    # Install strix-agent
    pip = str(STRIX_VENV / "bin" / "pip3")
    rc, out, err = _run_wsl(
        [pip, "install", "strix-agent"],
        timeout=300,  # 5 minutes for install
    )
    if rc != 0:
        return False, f"Install failed: {(err or out).strip()[:400]}"

    return True, "Strix installed successfully"


def start_strix(port: int = STRIX_PORT) -> tuple[bool, Any]:
    """Start Strix server in WSL2 runtime, returns (ok, pid_or_message)."""
    python = str(STRIX_VENV / "bin" / "python3")
    # The strix-agent runs as a server on port 8080
    cmd = [python, "-m", "strix_agent.server", "--port", str(port)]

    # Start in background with no window
    try:
        proc = subprocess.Popen(  # noqa: S603
            [_wsl_exe(), "-d", config.load().runtime_distro, "-u", "root", "--", *cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=0x08000000,
        )
    except Exception as exc:
        return False, f"Failed to start: {exc}"

    # Wait a moment to see if it starts
    time.sleep(2)
    if proc.poll() is not None:
        _, out, err = proc.communicate()
        return False, f"Process exited: {(out or err).strip()[:400]}"

    return True, proc.pid


def stop_strix(pid: int) -> tuple[bool, str]:
    """Stop Strix server by PID."""
    try:
        _run_wsl(["kill", str(pid)], timeout=10)
        return True, f"Stopped PID {pid}"
    except Exception as exc:
        return False, f"Failed to stop: {exc}"


def is_running(pid: int) -> bool:
    """Check if a PID is running in WSL2."""
    rc, out, err = _run_wsl(["ps", "-p", str(pid)], timeout=5)
    return rc == 0 and str(pid) in out


def get_strix_url() -> str:
    """Get the Strix API base URL."""
    return STRIX_API_BASE


def _scope_allows(target: str, confirmed: bool) -> tuple[bool, str]:
    """Check if target is in scope (reuses security logic)."""
    from server.config import load
    from server.security import scope_allows

    cfg = load()
    return scope_allows(target, confirmed, cfg.private_ranges)


def proxy_request(method: str, path: str,
               body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    """
    Proxy a request to Strix API with authentication and scope guard.
    
    Strix runs in the same WSL2 distro as the tool agent, so we use the
    same agent token for auth. The Strix server validates the token
    and enforces its own scope guard.
    """
    # Get agent token
    token = kws_secrets.get_secret("agent_token")
    if not token:
        return 401, {"error": "unauthorised"}

    # Build URL
    url = f"{STRIX_API_BASE}{path}"
    
    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    
    # Prepare body
    data = json.dumps(body).encode("utf-8") if body is not None else None
    
    # Make request
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in headers.items():
        req.add_header(key, value)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            resp_body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(resp_body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        return exc.code, {"error": f"Strix error: {detail}"}
    except urllib.error.URLError as exc:
        return 503, {"error": f"Strix unreachable: {exc}"}
    except json.JSONDecodeError as exc:
        return 500, {"error": f"Invalid response: {exc}"}


def status() -> dict[str, Any]:
    """Get Strix status: installed, running, PID, URL."""
    installed = STRIX_VENV.exists() and (STRIX_VENV / "bin" / "python3").exists()
    pid = None
    running = False
    if installed:
        # We could read PID from a file or scan processes
        # For now, just check if port 8080 is listening
        rc, out, err = _run_wsl(
            ["netstat", "-tuln"], timeout=5)
        if rc == 0 and f":{STRIX_PORT}" in out:
            # Try to find PID
            rc, out, err = _run_wsl(
                ["lsof", "-ti", f":{STRIX_PORT}"], timeout=5)
            if rc == 0 and out.strip().isdigit():
                pid = int(out.strip())
                running = True

    return {
        "installed": installed,
        "running": running,
        "pid": pid,
        "url": STRIX_API_BASE if installed and running else None,
    }

def main() -> int:
    """CLI entry point for testing."""
    import argparse
    parser = argparse.ArgumentParser(description="Strix manager")
    parser.add_argument("cmd", choices=["install", "start", "stop", "status", "proxy"])
    parser.add_argument("--port", type=int, default=STRIX_PORT)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--method", choices=["GET", "POST", "PUT", "DELETE"])
    parser.add_argument("--path", default="/")
    parser.add_argument("--body", default="{}")
    args = parser.parse_args()

    if args.cmd == "install":
        ok, msg = install_strix()
        print(json.dumps({"ok": ok, "message": msg}))
    elif args.cmd == "start":
        ok, pid = start_strix(args.port)
        print(json.dumps({"ok": ok, "pid": pid}))
    elif args.cmd == "stop":
        if not args.pid:
            print(json.dumps({"ok": False, "message": "PID required"}))
        else:
            ok, msg = stop_strix(args.pid)
            print(json.dumps({"ok": ok, "message": msg}))
    elif args.cmd == "status":
        if not args.pid:
            print(json.dumps({"ok": False, "message": "PID required"}))
        else:
            running = is_running(args.pid)
            print(json.dumps({"ok": True, "running": running}))
    elif args.cmd == "proxy":
        if not args.body:
            body = None
        else:
            body = json.loads(args.body)
        status, result = proxy_request(args.method, args.path, body)
        print(json.dumps({"status": status, "result": result}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
