"""End to end: UI-facing job API -> Flask backend -> (real) agent over HTTP."""
from __future__ import annotations

import http.client
import importlib.util
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import wait_until

import kws.secrets as kws_secrets
import server.app as app_module
import server.config as config
import server.history as history
import server.tools as tools

AGENT_PATH = Path(__file__).resolve().parent.parent / "runtime" / "agent" / "agent.py"
CSRF = {"X-KWS-CSRF": "test-csrf"}


@pytest.fixture()
def stack(monkeypatch):
    spec = importlib.util.spec_from_file_location("kalisub_agent_api", AGENT_PATH)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    monkeypatch.setattr(agent, "binary_present", lambda binary: True)
    handler = type("H", (agent.Handler,), {
        "token": "agent-tok",
        "tools": {"dns": {"id": "dns", "binary": sys.executable, "max_args": 8}},
    })
    server = agent._Server(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    kws_secrets.set_secret("agent_token", "agent-tok")
    cfg = replace(config.load(), agent_url=f"http://127.0.0.1:{server.server_address[1]}")
    state = {"code": "print('hi')"}
    monkeypatch.setattr(
        tools, "_build",
        lambda tool_id, payload, work: ([sys.executable, "-u", "-c", state["code"]], None),
    )
    application = app_module.create_app(cfg, "test-token", "test-csrf")
    application.config.update(TESTING=True)
    client = application.test_client()
    client.set_cookie(application.config["KWS_AUTH_COOKIE"], "test-token")
    client.set_cookie(application.config["KWS_CSRF_COOKIE"], "test-csrf")
    yield client, state
    server.shutdown()


def _finish(client, job, limit=20):
    end = time.time() + limit
    since = 0
    out = ""
    while time.time() < end:
        snap = client.get(f"/api/jobs/{job}?since={since}").get_json()
        out += snap.get("output", "")
        since = snap["next"]
        if snap["done"]:
            return snap, out
        time.sleep(0.05)
    raise AssertionError("job never finished")


def _output_of(client, job, text):
    """Poll until the job has printed ``text`` (or it finishes)."""
    def seen():
        return text in client.get(f"/api/jobs/{job}?since=0").get_json().get("output", "")
    return wait_until(seen)


def test_start_poll_finish_records_history(stack):
    client, state = stack
    state["code"] = "print('scan result')"
    resp = client.post("/api/tool/dns/start", json={"target": "127.0.0.1"}, headers=CSRF)
    assert resp.status_code == 202
    job = resp.get_json()["job"]
    snap, out = _finish(client, job)
    assert snap["state"] == "done" and "scan result" in out
    # Polling again after completion must not record a second history row.
    client.get(f"/api/jobs/{job}")
    rows = [
        r for r in history.list_history(limit=50) if r["output_preview"].startswith("scan result")
    ]
    assert len(rows) == 1
    assert rows[0]["success"] in (1, True) and rows[0]["rc"] == 0


def test_cancel_via_api(stack):
    client, state = stack
    state["code"] = "import time; print('going', flush=True); time.sleep(60)"
    job = client.post(
        "/api/tool/dns/start", json={"target": "127.0.0.1"}, headers=CSRF
    ).get_json()["job"]
    _output_of(client, job, "going")
    assert client.post(f"/api/jobs/{job}/cancel", json={}, headers=CSRF).status_code == 200
    snap, out = _finish(client, job)
    assert snap["state"] == "cancelled" and "going" in out


def test_out_of_scope_target_is_refused_before_starting(stack):
    client, _ = stack
    resp = client.post("/api/tool/dns/start", json={"target": "8.8.8.8"}, headers=CSRF)
    assert resp.status_code == 403


def test_job_endpoints_require_auth_and_csrf(stack):
    client, _ = stack
    assert client.post("/api/tool/dns/start", json={}).status_code == 403
    assert client.post("/api/jobs/abc123/cancel", json={}).status_code == 403
    anonymous = app_module.create_app(config.load(), "t", "c").test_client()
    assert anonymous.get("/api/jobs/abc123").status_code == 401


def test_job_id_is_validated(stack):
    client, _ = stack
    assert client.get("/api/jobs/not-alnum!").status_code == 404
    # str.isalnum() accepts non-ASCII letters; job ids must be ASCII only.
    assert client.get("/api/jobs/été").status_code == 404


def test_every_host_field_is_scope_checked(stack):
    client, _ = stack
    # A private target with a public url must not pass as private.
    payload = {"target": "127.0.0.1", "url": "http://93.184.216.34/"}
    assert client.post("/api/tool/dns/start", json=payload, headers=CSRF).status_code == 403
    assert client.post("/api/tool/dns", json=payload, headers=CSRF).status_code == 403


@pytest.mark.parametrize(
    "failure",
    [http.client.RemoteDisconnected("gone"), KeyError("job"), OSError("unreachable")],
)
def test_secret_inputs_are_deleted_when_the_run_never_starts(stack, monkeypatch, failure):
    written: list[str] = []
    real_write = tools._write_inputs

    def spy(tool_id, payload, work):
        paths = real_write(tool_id, payload, work)
        written.extend(str(p) for p in paths)
        return paths

    def failing_post(cfg, path, body, timeout=30):
        raise failure

    monkeypatch.setattr(tools, "_write_inputs", spy)
    monkeypatch.setattr(tools, "_build", lambda tool_id, payload, work: (["true"], None))
    monkeypatch.setattr(tools, "agent_post", failing_post)
    cfg = replace(config.load(), agent_url="http://127.0.0.1:1")
    _, status = tools.start_job(
        cfg, "hydra", {"target": "127.0.0.1", "users": "root", "passwords": "hunter2"},
        user_confirmed=True,
    )
    assert status in (400, 503)
    assert written, "the run should have written its secret inputs"
    assert not any(Path(p).exists() for p in written)


def test_history_trim_keeps_newest_500():
    for i in range(505):
        history.record_run("trimtest", "", {}, 0, 1.0, f"n{i}", True)
    rows = history.list_history(limit=1000)
    assert len(rows) <= 500
    assert rows[0]["output_preview"] == "n504"


def test_external_target_needs_the_users_own_confirmation(stack):
    client, _ = stack
    payload = {"target": "8.8.8.8", "confirm_external": True}
    # From the UI route the user's tick is honoured ...
    assert client.post("/api/tool/dns/start", json=payload, headers=CSRF).status_code == 202
    # ... but an internal caller (AI, skill, MCP) cannot grant it to itself.
    cfg = replace(config.load(), agent_url="http://127.0.0.1:1")
    body, error = tools._prepare_run(cfg, "dns", payload, 30)
    assert body is None and error[1] == 403
    body, error = tools._prepare_run(cfg, "dns", payload, 30, user_confirmed=True)
    assert error is None and body["confirm_external"] is True


def test_history_never_stores_secrets():
    history.record_run(
        "hydra", "10.0.0.1",
        {"target": "10.0.0.1", "passwords": "hunter2", "users": "root", "passphrase": "s3cret"},
        0, 1.0, "", True,
    )
    row = history.list_history(limit=1, tool="hydra")[0]
    assert "hunter2" not in row["argv"] and "s3cret" not in row["argv"]
    assert "10.0.0.1" in row["argv"]
