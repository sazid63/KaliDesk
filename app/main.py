"""Launcher for Kali Linux Windows Substitute.

Starts the loopback backend, then shows the UI in a native window (pywebview).
Falls back to the default browser if pywebview is unavailable, and supports a
headless self-check so a build can be verified without a display.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

# Running this file directly (python app/main.py) puts app/ on sys.path, not the
# project root, so make the root importable first.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from werkzeug.serving import make_server  # noqa: E402

import server.app as backend  # noqa: E402
import server.config as config  # noqa: E402
import server.security as security  # noqa: E402


def _build(cfg):
    token = security.new_token()
    csrf = security.new_token()
    flask_app = backend.create_app(cfg, token, csrf)
    return flask_app, token, csrf


def _url(cfg, token: str) -> str:
    return f"http://{cfg.host}:{cfg.port}/?token={token}"


def _serve(cfg, flask_app):
    server = make_server(cfg.host, cfg.port, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_check() -> int:
    """Headless smoke test used by installer/build.ps1 and CI."""
    cfg = config.load()
    flask_app, token, _ = _build(cfg)
    client = flask_app.test_client()
    index = client.get(f"/?token={token}")
    if index.status_code != 200:
        print(f"FAIL: index returned {index.status_code}")
        return 1
    health = client.get("/api/healthz")
    if health.status_code != 200:
        print(f"FAIL: /api/healthz returned {health.status_code}")
        return 1
    catalog = client.get("/api/catalog")
    data = catalog.get_json() or {}
    tools = data.get("tools") or []
    if not tools:
        print("FAIL: catalog is empty")
        return 1
    print(f"OK: backend healthy, {len(tools)} tools in the catalog")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kali-windows-substitute")
    parser.add_argument("--no-gui", action="store_true",
                        help="serve the backend and print the URL without a window")
    parser.add_argument("--check", action="store_true",
                        help="run a headless self-check and exit")
    parser.add_argument("--port", type=int, default=None,
                        help="override the backend port")
    args = parser.parse_args(argv)

    cfg = config.load()
    if args.port:
        cfg = type(cfg)(**{**cfg.__dict__, "port": args.port})

    if args.check:
        return run_check()

    flask_app, token, _ = _build(cfg)
    url = _url(cfg, token)
    server = _serve(cfg, flask_app)

    if args.no_gui:
        print(f"Kali Linux Windows Substitute is running at {url}")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
        return 0

    try:
        import webview  # type: ignore
    except ImportError:
        import webbrowser

        webbrowser.open(url)
        print(f"Opened {url} in your browser. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
        return 0

    webview.create_window(
        "Kali Linux Windows Substitute", url, width=1360, height=900, min_size=(980, 640)
    )
    webview.start()
    server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
