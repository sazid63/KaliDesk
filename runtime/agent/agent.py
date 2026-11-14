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

import codecs
import hmac
import ipaddress
import json
import os
import re
import secrets
import shlex
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

# The environment overrides let tests and tools/smoke.py run a throw-away agent without
# touching the real one in /etc/kalisub.
ENV_FILE = os.environ.get("KALISUB_ENV_FILE", "/etc/kalisub/agent.env")
TOOLS_FILE = os.environ.get("KALISUB_TOOLS_FILE", "/etc/kalisub/tools.json")
LOG = os.environ.get("KALISUB_LOG", "/var/log/kalisub-agent.log")

# The distro's default LANG (en_US.UTF-8) is usually not generated, which makes tools such as
# crunch abort with "setlocale() failed". C.UTF-8 always exists.
TOOL_ENV = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}

MAX_OUTPUT = 512 * 1024
DEFAULT_TIMEOUT = 180
MAX_TIMEOUT = 900

# The agent runs alone inside the distro, so it cannot import the server package.
# Keep this tuple in sync with server.config.PRIVATE_RANGES (a test checks it).
PRIVATE_RANGES = (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12",
    "192.168.0.0/16", "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10",
)

_LOG_LOCK = threading.Lock()
SAFE_ARG = re.compile(r"[^\x00\r\n]*")  # use fullmatch: "$" would accept a trailing newline


def log(message: str) -> None:
    try:
        line = message.rstrip() + "\n"
        with _LOG_LOCK:
            with open(LOG, "a", encoding="utf-8") as handle:
                handle.write(line)
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


_PRIVATE_NETS = tuple(ipaddress.ip_network(c) for c in PRIVATE_RANGES)


def _ip_is_private(ip) -> bool:
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback or any(ip.version == n.version and ip in n for n in _PRIVATE_NETS)


def _net_is_private(net) -> bool:
    """A network is private only if the *whole* network sits inside a private range."""
    if net.version == 6 and net.network_address.ipv4_mapped is not None:
        return False  # mapped networks are never treated as private
    return any(net.version == n.version and net.subnet_of(n) for n in _PRIVATE_NETS)


def classify_target(target: str) -> str:
    """Return 'empty', 'private' or 'public'. Stdlib only.

    Keep in sync with ``server.security.classify_target`` (a test compares them).
    Anything we cannot parse with certainty is 'public', i.e. needs confirmation.
    """
    text = (target or "").strip()
    if not text:
        return "empty"
    if any(ch in text for ch in "\\ \t\r\n\x00"):
        return "public"
    # Bare IP, bare IPv6 or CIDR (e.g. 10.0.0.0/24, ::1, ::ffff:8.8.8.8).
    try:
        if "/" in text:
            net = ipaddress.ip_network(text, strict=False)
            return "private" if _net_is_private(net) else "public"
        return "private" if _ip_is_private(ipaddress.ip_address(text)) else "public"
    except ValueError:
        pass
    # URL or host[:port][/path]
    try:
        parts = urlsplit(text if "://" in text else "//" + text)
        host = parts.hostname or ""
        parts.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError:
        return "public"
    if not host:
        return "public"
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return "private"
    try:
        return "private" if _ip_is_private(ipaddress.ip_address(host)) else "public"
    except ValueError:
        # A hostname: we cannot know where it resolves, so it needs confirmation.
        return "public"


