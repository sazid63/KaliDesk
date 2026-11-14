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
from urllib.parse import urlsplit

from flask import Response, jsonify, request

import server.config as config

CSRF_HEADER = "X-KWS-CSRF"


def cookie_names(port: int) -> tuple[str, str]:
    """Port-specific cookie names, so two copies on different ports do not overwrite each other.

    Returns ``(auth_cookie, csrf_cookie)``, e.g. ``("kws_auth_8765", "kws_csrf_8765")``.
    """
    return f"kws_auth_{int(port)}", f"kws_csrf_{int(port)}"

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
        supplied = request.cookies.get(current_app.config["KWS_AUTH_COOKIE"]) or ""
        # Compare bytes: hmac.compare_digest raises TypeError on non-ASCII str.
        if not expected or not hmac.compare_digest(
            str(supplied).encode("utf-8"), str(expected).encode("utf-8")
        ):
            return jsonify({"error": "unauthorised"}), 401
        return view(*args, **kwargs)

    return wrapper


def require_csrf(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        from flask import current_app

        cookie = request.cookies.get(current_app.config["KWS_CSRF_COOKIE"]) or ""
        header = request.headers.get(CSRF_HEADER) or ""
        # Compare bytes: hmac.compare_digest raises TypeError on non-ASCII str.
        if not cookie or not hmac.compare_digest(cookie.encode("utf-8"), header.encode("utf-8")):
            return jsonify({"error": "CSRF check failed"}), 403
        return view(*args, **kwargs)

    return wrapper


def _ip_is_private(ip, nets) -> bool:
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback or any(ip.version == n.version and ip in n for n in nets)


def _net_is_private(net, nets) -> bool:
    """A network is private only if the *whole* network sits inside a private range."""
    if net.version == 6 and net.network_address.ipv4_mapped is not None:
        return False
    return any(net.version == n.version and net.subnet_of(n) for n in nets)


def classify_target(target: str, private_ranges: tuple[str, ...] = config.PRIVATE_RANGES) -> str:
    """Return 'empty', 'private' or 'public' for a target string.

    Mirrors ``runtime/agent/agent.py::classify_target`` (a test compares them).
    Anything we cannot parse with certainty is 'public', i.e. needs confirmation.
    """
    nets = tuple(ipaddress.ip_network(c, strict=False) for c in private_ranges)
    text = (target or "").strip()
    if not text:
        return "empty"
    if any(ch in text for ch in "\\ \t\r\n\x00"):
        return "public"
    # Bare IP, bare IPv6 or CIDR (e.g. 10.0.0.0/24, ::1, ::ffff:8.8.8.8).
    try:
        if "/" in text:
            net = ipaddress.ip_network(text, strict=False)
            return "private" if _net_is_private(net, nets) else "public"
        return "private" if _ip_is_private(ipaddress.ip_address(text), nets) else "public"
    except ValueError:
        pass
    # URL or host[:port][/path]
    try:
        parts = urlsplit(text if "://" in text else "//" + text)
        host = parts.hostname or ""
        parts.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError:
        return "public"
    if not host:
        return "public"
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return "private"
    try:
        return "private" if _ip_is_private(ipaddress.ip_address(host), nets) else "public"
    except ValueError:
        # A hostname: we cannot know where it resolves, so it needs confirmation.
        return "public"


def scope_allows(
    target: str, confirmed_external: bool, private_ranges: tuple[str, ...] = config.PRIVATE_RANGES
) -> tuple[bool, str]:
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
