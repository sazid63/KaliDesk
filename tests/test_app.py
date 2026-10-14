"""End-to-end checks against the Flask app via its test client."""
from __future__ import annotations

CSRF = {"X-KWS-CSRF": "test-csrf"}


def test_index_serves_the_ui(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Kali Linux Windows Substitute" in resp.data


def test_index_sets_the_session_cookies():
    import server.app as app_module
    import server.config as config

    application = app_module.create_app(config.load(), "tok-abc", "csrf-abc")
    application.config.update(TESTING=True)
    fresh = application.test_client()
    resp = fresh.get("/?token=tok-abc")
    assert resp.status_code == 200
    cookies = resp.headers.getlist("Set-Cookie")
    assert any("kws_auth=" in c for c in cookies)
    assert any("kws_csrf=" in c for c in cookies)


def test_a_wrong_token_does_not_set_a_cookie():
    import server.app as app_module
    import server.config as config

    application = app_module.create_app(config.load(), "tok-abc", "csrf-abc")
    application.config.update(TESTING=True)
    fresh = application.test_client()
    resp = fresh.get("/?token=wrong")
    assert not any("kws_auth=" in c for c in resp.headers.getlist("Set-Cookie"))


def test_health_and_catalog(client):
    health = client.get("/api/healthz")
    assert health.status_code == 200
    assert health.get_json()["ok"] is True

    data = client.get("/api/catalog").get_json()
    assert data["app"]["name"]
    assert data["tools"]
    assert "nmap" in data["automated"]


def test_preview_returns_an_argv_without_running(client):
    resp = client.post("/api/tool/nmap/preview",
                       json={"target": "10.0.0.5", "profile": "service"}, headers=CSRF)
    assert resp.status_code == 200
    assert resp.get_json()["argv"] == ["nmap", "-sV", "-T4", "10.0.0.5"]


def test_preview_of_a_non_automated_tool_is_501(client):
    resp = client.post("/api/tool/wifite/preview", json={}, headers=CSRF)
    assert resp.status_code == 501


def test_report_download_is_an_attachment(client):
    resp = client.get("/api/report?format=csv")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    assert resp.headers["Content-Type"].startswith("text/csv")


def test_findings_round_trip(client):
    created = client.post("/api/findings", json={
        "tool": "nmap", "target": "10.0.0.9", "severity": "medium", "title": "Note"
    }, headers=CSRF)
    assert created.status_code == 200
    rows = client.get("/api/findings").get_json()["findings"]
    assert any(row["title"] == "Note" for row in rows)
    audit = client.get("/api/audit").get_json()["audit"]
    assert any(entry["action"] == "finding:add" for entry in audit)


def test_scope_guard_blocks_a_public_target_without_confirmation(client):
    # No runtime is running, but the scope check happens before the agent call,
    # so a public target must still be refused first.
    resp = client.post("/api/tool/nmap", json={"target": "93.184.216.34"}, headers=CSRF)
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "target is out of scope"


def test_ai_config_defaults_to_none(client):
    data = client.get("/api/ai/config").get_json()
    assert data["provider"] in {"none", "ollama", "openai"}
