"""Tests for portable mode endpoints."""
import json
import os
from pathlib import Path

import pytest


def test_portable_drives_endpoint(client):
    """GET /api/portable/drives returns a list (may be empty on CI)."""
    resp = client.get("/api/portable/drives")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "drives" in data
    assert isinstance(data["drives"], list)


def test_portable_status_endpoint(client, tmp_path):
    """GET /api/portable/status reports portable mode correctly."""
    # Create a mock portable marker
    marker = tmp_path / "kws_portable.json"
    marker.write_text(json.dumps({
        "version": "1.0",
        "created": "2025-01-01T00:00:00",
        "original_data_dir": str(tmp_path / "original"
    )}))

    # Override the default user data dir for this test
    import server.portable as portable_module
    original_dir = portable_module.DEFAULT_USER_DATA_DIR
    portable_module.DEFAULT_USER_DATA_DIR = tmp_path
    try:
        resp = client.get("/api/portable/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["portable"] is True
        assert data["location"] == str(tmp_path)
        assert data["created"] == "2025-01-01T00:00:00"
    finally:
        portable_module.DEFAULT_USER_DATA_DIR = original_dir


def test_portable_status_no_marker(client, tmp_path):
    """GET /api/portable/status returns portable: false when no marker."""
    import server.portable as portable_module
    original_dir = portable_module.DEFAULT_USER_DATA_DIR
    portable_module.DEFAULT_USER_DATA_DIR = tmp_path
    try:
        resp = client.get("/api/portable/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["portable"] is False
    finally:
        portable_module.DEFAULT_USER_DATA_DIR = original_dir


def test_portable_switch_missing_path(client):
    """POST /api/portable/switch requires a path."""
    resp = client.post(
        "/api/portable/switch",
        json={},
        headers={"X-KWS-CSRF": "test-csrf"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_portable_switch_nonexistent_path(client):
    """POST /api/portable/switch fails for nonexistent path."""
    resp = client.post(
        "/api/portable/switch",
        json={"path": "Z:\\nonexistent"},
        headers={"X-KWS-CSRF": "test-csrf"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data