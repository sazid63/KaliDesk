"""Security behaviour: auth, CSRF, headers and the scope guard."""
from __future__ import annotations

import server.security as security
from server.config import load as load_config

PRIVATE = load_config().private_ranges


def test_classify_private_targets():
    for target in ("192.168.1.10", "10.1.2.3", "172.16.0.9", "127.0.0.1", "localhost"):
        assert security.classify_target(target, PRIVATE) == "private", target


def test_classify_public_targets():
    for target in ("8.8.8.8", "example.com", "https://example.com/path?x=1", "1.1.1.1"):
        assert security.classify_target(target, PRIVATE) == "public", target


def test_classify_empty():
    assert security.classify_target("", PRIVATE) == "empty"
    assert security.classify_target("   ", PRIVATE) == "empty"


def test_public_target_needs_confirmation():
    allowed, _ = security.scope_allows("8.8.8.8", False, PRIVATE)
    assert allowed is False
    allowed, _ = security.scope_allows("8.8.8.8", True, PRIVATE)
    assert allowed is True


def test_private_target_allowed_without_confirmation():
    allowed, _ = security.scope_allows("192.168.0.5", False, PRIVATE)
    assert allowed is True


def test_url_host_is_extracted():
    assert security._host_of("https://user@example.com:8443/a?b=1") == "example.com"
    assert security._host_of("192.168.1.1:22") == "192.168.1.1"


def test_unauthenticated_request_is_rejected():
    import server.app as app_module
    import server.config as config

    application = app_module.create_app(config.load(), "tok", "csrf")
    application.config.update(TESTING=True)
    anonymous = application.test_client()
    assert anonymous.get("/api/catalog").status_code == 401


def test_authenticated_request_is_allowed(client):
    assert client.get("/api/healthz").status_code == 200


def test_write_requires_csrf(client):
    # client has the auth cookie; drop the CSRF cookie/header by omitting header.
    resp = client.post("/api/findings", json={"title": "x"})
    assert resp.status_code == 403


def test_write_with_csrf_succeeds(client):
    resp = client.post(
        "/api/findings",
        json={"tool": "nmap", "target": "10.0.0.1", "severity": "low", "title": "test"},
        headers={"X-KWS-CSRF": "test-csrf"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["id"] >= 1


def test_security_headers_present(client):
    resp = client.get("/api/healthz")
    assert "Content-Security-Policy" in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
