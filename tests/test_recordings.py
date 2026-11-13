"""Run transcripts: saved automatically, listed, viewed, deleted, and traversal-proof."""
from __future__ import annotations

import pytest

import server.recordings as recordings


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(recordings, "_dir", lambda: tmp_path)
    return tmp_path


def save(tool="nmap", output="hello\n", **kw):
    return recordings.save_transcript(
        tool, kw.get("target", "10.0.0.1"), ["nmap", "-sn", "10.0.0.1"], output,
        kw.get("rc", 0), kw.get("state", "done"), kw.get("elapsed", 1.5),
    )


def test_transcript_metadata_redacts_passwords_in_the_command():
    rid = recordings.save_transcript(
        "hydra", "10.0.0.1",
        ["hydra", "-l", "root", "--password", "hunter2", "--passphrase=s3cret", "ssh://10.0.0.1"],
        "", 0, "done", 1.0,
    )
    argv = recordings.load_recording(rid)["meta"]["argv"]
    assert "hunter2" not in argv and "s3cret" not in argv
    assert argv[:3] == ["hydra", "-l", "root"] and "ssh://10.0.0.1" in argv


def test_save_list_load_delete():
    rid = save(output="scan done\n")
    assert recordings.valid_id(rid) and rid.startswith("nmap_")
    rows = recordings.list_recordings()
    assert [r["id"] for r in rows] == [rid]
    assert rows[0]["duration_ms"] == 1500 and rows[0]["size_bytes"] == len("scan done\n")
    found = recordings.load_recording(rid)
    assert found["text"] == "scan done\n" and found["meta"]["argv"][0] == "nmap"
    assert recordings.delete_recording(rid) is True
    assert recordings.list_recordings() == []
    assert recordings.load_recording(rid) is None


def test_tool_ids_with_hyphens_work():
    assert recordings.valid_id(save("aircrack-ng"))


@pytest.mark.parametrize("bad", [
    "../x", "..\\x", "a/b", "nmap_20261110_140620_zzzzzzzz", "", "x" * 200, "C:\\win\\a",
    "nmap_20261110_140620_ab12cd34/../../evil",
])
def test_ids_are_strict(bad, isolated):
    assert not recordings.valid_id(bad)
    assert recordings.load_recording(bad) is None
    assert recordings.delete_recording(bad) is False


def test_hostile_tool_names_cannot_escape_the_folder(isolated):
    rid = save("../../evil\\name")
    assert recordings.valid_id(rid)
    assert all(p.parent == isolated for p in isolated.iterdir())


def test_output_is_capped():
    rid = save(output="x" * (recordings.MAX_LOG_BYTES + 5000))
    assert recordings.list_recordings()[0]["size_bytes"] == recordings.MAX_LOG_BYTES
    assert len(recordings.load_recording(rid)["text"]) == recordings.MAX_LOG_BYTES


def test_only_the_newest_are_kept(monkeypatch):
    monkeypatch.setattr(recordings, "MAX_KEPT", 3)
    ids = [save(output=str(i)) for i in range(6)]
    kept = {r["id"] for r in recordings.list_recordings()}
    assert len(kept) == 3 and kept <= set(ids)


def test_routes_and_download(client):
    rid = save(output="route output")
    listing = client.get("/api/recordings").get_json()["recordings"]
    assert any(r["id"] == rid for r in listing)
    assert client.get(f"/api/recordings/{rid}").get_json()["text"] == "route output"
    dl = client.get(f"/api/recordings/{rid}?download=1")
    assert dl.data == b"route output" and "attachment" in dl.headers["Content-Disposition"]
    assert client.get("/api/recordings/not-a-real-id").status_code == 404
    assert client.delete(f"/api/recordings/{rid}", headers={"X-KWS-CSRF": "test-csrf"}).get_json()[
        "ok"] is True
    assert client.delete(f"/api/recordings/{rid}").status_code == 403  # CSRF required
