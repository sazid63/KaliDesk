"""A deliberately vulnerable practice target.

A small web app runs on 127.0.0.1:3000 *inside* the private WSL2 runtime, so you can point
sqlmap, nikto, ffuf, whatweb, gobuster and friends at something you are allowed to attack.
WSL2 forwards the port, so it is reachable from Windows at http://127.0.0.1:3000 too.

Weaknesses (all contained in an in-memory database and one scratch folder):

* ``/sqli?id=1``       SQL injection (real SQLite, string-concatenated query)
* ``/xss?name=x``      reflected XSS (HTML page, input not escaped)
* ``/file?name=a.txt`` path traversal, but only inside the playground folder
                       (``../secret.txt`` works; ``/etc/passwd`` and the agent token do not)
* ``/token``           predictable session token
* ``/login``           weak login (admin / admin) for hydra and friends

It never reads anything outside ``/tmp/kalisub-playground``.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

import server.config as _cfg

PORT = 3000
APP_DIR = "/opt/kalisub-playground"
APP_PATH = f"{APP_DIR}/vulnerable_app.py"
LOG_PATH = "/tmp/kalisub-playground.log"

# Runs inside the distro with the system python3. Plain str (no f-string), so braces are safe.
VULNERABLE_APP_SOURCE = r'''
import html
import http.server
import json
import os
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

ROOT = os.path.realpath(os.environ.get("KWS_PLAYGROUND_ROOT", "/tmp/kalisub-playground"))
PORT = int(os.environ.get("KWS_PLAYGROUND_PORT", "3000"))
PUBLIC = os.path.join(ROOT, "public")
os.makedirs(PUBLIC, exist_ok=True)
with open(os.path.join(PUBLIC, "a.txt"), "w") as f:
    f.write("hello from the playground\n")
with open(os.path.join(ROOT, "secret.txt"), "w") as f:
    f.write("FLAG{path-traversal-works}\n")

DB = sqlite3.connect(":memory:", check_same_thread=False)
DB.execute("CREATE TABLE users (id INTEGER, name TEXT, secret TEXT)")
DB.executemany("INSERT INTO users VALUES (?,?,?)", [
    (1, "alice", "alice-password"), (2, "bob", "bob-password"),
    (3, "admin", "FLAG{sql-injection}")])
DB.commit()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/sqli":
            # VULNERABLE: the id is pasted into the query.
            sql = "SELECT id, name FROM users WHERE id = " + q.get("id", "1")
            try:
                rows = DB.execute(sql).fetchall()
                self.send(200, json.dumps({"rows": rows}))
            except sqlite3.Error as exc:
                self.send(500, json.dumps({"error": str(exc), "query": sql}))
        elif url.path == "/xss":
            # VULNERABLE: the name is reflected without escaping.
            page = "<html><body><h1>Hello, " + q.get("name", "world") + "</h1></body></html>"
            self.send(200, page, "text/html")
        elif url.path == "/file":
            # VULNERABLE to ../ but confined to ROOT so nothing else on the machine is exposed.
            path = os.path.realpath(os.path.join(PUBLIC, q.get("name", "a.txt")))
            if not path.startswith(ROOT + os.sep):
                self.send(403, json.dumps({"error": "outside the playground"}))
            elif os.path.isfile(path):
                self.send(200, open(path, errors="replace").read(400), "text/plain")
            else:
                self.send(404, json.dumps({"error": "not found"}))
        elif url.path == "/token":
            self.send(200, json.dumps({"token": str(int(time.time()) % 100000).zfill(5)}))
        elif url.path == "/login":
            ok = q.get("user") == "admin" and q.get("password") == "admin"
            self.send(200 if ok else 401, json.dumps({"ok": ok}))
        else:
            self.send(200, json.dumps({"endpoints": [
                "/sqli?id=1", "/xss?name=x", "/file?name=a.txt", "/token",
                "/login?user=admin&password=admin"]}))


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
'''


def _distro(argv: list[str], timeout: int = 30, stdin_text: str | None = None):
    from app import runtime

    return runtime.in_distro(_cfg.load(), argv, timeout=timeout, stdin_text=stdin_text)


# The playground's index page lists this endpoint. Any other program on port 3000 will not.
PLAYGROUND_MARKER = "/sqli?id=1"


def is_running() -> bool:
    """True only if the server on the port is this playground, not some other listener."""
    try:
        body = urllib.request.urlopen(  # noqa: S310
            f"http://127.0.0.1:{PORT}/", timeout=3
        ).read(65536)
    except OSError:
        return False
    try:
        listed = json.loads(body.decode("utf-8", errors="replace")).get("endpoints", [])
    except (ValueError, AttributeError):
        return False
    return PLAYGROUND_MARKER in listed


def start_playground() -> tuple[bool, str]:
    if is_running():
        return True, f"Playground already running on http://127.0.0.1:{PORT}"
    rc, out, err = _distro(
        ["sh", "-c", 'mkdir -p "$1" && cat > "$2"', "sh", APP_DIR, APP_PATH],
        stdin_text=VULNERABLE_APP_SOURCE,
    )
    if rc != 0:
        return False, f"could not install the playground: {(err or out).strip()[:300]}"
    # setsid + nohup so it keeps running after this short wsl session ends. The trailing sleep
    # matters: if the shell exits at once, WSL ends the session before the job has started
    # (found on a real distro: the app never launched and no log file appeared).
    rc, out, err = _distro(
        ["sh", "-c", f"setsid nohup python3 {APP_PATH} >{LOG_PATH} 2>&1 < /dev/null & sleep 1"]
    )
    if rc != 0:
        return False, f"could not start the playground: {(err or out).strip()[:300]}"
    for _ in range(10):
        time.sleep(0.5)
        if is_running():
            return True, f"Playground started on http://127.0.0.1:{PORT}"
    _, log, _ = _distro(["tail", "-n", "20", LOG_PATH])
    return False, f"the playground did not start. Log: {log.strip()[:300] or '(empty)'}"


def stop_playground() -> tuple[bool, str]:
    _distro(["pkill", "-f", "vulnerable_app.py"])
    for _ in range(6):
        if not is_running():
            return True, "Playground stopped"
        time.sleep(0.5)
    return False, "the playground is still answering"


def get_status() -> dict[str, Any]:
    running = is_running()
    return {
        "running": running,
        "port": PORT,
        "url": f"http://127.0.0.1:{PORT}" if running else None,
    }
