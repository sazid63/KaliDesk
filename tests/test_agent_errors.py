"""Runtime agent errors become messages a user can act on."""
from __future__ import annotations

import io
import urllib.error

import server.tools as tools


def _http(code: int, body: bytes):
    return urllib.error.HTTPError("http://agent", code, "x", {}, io.BytesIO(body))


def test_unknown_job_is_a_plain_message_without_raw_json():
    body, status = tools._agent_error(_http(404, b'{"error": "unknown job"}'))
    assert status == 404 and "no longer available" in body["error"] and "detail" not in body


def test_agent_message_is_used_when_present():
    body, status = tools._agent_error(_http(400, b'{"error": "tool is not on the allowlist"}'))
    assert status == 400 and body["error"] == "tool is not on the allowlist"


def test_unreadable_body_falls_back_to_the_status_code():
    body, status = tools._agent_error(_http(500, b"<html>oops</html>"))
    assert status == 500 and body["error"] == "the runtime refused the request (500)"


def test_unreachable_runtime_is_503():
    body, status = tools._agent_error(OSError("connection refused"))
    assert status == 503 and body["error"] == "the runtime is not reachable"
