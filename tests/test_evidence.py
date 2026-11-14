"""Adding files to the evidence folder from the browser."""
from __future__ import annotations

import io
from urllib.parse import quote

import pytest

import kws.paths as kws_paths
import server.evidence as evidence
import server.tools as tools

HEADERS = {"X-KWS-CSRF": "test-csrf"}


def _upload(client, name: str, body: bytes, headers=HEADERS):
    h = dict(headers)
    h["X-KWS-Filename"] = quote(name)
    return client.post("/api/evidence/upload", data=body, headers=h)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("capture.pcap", "capture.pcap"),
        ("C:\\Users\\me\\disk image.dd", "disk_image.dd"),
        ("../../etc/passwd", "passwd"),
        ("/etc/hostname", "hostname"),
        (".hidden", "hidden"),
        ("evil;rm -rf.txt", "evil_rm_-rf.txt"),
    ],
)
def test_safe_name_keeps_a_plain_name(raw, expected):
    assert evidence.safe_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", ".", "..", "/", "\\", "...."])
def test_safe_name_refuses_unusable_names(raw):
    with pytest.raises(evidence.UploadError):
        evidence.safe_name(raw)


def test_safe_name_caps_length_and_keeps_extension():
    name = evidence.safe_name("a" * 300 + ".img")
    assert len(name) <= evidence.MAX_NAME and name.endswith(".img")


def test_upload_is_listed_and_never_overwrites(client):
    first = _upload(client, "sample.bin", b"abc")
    assert first.status_code == 200 and first.get_json()["name"] == "sample.bin"
    second = _upload(client, "sample.bin", b"xyz")
    assert second.get_json()["name"] == "sample (2).bin"
    listed = client.get("/api/evidence").get_json()["files"]
    assert "sample.bin" in listed and "sample (2).bin" in listed
    assert (kws_paths.evidence_dir() / "sample.bin").read_bytes() == b"abc"


def test_upload_needs_csrf_and_auth(client):
    assert _upload(client, "x.txt", b"data", headers={}).status_code == 403


def test_empty_upload_is_refused_and_leaves_nothing(client):
    resp = _upload(client, "empty.txt", b"")
    assert resp.status_code == 400
    assert "empty" in resp.get_json()["error"]
    assert not (kws_paths.evidence_dir() / "empty.txt").exists()
    assert not any(p.name.startswith(evidence.TEMP_PREFIX) for p in kws_paths.evidence_dir().iterdir())


def test_oversize_upload_is_refused_and_cleaned_up(monkeypatch, client):
    monkeypatch.setattr(evidence, "MAX_UPLOAD", 10)
    resp = _upload(client, "big.bin", b"x" * 11)
    assert resp.status_code == 400
    assert not (kws_paths.evidence_dir() / "big.bin").exists()
    assert not any(p.name.startswith(evidence.TEMP_PREFIX) for p in kws_paths.evidence_dir().iterdir())


def test_temp_and_hidden_files_are_not_offered_to_tools(tmp_path, monkeypatch):
    folder = tmp_path
    (folder / "visible.cap").write_bytes(b"1")
    (folder / ".upload-abc").write_bytes(b"2")
    (folder / ".secret").write_bytes(b"3")
    monkeypatch.setattr(kws_paths, "evidence_dir", lambda: folder)
    assert tools.evidence_files() == ["visible.cap"]


def test_store_streams_from_a_file_object(tmp_path, monkeypatch):
    monkeypatch.setattr(kws_paths, "evidence_dir", lambda: tmp_path)
    assert evidence.store(io.BytesIO(b"hello"), "greeting.txt") == "greeting.txt"
    assert (tmp_path / "greeting.txt").read_bytes() == b"hello"
