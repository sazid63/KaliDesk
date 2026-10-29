"""Local vulnerable application playground.

Runs a simple Python http.server-based vulnerable app inside the WSL2 runtime.
The app source is embedded as a string constant and written to the WSL2 distro.

Classic vulns included:
  - SQLi echo: vulnerable to UNION-based injection (echoes raw input)
  - XSS reflect: reflects user input without escaping
  - Path traversal: reads files within /tmp/kalisub-playground
  - Weak session: predictable token (no HttpOnly/SameSite)

All vulns are sandboxed to 127.0.0.1:3000 and /tmp/kalisub-playground.
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

#: The vulnerable app source as a string constant.
_VULNERABLE_APP_SOURCE = '''
import http.server
import socketserver
import json
import os

PLAYGROUND_DIR = "/tmp/kalisub-playground"
os.makedirs(PLAYGROUND_DIR, exist_ok=True)

class KHandler(http.server.BaseHTTPRequestHandler):
    """Vulnerable HTTP request handler."""

    def _send_json(self, code: int, body: dict[str, Any]) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self) -> None:
        path = self.path
        if path.startswith("/SQLi"):
            # SQLi echo: raw concatenation
            query = path.split("?")[1] if "?" in path else ""
            params = {}
            for p in query.split("&"):
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k] = v
            user_input = params.get("q", "")
            result = f"echo: {user_input}"  # VULNERABLE
            self._send_json(200, {"result": result})
        elif path.startswith("/XSS"):
            # XSS reflect: raw reflection
            query = path.split("?")[1] if "?" in path else ""
            params = {}
            for p in query.split("&"):
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k] = v
            user_input = params.get("name", "")
            self._send_json(200, {"reflected": user_input})  # VULNERABLE
        elif path.startswith("/PATH"):
            # Path traversal: no realpath check
            query = path.split("?")[1] if "?" in path else ""
            params = {}
            for p in query.split("&"):
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k] = v
            filename = params.get("file", "index.html")
            safe_path = os.path.join(PLAYGROUND_DIR, filename)
            try:
                with open(safe_path, "r") as f:
                    content = f.read(400)
                self._send_json(200, {"file": filename, "content": content})
            except FileNotFoundError:
                self._send_json(404, {"error": "not found"})
            except OSError as exc:
                self._send_json(500, {"error": str(exc)})
        elif path.startswith("/TOKEN"):
            # Weak session: predictable token
            import time as _time
            token = str(int(_time.time()) % 1000000).zfill(6)
            self._send_json(200, {"token": token})
        else:
            self._send_json(200, {
                "endpoints": {
                    "SQLi": "/SQLi?q=<input>",
                    "XSS": "/XSS?name=<input>",
                    "PATH": "/PATH?file=<filename>",
                    "TOKEN": "/TOKEN",
                }
            })

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", 3000), KHandler)
    print("KWS Playground running on http://127.0.0.1:3000", flush=True)
    server.serve_forever()
'''

_PLAYGROUND_PORT = 3000
_PLAYGROUND_PID: int | None = None
_PLAYGROUND_DIR = Path("/opt/kalisub-playground")


def _write_playground_app() -> bool:
    """Write the vulnerable app source to the WSL2 data dir."""
    try:
        _PLAYGROUND_DIR.mkdir(parents=True, exist_ok=True)
        app_path = _PLAYGROUND_DIR / "vulnerable_app.py"
        app_path.write_text(_VULNERABLE_APP_SOURCE, encoding="utf-8")
        return True
    except OSError as exc:
        print(f"[playground] Failed to write app: {exc}", file=sys.stderr)
        return False


def start_playground() -> tuple[bool, str]:
    """Write the app and start it as a background process in WSL2.

    Returns (ok, message).
    """
    global _PLAYGROUND_PID

    # Ensure the app source is written
    if not _write_playground_app():
        return False, "Failed to write playground app"

    # Check if already running
    if is_running():
        return True, f"Playground already running on http://127.0.0.1:{_PLAYGROUND_PORT}"

    # Start the process inside WSL2 using nohup
    try:
        cmd = [
            "wsl", "-d", "KaliSubstitute",
            "nohup", sys.executable, "/opt/kalisub-playground/vulnerable_app.py",
            ">", "/tmp/kalisub-playground.log", "2>&1", "&"
        ]
        proc = subprocess.Popen(cmd, capture_output=True, text=True)  # noqa: S603
        proc.wait(timeout=5)
        time.sleep(2)

        # Verify it started
        if is_running():
            return True, f"Playground started on http://127.0.0.1:{_PLAYGROUND_PORT}"
        else:
            # Read log for error
            try:
                log_path = Path("/tmp/kalisub-playground.log")
                if log_path.exists():
                    log = log_path.read_text()[:400]
                    return False, f"Process start failed: {log}"
            except Exception:
                pass
            return False, "Process start failed: no log file"
    except Exception as exc:
        return False, f"Failed to start playground: {exc}"


def stop_playground() -> tuple[bool, str]:
    """Stop the playground process."""
    global _PLAYGROUND_PID
    try:
        # Kill any python process running the playground
        subprocess.run(
            ["wsl", "-d", "KaliSubstitute", "pkill", "-f", "vulnerable_app.py"],
            capture_output=True, timeout=5
        )
        _PLAYGROUND_PID = None
        return True, "Playground stopped"
    except Exception as exc:
        return False, f"Failed to stop: {exc}"


def is_running() -> bool:
    """Check if the playground process is alive."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{_PLAYGROUND_PORT}")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def get_status() -> dict[str, Any]:
    """Return the current playground status."""
    running = is_running()
    return {
        "running": running,
        "port": _PLAYGROUND_PORT,
        "url": f"http://127.0.0.1:{_PLAYGROUND_PORT}" if running else None,
    }