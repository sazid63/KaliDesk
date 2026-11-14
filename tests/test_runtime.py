"""Runtime provisioning: image lookup/download, checksum, decoding, state."""
from __future__ import annotations

import hashlib
import http.server
import threading
from pathlib import Path

import pytest

from app import runtime


@pytest.fixture()
def web(tmp_path):
    """Serve tmp_path over loopback HTTP and yield the base URL."""

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(tmp_path), **k)

        def log_message(self, *a):  # noqa: D102
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/", tmp_path
    server.shutdown()


def test_decode_handles_utf16_and_utf8():
    assert runtime._decode("Ubuntu\r\nKali\r\n".encode("utf-16-le")).split() == ["Ubuntu", "Kali"]
    assert runtime._decode(b"\xff\xfe" + "abc".encode("utf-16-le")) == "abc"
    assert runtime._decode(b"plain") == "plain"
    assert runtime._decode(None) == ""


def test_parse_sha256sums():
    good = "a" * 64
    text = f"{good}  kali-linux-2026.3-wsl-rootfs-amd64.wsl\nnot-a-hash  junk\n"
    assert runtime.parse_sha256sums(text) == {"kali-linux-2026.3-wsl-rootfs-amd64.wsl": good}


def test_official_image_picks_newest_wsl_rootfs(web):
    base, root = web
    h1, h2 = "1" * 64, "2" * 64
    (root / "SHA256SUMS").write_text(
        f"{h1}  kali-linux-2026.2-wsl-rootfs-amd64.wsl\n"
        f"{h2}  kali-linux-2026.3-wsl-rootfs-amd64.wsl\n"
        f"{'3' * 64}  kali-linux-2026.3-installer-amd64.iso\n"
    )
    url, sha = runtime.official_image(base)
    assert url.endswith("kali-linux-2026.3-wsl-rootfs-amd64.wsl")
    assert sha == h2


def test_official_image_compares_versions_as_numbers(web):
    base, root = web
    (root / "SHA256SUMS").write_text(
        f"{'1' * 64}  kali-linux-2025.4-wsl-rootfs-amd64.wsl\n"
        f"{'2' * 64}  kali-linux-2025.10-wsl-rootfs-amd64.wsl\n"
    )
    url, _sha = runtime.official_image(base)
    assert url.endswith("kali-linux-2025.10-wsl-rootfs-amd64.wsl")


def test_official_image_errors_when_none_listed(web):
    base, root = web
    (root / "SHA256SUMS").write_text(f"{'1' * 64}  something.iso\n")
    with pytest.raises(RuntimeError):
        runtime.official_image(base)


def test_download_verifies_checksum_and_reports_progress(web, tmp_path_factory):
    base, root = web
    payload = b"rootfs-bytes" * 1000
    (root / "img.wsl").write_bytes(payload)
    dest = tmp_path_factory.mktemp("dl") / "img.wsl"
    ok, detail = runtime.download_image(base + "img.wsl", hashlib.sha256(payload).hexdigest(), dest)
    assert ok, detail
    assert dest.read_bytes() == payload
    assert runtime.provisioning_status()["progress"]["done"] == len(payload)
    # A verified file is reused without another download.
    ok, _ = runtime.download_image("http://127.0.0.1:1/unreachable", hashlib.sha256(payload).hexdigest(), dest)
    assert ok


def test_download_rejects_bad_checksum_and_discards(web, tmp_path_factory):
    base, root = web
    (root / "img.wsl").write_bytes(b"abc")
    dest = tmp_path_factory.mktemp("dl") / "img.wsl"
    ok, detail = runtime.download_image(base + "img.wsl", "0" * 64, dest)
    assert not ok and "SHA-256" in detail
    assert not dest.exists()
    assert not Path(str(dest) + ".part").exists()


def test_download_refuses_without_checksum(tmp_path):
    ok, detail = runtime.download_image("http://127.0.0.1:1/x", "", tmp_path / "x")
    assert not ok and "checksum" in detail


def test_baseline_packages_are_valid_and_include_essentials():
    packages = runtime.baseline_packages()
    assert "python3" in packages and "nmap" in packages
    assert all(runtime.PACKAGE_NAME.match(p) for p in packages)
    assert len(packages) == len(set(packages))


def test_ensure_is_single_flight(monkeypatch):
    """A second ensure() while one runs must not start another worker."""
    gate = threading.Event()
    started = []

    def slow(cfg, fail):
        started.append(1)
        gate.wait(5)

    monkeypatch.setattr(runtime, "_provision", slow)
    import server.config as config

    cfg = config.load()
    first = runtime.ensure(cfg)
    second = runtime.ensure(cfg)
    assert first["provisioning"] and second["provisioning"]
    assert "already" in second["message"]
    gate.set()
    for _ in range(50):
        if not runtime._PROVISION_LOCK.locked():
            break
        threading.Event().wait(0.1)
    assert started == [1]


def test_failure_is_reported_not_swallowed(monkeypatch):
    def boom(cfg, fail):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(runtime, "_provision", boom)
    import server.config as config

    runtime.ensure(config.load())
    for _ in range(50):
        if not runtime._PROVISION_LOCK.locked():
            break
        threading.Event().wait(0.1)
    state = runtime.provisioning_status()
    assert state["error"] is True and state["done"] is True and "kaboom" in state["message"]


def test_commands_in_the_distro_bypass_the_distro_shell(monkeypatch):
    """Regression (found on a real distro): without --exec, wsl.exe's shell ate $1 and quotes."""
    seen = []
    monkeypatch.setattr(runtime, "_run", lambda args, timeout=60, stdin_text=None: seen.append(args) or (0, "", ""))
    import server.config as config

    runtime.in_distro(config.load(), ["sh", "-c", 'cat > "$1"', "sh", "/x"])
    assert "--exec" in seen[0] and "--" not in seen[0]
    assert seen[0][seen[0].index("--exec") + 1:] == ["sh", "-c", 'cat > "$1"', "sh", "/x"]


def test_apt_sources_fix_keeps_the_sed_backreference(monkeypatch):
    sent = []
    monkeypatch.setattr(runtime, "_run", lambda args, timeout=60, stdin_text=None: sent.append(args) or (0, "", ""))
    import server.config as config

    runtime._ensure_apt_components(config.load())
    script = sent[0][-1]
    assert r"\1 main contrib non-free non-free-firmware" in script and "\x01" not in script


def test_sed_expression_really_rewrites_the_line(tmp_path):
    import re

    line = "deb http://http.kali.org/kali kali-rolling main"
    pattern = r"^(deb(-src)? +[^ ]*kali[^ ]* +kali-rolling) +main( +.*)?$"
    assert re.sub(pattern, r"\1 " + runtime.APT_COMPONENTS, line) == line + " contrib non-free non-free-firmware"
    done = line + " contrib non-free non-free-firmware"
    assert re.sub(pattern, r"\1 " + runtime.APT_COMPONENTS, done) == done  # idempotent
