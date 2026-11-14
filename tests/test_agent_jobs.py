"""The in-runtime agent's streamed, cancellable jobs, exercised over real HTTP."""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from conftest import wait_until

AGENT_PATH = Path(__file__).resolve().parent.parent / "runtime" / "agent" / "agent.py"
TOKEN = "agent-test-token"


@pytest.fixture(scope="module")
def agent():
    spec = importlib.util.spec_from_file_location("kalisub_agent_jobs", AGENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def live(agent, monkeypatch):
    monkeypatch.setattr(agent, "binary_present", lambda binary: True)
    handler = type("H", (agent.Handler,), {
        "token": TOKEN,
        "tools": {"py": {"id": "py", "binary": sys.executable, "max_args": 8}},
    })
    server = agent._Server(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {TOKEN}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    yield call
    server.shutdown()


def _start(call, code, timeout=30):
    status, body = call("POST", "/jobs", {
        "kind": "run", "tool": "py", "argv": [sys.executable, "-u", "-c", code],
        "target": "", "timeout": timeout,
    })
    assert status == 202, body
    return body["job"]


def _wait(call, job, want_done=True, limit=15):
    end = time.time() + limit
    while time.time() < end:
        _, snap = call("GET", f"/jobs/{job}")
        if snap["done"] == want_done:
            return snap
        time.sleep(0.1)
    raise AssertionError("job did not reach the expected state")


def test_job_streams_output_incrementally(live):
    job = _start(live, "import time; print('one', flush=True); time.sleep(1.5); print('two')")
    seen = ""
    first_chunk_before_done = False
    nxt = 0
    end = time.time() + 15
    while time.time() < end:
        _, snap = live("GET", f"/jobs/{job}?since={nxt}")
        seen += snap["output"]
        nxt = snap["next"]
        if "one" in seen and not snap["done"]:
            first_chunk_before_done = True
        if snap["done"]:
            break
        time.sleep(0.1)
    assert first_chunk_before_done, "output must be visible while the job is still running"
    assert "one" in seen and "two" in seen
    assert snap["state"] == "done" and snap["rc"] == 0


def test_job_reports_failure_rc(live):
    job = _start(live, "import sys; print('bad'); sys.exit(3)")
    snap = _wait(live, job)
    assert snap["state"] == "failed" and snap["rc"] == 3 and "bad" in snap["output"]


def test_job_cancel_stops_process_and_keeps_partial_output(live):
    job = _start(live, "import time; print('started', flush=True); time.sleep(60)")
    wait_until(lambda: "started" in live("GET", f"/jobs/{job}")[1]["output"])
    status, _ = live("POST", f"/jobs/{job}/cancel")
    assert status == 200
    snap = _wait(live, job)
    assert snap["state"] == "cancelled"
    assert "started" in snap["output"]
    assert snap["elapsed"] < 30


def test_job_timeout_keeps_partial_output(live):
    job = _start(live, "import time; print('partial', flush=True); time.sleep(60)", timeout=5)
    snap = _wait(live, job, limit=30)
    assert snap["state"] == "timeout"
    assert "partial" in snap["output"] and "timed out" in snap["output"]


def test_job_unknown_and_unauthorised(live, agent):
    assert live("GET", "/jobs/doesnotexist")[0] == 404
    assert live("POST", "/jobs", {"kind": "run", "tool": "nope", "argv": ["x"]})[0] == 403
    assert live("POST", "/jobs", {"kind": "weird"})[0] == 400


def test_job_rejects_out_of_scope_target(live):
    status, body = live("POST", "/jobs", {
        "kind": "run", "tool": "py", "argv": [sys.executable, "-c", "print(1)"],
        "target": "8.8.8.8",
    })
    assert status == 403 and "scope" in body["error"]


def test_agent_checks_the_url_field_too(live):
    # The private "target" must not let a public "url" through.
    status, body = live("POST", "/jobs", {
        "kind": "run", "tool": "py", "argv": [sys.executable, "-c", "print(1)"],
        "target": "127.0.0.1", "url": "http://8.8.8.8/",
    })
    assert status == 403 and "scope" in body["error"]


def test_job_output_is_capped(agent):
    job = agent.Job("py", "run", [[sys.executable, "-c", "print('x' * 2_000_000)"]], 30)
    job.start()
    end = time.time() + 20
    while time.time() < end and not job.snapshot(0, with_text=False)["done"]:
        time.sleep(0.1)
    snap = job.snapshot(0)
    assert snap["truncated"] is True
    assert len(snap["output"]) <= agent.MAX_OUTPUT
