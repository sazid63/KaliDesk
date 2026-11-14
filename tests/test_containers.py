"""Podman container manager: validation and parsing, with the distro mocked out."""
from __future__ import annotations

import json
import time

import pytest

import server.container_runtime as cr
from app import runtime


@pytest.fixture()
def calls(monkeypatch):
    """Record every argv sent to the distro; reply from `replies` (default: success)."""
    class Log(list):
        replies: dict[str, tuple[int, str, str]]

    log = Log()
    replies: dict[str, tuple[int, str, str]] = {}

    def fake(cfg, argv, timeout=60, stdin_text=None):
        log.append(argv)
        for key, value in replies.items():
            if key in " ".join(argv):
                return value
        return 0, "", ""

    monkeypatch.setattr(runtime, "in_distro", fake)
    log.replies = replies
    return log


def test_image_regex_is_not_exponential():
    started = time.time()
    for n in (20, 24, 28, 40, 200):
        assert not cr.validate_image_name("a" * n + "!")[0]
    assert time.time() - started < 1.0


@pytest.mark.parametrize("image", [
    "alpine", "ubuntu:22.04", "docker.io/library/kali:latest", "quay.io/centos/centos:8",
    "localhost:5000/team/app:v1", "redis:7@sha256:" + "a" * 64, "bkimminich/juice-shop",
])
def test_good_images(image):
    assert cr.validate_image_name(image) == (True, "")


@pytest.mark.parametrize("image", [
    "", "-rm", "a b", "alpine;rm -rf /", "../x", "UPPER", "x" * 300, "a/../b", "a:", "$(id)",
])
def test_bad_images(image):
    assert not cr.validate_image_name(image)[0]


def test_ports_bind_to_loopback_only():
    assert cr.normalize_port_binding("3000:3000") == ("127.0.0.1:3000:3000", "")
    assert cr.normalize_port_binding("127.0.0.1:8080:80/udp") == ("127.0.0.1:8080:80/udp", "")
    for bad in ("0.0.0.0:80:80", "80", "a:b", "70000:80", "1:2:3:4", "8080:80/icmp", ""):
        assert cr.normalize_port_binding(bad)[1], bad


def test_volumes_are_limited_to_safe_roots():
    assert cr.validate_volume_spec("/tmp/data:/data")[0]
    assert cr.validate_volume_spec("/tmp/data:/data:ro")[0]
    for bad in ("/etc:/data", "/tmp/../etc:/data", "C:/temp:/data", "tmp:/data",
                "/tmp/x:data", "/tmp/x:/d:weird", "/tmp"):
        assert not cr.validate_volume_spec(bad)[0], bad
    evidence = cr.allowed_volume_roots()[1]
    assert cr.validate_volume_spec(f"{evidence}:/evidence:ro")[0]


def test_exec_allowlist_blocks_shells_and_interpreters():
    assert cr.validate_exec_command(["ping", "-c", "1", "10.0.0.1"])[0]
    for bad in (["bash", "-c", "id"], ["sh"], ["python3", "-c", "1"], ["find", ".", "-exec", "id"],
                ["xargs", "id"], ["awk", "BEGIN{system(1)}"], ["env", "id"], ["apt", "install"],
                ["ls", "a;b"], ["cat", "a|b"], ["echo", "$(id)"], ["echo", "`id`"], []):
        assert not cr.validate_exec_command(bad)[0], bad


def test_container_refs_cannot_be_options():
    assert cr.validate_container_ref("abc123")[0] and cr.validate_container_ref("my-app_1")[0]
    for bad in ("--all", "-f", "a b", "", "x" * 200, "a;b"):
        assert not cr.validate_container_ref(bad)[0], bad


def test_every_operation_validates_the_container_ref(calls):
    for fn in (cr.start_container, cr.stop_container, cr.remove_container, cr.get_container_logs):
        assert fn("--all")["ok"] is False
    assert cr.exec_in_container("--all", ["ls"])["ok"] is False
    assert calls == []  # nothing reached the distro


def test_list_parses_a_json_array_and_json_lines(calls):
    images = [{"Id": "a" * 64, "Names": ["docker.io/library/alpine:latest"], "Size": 5,
               "CreatedAt": "x"}]
    calls.replies["images"] = (0, json.dumps(images), "")
    assert cr.list_images()[0]["name"] == "docker.io/library/alpine:latest"
    calls.replies["images"] = (0, "\n".join(json.dumps(i) for i in images), "")
    assert cr.list_images()[0]["id"] == "a" * 12
    ps = [{"Id": "b" * 64, "Names": ["web"], "Image": "nginx", "State": "running",
           "Ports": [{"host_ip": "127.0.0.1", "host_port": 8080, "container_port": 80}]}]
    calls.replies["ps"] = (0, json.dumps(ps), "")
    row = cr.list_containers(all=True)[0]
    assert row["names"] == ["web"] and "8080->80" in row["ports"] and row["status"] == "running"


def test_status_skips_listing_when_podman_is_missing(calls):
    calls.replies["--version"] = (1, "", "podman: not found")
    assert cr.status() == {"podman_installed": False, "images": [], "containers": []}
    assert all("ps" not in a and "images" not in a for a in calls)


def test_install_podman_uses_apt_not_a_podman_prefix(calls):
    calls.replies["--version"] = (1, "", "")  # not installed
    cr.install_podman()
    apt_calls = [a for a in calls if "apt-get" in a]
    assert apt_calls and all(a[0] != "podman" for a in apt_calls)


def test_run_container_builds_a_safe_command(calls):
    result = cr.run_container("alpine", "box", ["3000:3000"], ["/tmp/d:/data"])
    assert result["ok"]
    argv = next(a for a in calls if a[1:2] == ["run"])
    assert argv[0] == "podman" and "--privileged" not in argv
    assert "127.0.0.1:3000:3000" in argv and "/tmp/d:/data" in argv
    assert "no-new-privileges" in argv and argv[-1] == "alpine"
    assert not cr.run_container("alpine", "-x")["ok"]
    assert not cr.run_container("alpine", "box", ["0.0.0.0:1:1"])["ok"]


def test_run_passes_the_command_as_argv_after_the_image(calls):
    cr.run_container("alpine", "box", command=["sleep", "300"])
    argv = next(a for a in calls if a[1:2] == ["run"])
    assert argv[-3:] == ["alpine", "sleep", "300"]


def test_run_refuses_too_many_command_parts(calls):
    result = cr.run_container("alpine", "box", command=["x"] * (cr.MAX_COMMAND_ARGS + 1))
    assert not result["ok"] and "at most" in result["error"]
    assert not any(a[1:2] == ["run"] for a in calls)


def test_run_reports_a_quick_exit_with_its_code(calls):
    calls.replies["run"] = (0, "cb7e20f7412b\n", "")
    calls.replies["inspect"] = (0, "exited 3\n", "")
    result = cr.run_container("alpine", "box")
    assert result["state"] == "exited" and result["exit_code"] == 3
    assert "exited with code 3" in result["message"]


def test_run_reports_a_running_container(calls):
    calls.replies["run"] = (0, "cb7e20f7412b\n", "")
    calls.replies["inspect"] = (0, "running 0\n", "")
    result = cr.run_container("alpine", "box")
    assert result["state"] == "running" and "started" in result["message"]
