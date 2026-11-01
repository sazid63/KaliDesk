"""Tests for the notebook API endpoints."""
from __future__ import annotations

import pytest


def test_add_and_list_entries(client):
    # Add entries via API
    resp = client.post("/api/notebook/entries", json={
        "type": "finding",
        "content": "test finding unique1",
        "tags": ["phishing", "tool"]
    }, headers={"X-KWS-CSRF": "test-csrf"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    nid = data["id"]

    # List entries
    resp = client.get("/api/notebook/entries")
    assert resp.status_code == 200
    entries = resp.get_json()["entries"]
    # Find our entry (there may be others from prior tests)
    e = next((x for x in entries if x["id"] == nid), None)
    assert e is not None
    assert e["type"] == "finding"
    assert e["content"] == "test finding unique1"
    assert e["tags"] == ["phishing", "tool"]


def test_list_filter_by_type(client):
    client.post("/api/notebook/entries", json={"type": "finding", "content": "f1 unique2", "tags": []}, headers={"X-KWS-CSRF": "test-csrf"})
    client.post("/api/notebook/entries", json={"type": "note", "content": "n1 unique2", "tags": []}, headers={"X-KWS-CSRF": "test-csrf"})
    client.post("/api/notebook/entries", json={"type": "finding", "content": "f2 unique2", "tags": []}, headers={"X-KWS-CSRF": "test-csrf"})

    resp = client.get("/api/notebook/entries?type=finding")
    assert resp.status_code == 200
    findings = resp.get_json()["entries"]
    # At least 2 findings (f1, f2) plus any from prior tests
    assert len(findings) >= 2
    # Verify our specific entries are present
    contents = {e["content"] for e in findings}
    assert "f1 unique2" in contents
    assert "f2 unique2" in contents

    resp = client.get("/api/notebook/entries?type=note")
    assert resp.status_code == 200
    notes = resp.get_json()["entries"]
    contents = {e["content"] for e in notes}
    assert "n1 unique2" in contents


def test_list_filter_by_tags(client):
    client.post("/api/notebook/entries", json={"type": "finding", "content": "f1 unique3", "tags": ["phishing", "tool"]}, headers={"X-KWS-CSRF": "test-csrf"})
    client.post("/api/notebook/entries", json={"type": "finding", "content": "f2 unique3", "tags": ["malware", "analysis"]}, headers={"X-KWS-CSRF": "test-csrf"})
    client.post("/api/notebook/entries", json={"type": "note", "content": "n1 unique3", "tags": ["analysis"]}, headers={"X-KWS-CSRF": "test-csrf"})

    resp = client.get("/api/notebook/entries?tags=phishing")
    assert resp.status_code == 200
    phishing = resp.get_json()["entries"]
    # At least 1 entry with phishing tag
    assert len(phishing) >= 1
    assert any(e["content"] == "f1 unique3" for e in phishing)

    resp = client.get("/api/notebook/entries?tags=analysis")
    assert resp.status_code == 200
    analysis = resp.get_json()["entries"]
    assert len(analysis) >= 2
    contents = {e["content"] for e in analysis}
    assert "f2 unique3" in contents
    assert "n1 unique3" in contents


def test_search_entries(client):
    client.post("/api/notebook/entries", json={"type": "finding", "content": "shellcode unique4 detected", "tags": []}, headers={"X-KWS-CSRF": "test-csrf"})
    client.post("/api/notebook/entries", json={"type": "finding", "content": "port scan unique4", "tags": []}, headers={"X-KWS-CSRF": "test-csrf"})
    client.post("/api/notebook/entries", json={"type": "note", "content": "shellcode unique4 in binary", "tags": []}, headers={"X-KWS-CSRF": "test-csrf"})

    resp = client.get("/api/notebook/search?q=shellcode unique4")
    assert resp.status_code == 200
    found = resp.get_json()["entries"]
    assert len(found) >= 2
    contents = {e["content"] for e in found}
    assert "shellcode unique4 detected" in contents
    assert "shellcode unique4 in binary" in contents


def test_delete_entry(client):
    resp = client.post("/api/notebook/entries", json={"type": "finding", "content": "to delete unique5", "tags": []}, headers={"X-KWS-CSRF": "test-csrf"})
    nid = resp.get_json()["id"]

    # Delete
    resp = client.delete(f"/api/notebook/entries/{nid}", headers={"X-KWS-CSRF": "test-csrf"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    # Delete again (should be False)
    resp = client.delete(f"/api/notebook/entries/{nid}", headers={"X-KWS-CSRF": "test-csrf"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is False

    # Verify gone
    resp = client.get("/api/notebook/entries")
    assert resp.status_code == 200
    entries = resp.get_json()["entries"]
    assert not any(e["id"] == nid for e in entries)


def test_export_notebook(client):
    client.post("/api/notebook/entries", json={"type": "finding", "content": "f1 unique6", "tags": []}, headers={"X-KWS-CSRF": "test-csrf"})
    client.post("/api/notebook/entries", json={"type": "note", "content": "n1 unique6", "tags": []}, headers={"X-KWS-CSRF": "test-csrf"})
    client.post("/api/notebook/entries", json={"type": "ip", "content": "1.1.1.1", "tags": ["clean"]}, headers={"X-KWS-CSRF": "test-csrf"})

    resp = client.get("/api/notebook/export")
    assert resp.status_code == 200
    md = resp.get_json()["markdown"]
    assert "# OSINT Notebook Export" in md
    assert "f1 unique6" in md
    assert "n1 unique6" in md
    assert "1.1.1.1" in md
    assert "clean" in md