#!/usr/bin/env python3
"""Kali Linux Windows Substitute - in-runtime tool agent.

Runs *inside* the app's private WSL2 distribution. It is the only component
that ever executes a tool. The Windows side (the Flask backend) can only ask it
to run a tool by id with an explicit argv list.

Safety properties:

* Binds 127.0.0.1 only, inside the distribution.
* Every request must carry the bearer token in ``/etc/kalisub/agent.env``.
* ``argv`` is executed with ``shell=False``. A metacharacter in a value is just
  data; there is no shell to interpret it.
* ``argv[0]`` must be the binary declared for that tool in
  ``/etc/kalisub/tools.json``. A tool that is not declared cannot be run at all.
* The target is scope-checked: public addresses are refused unless the user
  explicitly confirmed them.
* Output is capped and every run has a timeout.

This file uses only the Python standard library so it works before any package
beyond Python itself is installed.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ENV_FILE = "/etc/kalisub/agent.env"
TOOLS_FILE = "/etc/kalisub/tools.json"
LOG = "/var/log/kalisub-agent.log"

MAX_OUTPUT = 512 * 1024
DEFAULT_TIMEOUT = 180
MAX_TIMEOUT = 900

PRIVATE_RANGES = (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12",
    "192.168.0.0/16", "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10",
)

SAFE_ARG = re.compile(r"^[^\x00\r\n]*$")


def log(message: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except OSError:
        pass


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(ENV_FILE, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
    values.setdefault("AGENT_TOKEN", os.environ.get("AGENT_TOKEN", ""))
    values.setdefault("KALISUB_PORT", os.environ.get("KALISUB_PORT", "5055"))
    return values


def load_tools() -> dict[str, dict]:
    try:
        with open(TOOLS_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if isinstance(data, dict) and "tools" in data:
        return {entry["id"]: entry for entry in data["tools"] if entry.get("id")}
    if isinstance(data, dict):
        return data
    return {}


def host_of(target: str) -> str:
    host = (target or "").strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].split("?", 1)[0]
    if "@" in host:
        host = host.split("@", 1)[1]
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else host
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.strip()


def in_scope(target: str, confirmed: bool) -> tuple[bool, str]:
    host = target.strip()
    if not host:
        return True, "no target"
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return True, "loopback"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return (True, "hostname confirmed") if confirmed else (
            False, "hostname target needs explicit confirmation")
    if ip.is_loopback or ip.is_link_local:
        return True, "loopback"
    for cidr in PRIVATE_RANGES:
        try:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True, "private range"
        except ValueError:
            continue
    return (True, "external confirmed") if confirmed else (
        False, "external target needs explicit confirmation")


def binary_present(binary: str) -> bool:
    if not binary:
        return False
    if "/" in binary:
        return os.path.exists(binary)
    for folder in os.environ.get("PATH", "/usr/sbin:/usr/bin:/sbin:/bin").split(":"):
        candidate = os.path.join(folder, binary)
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return True
    return False


def run_argv(argv: list[str], timeout: int, cwd: str | None = None) -> dict:
    try:
        proc = subprocess.run(  # noqa: S603
            argv, capture_output=True, timeout=timeout, cwd=cwd, shell=False
        )
    except FileNotFoundError:
        return {"ok": False, "rc": 127, "stdout": "", "stderr": "command not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "rc": 124, "stdout": "",
                "stderr": f"timed out after {timeout}s"}
    except OSError as exc:
        return {"ok": False, "rc": 1, "stdout": "", "stderr": str(exc)}
    out = proc.stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT]
    err = proc.stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT]
    return {"ok": proc.returncode == 0, "rc": proc.returncode,
            "stdout": out, "stderr": err,
            "truncated": len(proc.stdout) > MAX_OUTPUT or len(proc.stderr) > MAX_OUTPUT}


class Handler(BaseHTTPRequestHandler):
    server_version = "kalisub-agent/1.0"
    protocol_version = "HTTP/1.1"

    # injected by the server
    token = ""
    tools: dict = {}

    def log_message(self, fmt, *args):  # noqa: A003
        log(f"{self.address_string()} {fmt % args}")

    # --- plumbing ---------------------------------------------------------
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self) -> bool:
        header = self.headers.get("Authorization", "")
        return bool(self.token) and header == f"Bearer {self.token}"

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self):  # noqa: N802
        if not self._authorised():
            self._json(401, {"error": "unauthorised"})
            return
        if self.path == "/health":
            self._json(200, {"ok": True, "tools": len(self.tools)})
            return
        if self.path == "/tools":
            listing = [
                {"id": tool_id, "present": binary_present(meta.get("binary", ""))}
                for tool_id, meta in sorted(self.tools.items())
            ]
            self._json(200, {"tools": listing})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if not self._authorised():
            self._json(401, {"error": "unauthorised"})
            return
        path = self.path.rstrip("/")
        body = self._read_body()
        if path == "/run":
            self._json(*self._run(body))
        elif path == "/tools/install":
            self._json(*self._apt(body, "install"))
        elif path == "/tools/remove":
            self._json(*self._apt(body, "remove"))
        else:
            self._json(404, {"error": "not found"})

    # --- operations -------------------------------------------------------
    def _run(self, body: dict):
        tool_id = str(body.get("tool", ""))
        meta = self.tools.get(tool_id)
        if meta is None:
            return 403, {"error": f"tool '{tool_id}' is not in the allowlist"}
        argv = body.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            return 400, {"error": "argv must be a non-empty list of strings"}
        if len(argv) > int(meta.get("max_args", 32)):
            return 400, {"error": "too many arguments"}
        expected = meta.get("binary", "")
        if argv[0] != expected:
            return 403, {"error": f"binary mismatch for '{tool_id}'"}
        for arg in argv:
            if not SAFE_ARG.match(arg):
                return 400, {"error": "argument contains a forbidden character"}
        if not binary_present(expected):
            return 409, {"error": f"{expected} is not installed",
                         "detail": "Install it from the Tool manager first."}
        allowed, reason = in_scope(
            str(body.get("target", "")), bool(body.get("confirm_external")))
        if not allowed:
            return 403, {"error": "target is out of scope", "detail": reason}

        timeout = int(body.get("timeout") or DEFAULT_TIMEOUT)
        timeout = max(5, min(timeout, MAX_TIMEOUT))
        log(f"run {tool_id}: {shlex.join(argv)}")
        result = run_argv(argv, timeout)
        result["argv"] = argv
        result["tool"] = tool_id
        return 200, result

    def _apt(self, body: dict, action: str):
        tool_id = str(body.get("tool", ""))
        meta = self.tools.get(tool_id)
        if meta is None:
            return 403, {"error": f"tool '{tool_id}' is not known"}
        packages = meta.get("packages") or []
        if not packages:
            return 400, {"error": "this tool has no packages to manage"}
        for package in packages:
            if not re.match(r"^[a-z0-9][a-z0-9+.\-]{0,80}$", package):
                return 400, {"error": f"refusing suspicious package name: {package}"}
        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        if action == "install":
            steps = [
                ["apt-get", "update", "-qq"],
                ["apt-get", "install", "-y", "--no-install-recommends", *packages],
            ]
            message = f"installed: {', '.join(packages)}"
        else:
            steps = [["apt-get", "remove", "-y", *packages]]
            message = f"removed: {', '.join(packages)}"

        output = ""
        for step in steps:
            try:
                proc = subprocess.run(  # noqa: S603
                    step, capture_output=True, timeout=MAX_TIMEOUT, env=env, shell=False
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return 500, {"error": str(exc)}
            output += proc.stdout.decode("utf-8", errors="replace")
            output += proc.stderr.decode("utf-8", errors="replace")
            if proc.returncode != 0:
                log(f"{action} {tool_id} failed rc={proc.returncode}")
                return 500, {"error": f"{action} failed", "detail": output[-4000:]}
        log(f"{action} {tool_id}")
        return 200, {"ok": True, "message": message,
                     "detail": output[-4000:], "tool": tool_id}


def main() -> int:
    env = load_env()
    Handler.token = env.get("AGENT_TOKEN", "")
    Handler.tools = load_tools()

    if not Handler.token:
        print("refusing to start: no AGENT_TOKEN configured", file=sys.stderr)
        return 2

    port = int(env.get("KALISUB_PORT", "5055"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    log(f"agent listening on 127.0.0.1:{port} with {len(Handler.tools)} tools")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
