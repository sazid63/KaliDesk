"""Tests for the recordings module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import server.recordings as recordings


@pytest.fixture
def rec_dir(tmp_path: Path):
    """Redirect recordings directory to a temp folder."""
    original = recordings._RECORDINGS_DIR
    recordings._RECORDINGS_DIR = tmp_path / "recordings"
    recordings._RECORDINGS_DIR.mkdir()
    yield recordings._RECORDINGS_DIR
    recordings._RECORDINGS_DIR = original


def test_start_and_stop(rec_dir):
    rid = recordings.start_recording("nmap", {"target": "10.0.0.1"})
    assert isinstance(rid, str) and len(rid) > 0
    meta = json.loads((rec_dir / f"{rid}.meta.json").read_text())
    assert meta["tool"] == "nmap"
    assert meta["ended"] is None

    ok = recordings.stop_recording(rid)
    assert ok is True
    meta = json.loads((rec_dir / f"{rid}.meta.json").read_text())
    assert meta["ended"] is not None


def test_append_and_load(rec_dir):
    rid = recordings.start_recording("nmap", {})
    recordings.append_recording(rid, '{"line":"scan done"}')
    lines = recordings.load_recording(rid)
    assert lines == ['{"line":"scan done"}']


def test_list_recordings_uses_limit(rec_dir):
    """list_recordings should respect the limit parameter."""
    ids = []
    for i in range(5):
        r = recordings.start_recording("test", {})
        ids.append(r)

    all_list = recordings.list_recordings(limit=1000)
    assert len(all_list) == 5

    limited = recordings.list_recordings(limit=2)
    assert len(limited) == 2


def test_load_recording_with_bad_id_returns_empty(rec_dir):
    # A completely made-up id should not crash and should return [].
    result = recordings.load_recording("does-not-exist")
    assert result == []


def test_nonexistent_recording_is_noop(rec_dir):
    ok = recordings.stop_recording("missing")
    assert ok is False