def in_scope(target: str, confirmed: bool) -> tuple[bool, str]:
    """Check whether the target is in scope (private/loopback, or user-confirmed)."""
    kind = classify_target(target)
    if kind == "empty":
        return True, "no target"
    if kind == "private":
        return True, "target is on a private or loopback address"
    # For hostnames and external IPs, use the same confirmation logic
    if confirmed:
        return True, "external target explicitly confirmed by the user"
    return False, (
        "target is outside the private ranges. Tick the confirmation box and "
        "make sure you have written authorisation to test it."
    )


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
            argv, capture_output=True, timeout=timeout, cwd=cwd, shell=False,
            env={**os.environ, **TOOL_ENV},
        )
    except FileNotFoundError:
        return {"ok": False, "rc": 127, "stdout": "", "stderr": "command not found"}
    except subprocess.TimeoutExpired as exc:
        # Keep whatever the tool printed before it was killed.
        partial_out = (exc.stdout or b"")
        partial_err = (exc.stderr or b"")
        if isinstance(partial_out, str):
            partial_out = partial_out.encode("utf-8", errors="replace")
        if isinstance(partial_err, str):
            partial_err = partial_err.encode("utf-8", errors="replace")
        note = f"\n[timed out after {timeout}s - partial output above]"
        return {"ok": False, "rc": 124, "timed_out": True,
                "stdout": partial_out.decode("utf-8", errors="replace")[:MAX_OUTPUT],
                "stderr": partial_err.decode("utf-8", errors="replace")[:MAX_OUTPUT] + note}
    except OSError as exc:
        return {"ok": False, "rc": 1, "stdout": "", "stderr": str(exc)}
    out = proc.stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT]
    err = proc.stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT]
    return {"ok": proc.returncode == 0, "rc": proc.returncode,
            "stdout": out, "stderr": err,
            "truncated": len(proc.stdout) > MAX_OUTPUT or len(proc.stderr) > MAX_OUTPUT}


class Job:
    """One streamed, cancellable run: tool output is captured as it is produced."""

    def __init__(self, tool: str, kind: str, steps: list[list[str]], timeout: int):
        self.id = secrets.token_hex(8)
        self.tool = tool
        self.kind = kind
        self.steps = steps
        self.timeout = timeout
        self.state = "running"  # running | done | failed | cancelled | timeout
        self.rc: int | None = None
        self.text = ""
        self.truncated = False
        self.started = time.time()
        self.ended: float | None = None
        self._proc: subprocess.Popen | None = None
        self._cancelled = False
        self._timed_out = False
        self._lock = threading.Lock()
        with _JOBS_LOCK:
            _prune_jobs()
            JOBS[self.id] = self

    def start(self) -> None:
        threading.Thread(target=self._work, daemon=True).start()

    def _append(self, chunk: str) -> None:
        with self._lock:
            room = MAX_OUTPUT - len(self.text)
            if room <= 0:
                self.truncated = True
                return
            if len(chunk) > room:
                chunk = chunk[:room]
                self.truncated = True
            self.text += chunk

    def _work(self) -> None:
        env = {**os.environ, **TOOL_ENV, "DEBIAN_FRONTEND": "noninteractive"}
        deadline = self.started + self.timeout
        rc = 0
        try:
            for step in self.steps:
                if self._cancelled:
                    break
                if self.kind != "run":
                    self._append(f"$ {shlex.join(step)}\n")
                try:
                    proc = subprocess.Popen(  # noqa: S603
                        step, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL, env=env, shell=False,
                        start_new_session=True,
                    )
                except FileNotFoundError:
                    self._append("command not found\n")
                    rc = 127
                    break
                except OSError as exc:
                    self._append(f"{exc}\n")
                    rc = 1
                    break
                self._proc = proc
                timer = threading.Timer(max(1.0, deadline - time.time()), self._on_timeout)
                timer.daemon = True
                timer.start()
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                fd = proc.stdout.fileno()
                while True:
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        break
                    self._append(decoder.decode(chunk))
                self._append(decoder.decode(b"", final=True))
                rc = proc.wait()
                timer.cancel()
                if rc != 0:
                    break
        except Exception as exc:  # noqa: BLE001
            self._append(f"\n[agent error: {exc}]\n")
            rc = 1
        with self._lock:
            self.rc = rc
            self.ended = time.time()
            if self._cancelled:
                self.state = "cancelled"
            elif self._timed_out:
                self.state = "timeout"
                self.text += f"\n[timed out after {self.timeout}s - output above is partial]"
            else:
                self.state = "done" if rc == 0 else "failed"

    def _on_timeout(self) -> None:
        self._timed_out = True
        self._kill()

    def _kill(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGTERM)
            else:
                proc.terminate()
        except OSError:
            return

        def hard_kill() -> None:
            if proc.poll() is None:
                try:
                    if hasattr(os, "killpg"):
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except OSError:
                    pass

        threading.Timer(3.0, hard_kill).start()

    def cancel(self) -> None:
        self._cancelled = True
        self._kill()

    def snapshot(self, since: int = 0, with_text: bool = True) -> dict:
        with self._lock:
            end = self.ended or time.time()
            data = {
                "id": self.id, "tool": self.tool, "kind": self.kind, "state": self.state,
                "rc": self.rc, "elapsed": round(end - self.started, 1),
                "truncated": self.truncated, "next": len(self.text),
                "done": self.state != "running",
            }
            if with_text:
                data["output"] = self.text[max(0, since):]
            return data


