"""Skipping the onboarding guide is remembered; finishing it still records consent."""
from __future__ import annotations

HEADERS = {"X-KWS-CSRF": "test-csrf"}


def test_skip_is_remembered_but_guide_stays_needed(client):
    before = client.get("/api/onboarding/status").get_json()
    assert before["skipped"] is False
    assert client.post("/api/onboarding/skip", headers=HEADERS).status_code == 200
    after = client.get("/api/onboarding/status").get_json()
    assert after["skipped"] is True
    assert after["needed"] is True


def test_skip_needs_csrf(client):
    assert client.post("/api/onboarding/skip").status_code == 403


def test_finishing_still_requires_acceptance(client):
    resp = client.post("/api/onboarding/finish", json={"accepted": False}, headers=HEADERS)
    assert resp.status_code == 400
