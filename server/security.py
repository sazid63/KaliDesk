"""Authentication, CSRF, security headers and the authorisation scope guard.

The backend is loopback-only. Even so it requires a bearer token (set as an
HttpOnly cookie after the launcher opens the UI) and a CSRF token on every
state-changing request. The scope guard is the last line of defence against a
tool being pointed at a third party by accident.
"""
from __future__ import annotations

import hmac
import ipaddress
import secrets
from collections.abc import Callable
from functools import wraps

from flask import Response, jsonify, request

AUTH_COOKIE = "kws_auth"
CSRF_COOKIE = "kws_csrf"
CSRF_HEADER = "X-KWS-CSRF"

# Deliberately strict. No inline script/style, no framing, no remote origins.
CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def install_headers(app) -> None:
    @app.after_request
    def _headers(resp: Response) -> Response:  # noqa: ANN001
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        resp.headers.setdefault("Cache-Control", "no-store")
        return resp


def require_auth(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        from flask import current_app

        expected = current_app.config.get("KWS_TOKEN", "")
        supplied = request.cookies.get(AUTH_COOKIE) or ""
        if not expected or not hmac.compare_digest(str(supplied), str(expected)):
            return jsonify({"error": "unauthorised"}), 401
        return view(*args, **kwargs)

    return wrapper


def require_csrf(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        cookie = request.cookies.get(CSRF_COOKIE) or ""
        header = request.headers.get(CSRF_HEADER) or ""
        if not cookie or not hmac.compare_digest(cookie, header):
            return jsonify({"error": "CSRF check failed"}), 403
        return view(*args, **kwargs)

    return wrapper


def _host_of(target: str) -> str:
    host = (target or "").strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].split("?", 1)[0]
    if "@" in host:
        host = host.split("@", 1)[1]
    if host.startswith("["):  # IPv6 literal
        return host[1 : host.find("]")] if "]" in host else host
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.strip()


def classify_target(target: str, private_ranges: tuple[str, ...]) -> str:
    """Return 'empty', 'private' or 'public' for a target string."""
    host = _host_of(target)
    if not host:
        return "empty"
    if host.lower() in {"localhost", "localhost.localdomain", "::1"}:
        return "private"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A hostname: we cannot know where it resolves without a lookup, so we
        # treat it as external and require confirmation.
        return "public"
    if ip.is_loopback:
        return "private"
    for cidr in private_ranges:
        try:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return "private"
        except ValueError:
            continue
    return "public"


def scope_allows(target: str, confirmed_external: bool,
                 private_ranges: tuple[str, ...]) -> tuple[bool, str]:
    kind = classify_target(target, private_ranges)
    if kind == "empty":
        return True, "no target supplied"
    if kind == "private":
        return True, "target is on a private or loopback address"
    if confirmed_external:
        return True, "external target explicitly confirmed by the user"
    return False, (
        "target is outside the private ranges. Tick the confirmation box and "
        "make sure you have written authorisation to test it."
    )
