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


def _setup_logging() -> None:
    """Log to %LOCALAPPDATA%/KaliWindowsSubstitute/logs (a windowed build has no console)."""
    import logging
    from logging.handlers import RotatingFileHandler

    import kws.paths as kws_paths

    handler = RotatingFileHandler(
        kws_paths.log_dir() / "kws.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("kws")
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _port_free(host: str, port: int) -> bool:
    """True if nothing is bound to the port. (On Windows a plain bind can silently share
    a port that is already in use, so ask for exclusive use.)"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _build(cfg):
    token = security.new_token()
    csrf = security.new_token()
    return backend.create_app(cfg, token, csrf)


def _url(cfg, launch: str) -> str:
    # The URL carries only a one-time launch code. The backend spends it on first use and
    # redirects to a clean address, so the session secret never appears in a URL.
    return f"http://{cfg.host}:{cfg.port}/?launch={launch}"


def _serve(cfg, flask_app):
    server = make_server(cfg.host, cfg.port, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_check() -> int:
    """Headless smoke test used by installer/build.ps1 and CI."""
    cfg = config.load()
    flask_app = _build(cfg)
    client = flask_app.test_client()
    index = client.get(f"/?launch={flask_app.config['KWS_LAUNCH']}", follow_redirects=True)
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
    parser.add_argument(
        "--no-gui", action="store_true", help="serve the backend and print the URL without a window"
    )
    parser.add_argument("--check", action="store_true", help="run a headless self-check and exit")
    parser.add_argument("--port", type=int, default=None, help="override the backend port")
    args = parser.parse_args(argv)

    cfg = config.load()
    if args.port:
        cfg = type(cfg)(**{**cfg.__dict__, "port": args.port})

    if args.check:
        return run_check()

    _setup_logging()
    # If the port is taken (a second copy, or another program), try the next ones, never past
    # 65535. The port is chosen before the app is built because the cookie names include it.
    first = cfg.port
    last = min(first + 9, 65535)
    port = next((p for p in range(first, last + 1) if _port_free(cfg.host, p)), None)
    if port is None:
        print(f"ports {first}-{last} are all in use", file=sys.stderr, flush=True)
        return 1
    cfg = type(cfg)(**{**cfg.__dict__, "port": port})
    flask_app = _build(cfg)
    try:
        server = _serve(cfg, flask_app)
    except OSError as exc:
        print(f"port {port} could not be opened: {exc}", file=sys.stderr, flush=True)
        return 1
    url = _url(cfg, flask_app.config["KWS_LAUNCH"])

    if args.no_gui:
        # flush=True: a windowed or piped run may not flush stdout, and the URL must show now.
        print(f"Kali Linux Windows Substitute is running at {url}", flush=True)
        print(
            f"The link works once and expires after {backend.LAUNCH_TTL // 60} minutes. "
            "If it says the link was used or expired, restart the app.",
            flush=True,
        )
        print("Press Ctrl+C to stop.", flush=True)
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
        print(f"Opened {url} in your browser. Press Ctrl+C to stop.", flush=True)
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
