"""Findings from the browser: validation, and deleting one."""
from __future__ import annotations

HEADERS = {"X-KWS-CSRF": "test-csrf"}


def _finding(**overrides):
    body = {"tool": "nmap", "target": "127.0.0.1", "severity": "high", "title": "Open port", "detail": ""}
    body.update(overrides)
    return body


def test_title_is_required(client):
    resp = client.post("/api/findings", json=_finding(title="   "), headers=HEADERS)
    assert resp.status_code == 400 and "title" in resp.get_json()["error"]


def test_unknown_severity_is_refused(client):
    resp = client.post("/api/findings", json=_finding(severity="URGENT!!"), headers=HEADERS)
    assert resp.status_code == 400 and "severity" in resp.get_json()["error"]


def test_overlong_fields_are_refused(client):
    resp = client.post("/api/findings", json=_finding(title="x" * 201), headers=HEADERS)
    assert resp.status_code == 400 and "200" in resp.get_json()["error"]


def test_non_text_fields_are_refused(client):
    resp = client.post("/api/findings", json=_finding(detail=["a"]), headers=HEADERS)
    assert resp.status_code == 400


def test_valid_finding_is_saved_trimmed_and_can_be_deleted(client):
    resp = client.post("/api/findings", json=_finding(title="  Trim me  "), headers=HEADERS)
    assert resp.status_code == 200
    fid = resp.get_json()["id"]
    saved = [f for f in client.get("/api/findings").get_json()["findings"] if f["id"] == fid]
    assert saved and saved[0]["title"] == "Trim me"
    gone = client.delete(f"/api/findings/{fid}", headers=HEADERS)
    assert gone.status_code == 200 and gone.get_json()["ok"] is True
    again = client.delete(f"/api/findings/{fid}", headers=HEADERS)
    assert again.status_code == 404


def test_delete_needs_csrf(client):
    resp = client.post("/api/findings", json=_finding(), headers=HEADERS)
    fid = resp.get_json()["id"]
    assert client.delete(f"/api/findings/{fid}").status_code == 403
