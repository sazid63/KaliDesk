"""Backup and restore: round trip, and hostile archives are refused."""
from __future__ import annotations

import io
import json
import zipfile

import pytest

import kws.paths as kws_paths
import server.backup as backup
import server.db as db

HEADERS = {"X-KWS-CSRF": "test-csrf"}


@pytest.fixture(autouse=True)
def init():
    db.init_db()


def zip_of(files: dict[str, bytes], manifest=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if manifest:
            z.writestr("manifest.json", json.dumps({"app": "kali-windows-substitute"}))
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_round_trip_restores_data_and_files():
    db.add_finding("nmap", "10.0.0.1", "high", "open telnet")
    (kws_paths.evidence_dir() / "keep.txt").write_text("evidence", encoding="utf-8")
    blob = backup.export_zip()
    names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
    assert {"manifest.json", "kws.sqlite3", "evidence/keep.txt"} <= set(names)
    assert not any("secret" in n or n.startswith("wsl") for n in names)

    with db.connect() as conn:
        conn.execute("DELETE FROM findings")
    (kws_paths.evidence_dir() / "keep.txt").unlink()
    result = backup.import_zip(blob)
    assert result["ok"], result
    assert any(f["title"] == "open telnet" for f in db.findings())
    assert (kws_paths.evidence_dir() / "keep.txt").read_text(encoding="utf-8") == "evidence"
    assert kws_paths.db_path().with_name("kws.sqlite3.before-restore").exists()


@pytest.mark.parametrize("name", [
    "../evil.txt", "evidence/../../evil.txt", "/abs.txt", "evidence//x", "secrets/key.bin",
    "wsl/ext4.vhdx", "C:/x.txt", "evidence/a:b", "kws.sqlite3.evil",
])
def test_hostile_member_names_are_refused(name):
    blob = zip_of({"kws.sqlite3": b"x", name: b"boom"})
    result = backup.import_zip(blob)
    assert result["ok"] is False and "not allowed" in result["message"]


def test_symlink_members_are_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({"app": "kali-windows-substitute"}))
        z.writestr("kws.sqlite3", b"x")
        link = zipfile.ZipInfo("evidence/link")
        link.external_attr = (0o120777 << 16)
        z.writestr(link, "/etc/passwd")
    assert backup.import_zip(buf.getvalue())["ok"] is False


def test_bad_inputs_never_raise():
    assert backup.import_zip(b"not a zip")["ok"] is False
    assert backup.import_zip(zip_of({"kws.sqlite3": b"x"}, manifest=False))["ok"] is False
    assert backup.import_zip(zip_of({}, manifest=True))["ok"] is False
    wrong = io.BytesIO()
    with zipfile.ZipFile(wrong, "w") as z:
        z.writestr("manifest.json", json.dumps({"app": "something-else"}))
        z.writestr("kws.sqlite3", b"x")
    assert backup.import_zip(wrong.getvalue())["ok"] is False


def test_a_damaged_database_does_not_replace_the_real_one():
    db.add_finding("nmap", "10.0.0.1", "low", "still here")
    result = backup.import_zip(zip_of({"kws.sqlite3": b"this is not sqlite at all" * 50}))
    assert result["ok"] is False and "damaged" in result["message"]
    assert any(f["title"] == "still here" for f in db.findings())


def test_routes(client):
    resp = client.get("/api/backup/export")
    assert resp.status_code == 200 and resp.mimetype == "application/zip"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert client.post("/api/backup/import", data=resp.data).status_code == 403  # CSRF
    ok = client.post("/api/backup/import", data=resp.data, headers=HEADERS)
    assert ok.status_code == 200 and ok.get_json()["ok"] is True
    bad = client.post("/api/backup/import", data=b"junk", headers=HEADERS)
    assert bad.status_code == 400
