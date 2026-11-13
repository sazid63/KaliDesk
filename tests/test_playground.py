"""The practice target really is vulnerable, and only to what it should be."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

import server.playground as pg


@pytest.fixture(scope="module")
def target(tmp_path_factory):
    root = tmp_path_factory.mktemp("playground")
    script = root / "app.py"
    script.write_text(pg.VULNERABLE_APP_SOURCE, encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "KWS_PLAYGROUND_ROOT": str(root / "data"), "KWS_PLAYGROUND_PORT": str(port)}
    proc = subprocess.Popen([sys.executable, str(script)], env=env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/", timeout=1).read()
            break
        except OSError:
            time.sleep(0.2)
    yield base, root / "data"
    proc.kill()


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_sql_injection_is_real(target):
    base, _ = target
    assert json.loads(get(base, "/sqli?id=1")[1])["rows"] == [[1, "alice"]]
    dump = json.loads(get(base, "/sqli?id=1%20OR%201=1")[1])["rows"]
    assert len(dump) == 3
    union = json.loads(get(base, "/sqli?id=0%20UNION%20SELECT%20id,secret%20FROM%20users")[1])
    assert any("FLAG{sql-injection}" in row for row in union["rows"])
    status, body = get(base, "/sqli?id='")
    assert status == 500 and "query" in body  # verbose errors help sqlmap detect it


def test_reflected_xss(target):
    base, _ = target
    assert "<script>alert(1)</script>" in get(base, "/xss?name=<script>alert(1)</script>")[1]


def test_traversal_reaches_the_secret_but_nothing_outside(target):
    base, root = target
    assert "hello" in get(base, "/file?name=a.txt")[1]
    assert "FLAG{path-traversal-works}" in get(base, "/file?name=../secret.txt")[1]
    outside = root.parent / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    for evil in ("../../outside.txt", "../../../../../../etc/passwd",
                 "..%5c..%5c..%5cWindows%5cwin.ini", str(outside)):
        status, body = get(base, "/file?name=" + evil)
        assert status in (403, 404) and "private" not in body, evil


def test_weak_token_and_login(target):
    base, _ = target
    assert len(json.loads(get(base, "/token")[1])["token"]) == 5
    assert get(base, "/login?user=admin&password=admin")[0] == 200
    assert get(base, "/login?user=admin&password=x")[0] == 401


def test_start_uses_the_runtime_not_windows_paths(monkeypatch):
    from app import runtime

    calls = []

    def fake(cfg, argv, timeout=60, stdin_text=None):
        calls.append((argv, stdin_text))
        return 0, "", ""

    monkeypatch.setattr(runtime, "in_distro", fake)
    monkeypatch.setattr(pg, "is_running", lambda: len(calls) >= 2)
    ok, message = pg.start_playground()
    assert ok, message
    assert calls[0][1] == pg.VULNERABLE_APP_SOURCE and pg.APP_PATH in calls[0][0][-1]
    assert "setsid" in calls[1][0][-1] and calls[1][0][-1].endswith("& sleep 1")


def test_source_has_no_undefined_names():
    compile(pg.VULNERABLE_APP_SOURCE, "vulnerable_app.py", "exec")
    assert "agent.env" not in pg.VULNERABLE_APP_SOURCE