JOBS: dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()
MAX_JOBS = 64


def _prune_jobs() -> None:
    """Drop the oldest finished jobs (caller holds _JOBS_LOCK)."""
    if len(JOBS) < MAX_JOBS:
        return
    finished = sorted((j for j in JOBS.values() if j.ended), key=lambda j: j.ended)
    for job in finished[: max(1, len(JOBS) - MAX_JOBS + 8)]:
        JOBS.pop(job.id, None)


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
        expected = f"Bearer {self.token}"
        # Compare bytes: hmac.compare_digest raises TypeError on non-ASCII str.
        return bool(self.token) and hmac.compare_digest(
            header.encode("utf-8"), expected.encode("utf-8")
        )

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
        if self.path.startswith("/jobs/"):
            path, _, query = self.path.partition("?")
            since = 0
            for pair in query.split("&"):
                if pair.startswith("since=") and pair[6:].isdigit():
                    since = int(pair[6:])
            self._json(*self._job_get(path[len("/jobs/"):], since))
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
        elif path == "/jobs":
            self._json(*self._job_start(body))
        elif path.startswith("/jobs/") and path.endswith("/cancel"):
            self._json(*self._job_cancel(path[len("/jobs/"):-len("/cancel")]))
        elif path == "/tools/install":
            self._json(*self._apt(body, "install"))
        elif path == "/tools/remove":
            self._json(*self._apt(body, "remove"))
        else:
            self._json(404, {"error": "not found"})

    # --- operations -------------------------------------------------------
    def _prepare(self, body: dict):
        """Validate a run request: (tool_id, argv, timeout, None) or (None, None, None, error)."""
        def bad(status: int, payload: dict):
            return None, None, None, (status, payload)

        tool_id = str(body.get("tool", ""))
        meta = self.tools.get(tool_id)
        if meta is None:
            return bad(403, {"error": f"tool '{tool_id}' is not in the allowlist"})
        argv = body.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            return bad(400, {"error": "argv must be a non-empty list of strings"})
        if len(argv) > int(meta.get("max_args", 32)):
            return bad(400, {"error": "too many arguments"})
        expected = meta.get("binary", "")
        if argv[0] != expected:
            return bad(403, {"error": f"binary mismatch for '{tool_id}'"})
        for arg in argv:
            if not SAFE_ARG.fullmatch(arg):
                return bad(400, {"error": "argument contains a forbidden character"})
        if not binary_present(expected):
            return bad(409, {"error": f"{expected} is not installed",
                             "detail": "Install it from the Tool manager first."})
        # Every host-bearing field is checked: the server sends "target" and "url" both.
        targets = body.get("targets")
        if not isinstance(targets, list):
            targets = [body.get("target", ""), body.get("url", "")]
        for target in targets:
            allowed, reason = in_scope(str(target or ""), body.get("confirm_external") is True)
            if not allowed:
                return bad(403, {"error": "target is out of scope", "detail": reason})
        timeout = int(body.get("timeout") or DEFAULT_TIMEOUT)
        return tool_id, argv, max(5, min(timeout, MAX_TIMEOUT)), None

    def _run(self, body: dict):
        tool_id, argv, timeout, error = self._prepare(body)
        if error is not None:
            return error
        log(f"run {tool_id}: {shlex.join(argv)}")
        result = run_argv(argv, timeout)
        result["argv"] = argv
        result["tool"] = tool_id
        return 200, result

    # --- jobs (streamed, cancellable) -------------------------------------
    def _job_start(self, body: dict):
        kind = str(body.get("kind", "run"))
        if kind == "run":
            tool_id, argv, timeout, error = self._prepare(body)
            if error is not None:
                return error
            log(f"job run {tool_id}: {shlex.join(argv)}")
            job = Job(tool_id, "run", [argv], timeout)
        elif kind in ("install", "remove"):
            tool_id = str(body.get("tool", ""))
            steps, error = self._apt_steps(tool_id, kind)
            if error is not None:
                return error
            job = Job(tool_id, kind, steps, MAX_TIMEOUT * 2)
        else:
            return 400, {"error": "unknown job kind"}
        job.start()
        return 202, {"job": job.id, "kind": job.kind, "tool": job.tool}

    def _job_get(self, job_id: str, since: int):
        job = JOBS.get(job_id)
        if job is None:
            return 404, {"error": "unknown job"}
        return 200, job.snapshot(since)

    def _job_cancel(self, job_id: str):
        job = JOBS.get(job_id)
        if job is None:
            return 404, {"error": "unknown job"}
        job.cancel()
        return 200, job.snapshot(0, with_text=False)

    def _apt_steps(self, tool_id: str, action: str):
        meta = self.tools.get(tool_id)
        if meta is None:
            return None, (403, {"error": f"tool '{tool_id}' is not known"})
        custom = meta.get("install_steps" if action == "install" else "remove_steps")
        if custom:
            steps = [s for s in custom if isinstance(s, list) and s and all(
                isinstance(a, str) and SAFE_ARG.fullmatch(a) for a in s)]
            if len(steps) != len(custom):
                return None, (400, {"error": f"malformed {action} steps for '{tool_id}'"})
            return steps, None
        packages = meta.get("packages") or []
        if not packages:
            return None, (400, {"error": "this tool has no packages to manage"})
        for package in packages:
            if not re.match(r"^[a-z0-9][a-z0-9+.\-]{0,80}$", package):
                return None, (400, {"error": f"refusing suspicious package name: {package}"})
        if action == "install":
            steps = [
                ["apt-get", "update", "-qq"],
                ["apt-get", "install", "-y", "--no-install-recommends", *packages],
            ]
        else:
            steps = [
                ["apt-get", "remove", "-y", "--purge", *packages],
                ["apt-get", "-y", "autoremove", "--purge"],
            ]
        return steps, None

    def _apt(self, body: dict, action: str):
        tool_id = str(body.get("tool", ""))
        steps, error = self._apt_steps(tool_id, action)
        if error is not None:
            return error
        packages = self.tools[tool_id].get("packages") or []
        verb = "installed" if action == "install" else "removed"
        message = f"{verb}: {', '.join(packages)}"
        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")

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


class _Server(ThreadingHTTPServer):
    """One daemon thread per request; loopback only, so no pool is needed."""

    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    env = load_env()
    Handler.token = env.get("AGENT_TOKEN", "")
    Handler.tools = load_tools()

    if not Handler.token:
        print("refusing to start: no AGENT_TOKEN configured", file=sys.stderr)
        return 2

    port = int(env.get("KALISUB_PORT", "5055"))
    server = _Server(("127.0.0.1", port), Handler)
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
