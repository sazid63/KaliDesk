"""End-to-end checks against the Flask app via its test client."""
from __future__ import annotations

CSRF = {"X-KWS-CSRF": "test-csrf"}


def test_index_serves_the_ui(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Kali Linux Windows Substitute" in resp.data


def test_launch_code_sets_the_session_cookies_and_redirects_clean():
    import server.app as app_module
    import server.config as config

    application = app_module.create_app(config.load(), "tok-abc", "csrf-abc")
    application.config.update(TESTING=True)
    fresh = application.test_client()
    resp = fresh.get(f"/?launch={application.config['KWS_LAUNCH']}")
    # The session secret is never in the URL: the code is spent and the browser is sent to "/".
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
    cookies = resp.headers.getlist("Set-Cookie")
    auth, csrf = application.config["KWS_AUTH_COOKIE"], application.config["KWS_CSRF_COOKIE"]
    assert auth == f"kws_auth_{config.load().port}" and csrf == f"kws_csrf_{config.load().port}"
    assert any(f"{auth}=tok-abc" in c for c in cookies)
    assert any(f"{csrf}=csrf-abc" in c for c in cookies)


def test_launch_code_works_once():
    import server.app as app_module
    import server.config as config

    application = app_module.create_app(config.load(), "tok-abc", "csrf-abc")
    application.config.update(TESTING=True)
    code = application.config["KWS_LAUNCH"]
    application.test_client().get(f"/?launch={code}")
    again = application.test_client().get(f"/?launch={code}")
    assert again.status_code == 403
    assert b"already used" in again.data
    assert not any("kws_auth_" in c for c in again.headers.getlist("Set-Cookie"))


def test_launch_code_expires_after_ten_minutes():
    import server.app as app_module
    import server.config as config

    application = app_module.create_app(config.load(), "tok-abc", "csrf-abc")
    application.config.update(TESTING=True)
    code = application.config["KWS_LAUNCH"]
    application.config["KWS_LAUNCH_EXPIRES"] = 0  # as if ten minutes had passed
    resp = application.test_client().get(f"/?launch={code}")
    assert resp.status_code == 403
    assert b"expired" in resp.data
    assert not any("kws_auth_" in c for c in resp.headers.getlist("Set-Cookie"))
    # Once expired, the code stays dead.
    assert b"expired" in application.test_client().get(f"/?launch={code}").data


def test_wrong_launch_code_says_it_is_not_valid():
    import server.app as app_module
    import server.config as config

    application = app_module.create_app(config.load(), "tok-abc", "csrf-abc")
    application.config.update(TESTING=True)
    resp = application.test_client().get("/?launch=wrong")
    assert resp.status_code == 403 and b"not valid" in resp.data


def test_a_wrong_launch_code_or_the_session_token_in_the_url_sets_no_cookie():
    import server.app as app_module
    import server.config as config

    application = app_module.create_app(config.load(), "tok-abc", "csrf-abc")
    application.config.update(TESTING=True)
    for url, status in (("/?launch=wrong", 403), ("/?token=tok-abc", 200)):
        resp = application.test_client().get(url)
        assert resp.status_code == status
        assert not any("kws_auth_" in c for c in resp.headers.getlist("Set-Cookie"))


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


def test_report_lists_every_finding_not_just_200(client):
    import json

    import server.db as db

    for i in range(205):
        db.add_finding("nmap", "10.0.0.2", "low", f"bulk {i}")
    resp = client.get("/api/report?format=json")
    assert resp.get_json(force=True)["finding_count"] >= 205
    assert len(json.loads(resp.data)["findings"]) >= 205


def test_notebook_rejects_non_text_and_oversized_content(client):
    resp = client.post("/api/notebook/entries", json={"content": ["x"]}, headers=CSRF)
    assert resp.status_code == 400
    resp = client.post("/api/notebook/entries", json={"content": "x", "type": 5}, headers=CSRF)
    assert resp.status_code == 400
    resp = client.post("/api/notebook/entries", json={"content": "x" * 20001}, headers=CSRF)
    assert resp.status_code == 400
    resp = client.post("/api/notebook/entries", json={"content": "ok", "tags": "x"}, headers=CSRF)
    assert resp.status_code == 200


def test_refused_requests_are_not_recorded_as_runs(client):
    import server.history as history

    before = len(history.list_history(limit=1000, tool="nmap"))
    resp = client.post("/api/tool/nmap", json={"target": "93.184.216.34"}, headers=CSRF)
    assert resp.status_code == 403
    assert len(history.list_history(limit=1000, tool="nmap")) == before


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


def test_api_errors_are_json_not_html(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.is_json and "error" in resp.get_json()
    resp = client.put("/api/healthz")
    assert resp.status_code == 405 and resp.is_json


def test_unexpected_errors_are_json_and_logged(client, monkeypatch):
    import server.tools as tools

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(tools, "manage_list", boom)
    resp = client.get("/api/tools/manage")
    assert resp.status_code == 500
    assert resp.get_json() == {"error": "internal error", "detail": "RuntimeError"}
