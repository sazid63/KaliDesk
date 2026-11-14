"""Security behaviour: auth, CSRF, headers and the port-specific cookie names.

Classification of targets is covered once, in tests/test_scope.py.
"""
from __future__ import annotations

import re

import pytest

import server.app as app_module
import server.config as config
import server.security as security


def test_cookie_names_carry_the_port():
    assert security.cookie_names(8765) == ("kws_auth_8765", "kws_csrf_8765")


def test_unauthenticated_request_is_rejected():
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


# --- every /api route, checked by its method -------------------------------------

_APP = app_module.create_app(config.load(), "tok-matrix", "csrf-matrix")
_APP.config.update(TESTING=True)


def _api_routes() -> list[tuple[str, str]]:
    """(method, concrete path) for every /api route; parameters become sample values."""
    found: list[tuple[str, str]] = []
    for rule in _APP.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        path = re.sub(r"<(?:\w+:)?\w+>", "1", rule.rule)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            found.append((method, path))
    return found


ROUTES = _api_routes()


def test_the_route_list_is_not_empty():
    assert len(ROUTES) > 40


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_every_api_route_returns_401_anonymously(method, path):
    resp = _APP.test_client().open(path, method=method)
    assert resp.status_code == 401, f"{method} {path} answered {resp.status_code}"


@pytest.mark.parametrize(
    ("method", "path"),
    [(m, p) for m, p in ROUTES if m in ("POST", "DELETE")],
)
def test_every_write_route_returns_403_without_csrf(method, path):
    client = _APP.test_client()
    client.set_cookie(_APP.config["KWS_AUTH_COOKIE"], "tok-matrix")
    resp = client.open(path, method=method, json={})
    assert resp.status_code == 403, f"{method} {path} answered {resp.status_code}"
