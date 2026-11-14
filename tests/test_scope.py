"""Scope guard: server and in-runtime agent must agree, and bypasses must fail."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

import server.config as config
import server.security as security

AGENT_PATH = Path(__file__).resolve().parent.parent / "runtime" / "agent" / "agent.py"


@pytest.fixture(scope="module")
def agent():
    spec = importlib.util.spec_from_file_location("kalisub_agent", AGENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CASES = [
    # (target, expected)
    ("", "empty"),
    ("   ", "empty"),
    ("127.0.0.1", "private"),
    ("localhost", "private"),
    ("::1", "private"),
    ("192.168.1.10", "private"),
    ("192.168.1.10:8080", "private"),
    ("http://10.0.0.5:8443/login?x=1", "private"),
    ("10.0.0.0/24", "private"),
    ("192.168.0.0/16", "private"),
    ("8.8.8.8", "public"),
    ("example.com", "public"),
    ("https://example.com/a", "public"),
    # Bypass attempts that previously slipped through.
    ("10.0.0.1/0", "public"),
    ("10.0.0.0/7", "public"),
    ("0.0.0.0/0", "public"),
    ("::ffff:8.8.8.8", "public"),
    ("::ffff:127.0.0.1", "private"),
    ("evil.com\\@10.0.0.1", "public"),
    ("10.0.0.1 8.8.8.8", "public"),
    ("10.0.0.1\n8.8.8.8", "public"),
    ("http://10.0.0.1@evil.com/", "public"),
    ("http://[::ffff:8.8.8.8]/", "public"),
    ("http://10.0.0.1:99999/", "public"),
]


@pytest.mark.parametrize(("target", "expected"), CASES)
def test_server_classification(target, expected):
    assert security.classify_target(target, config.PRIVATE_RANGES) == expected


@pytest.mark.parametrize(("target", "expected"), CASES)
def test_agent_classification_matches(agent, target, expected):
    assert agent.classify_target(target) == expected


def test_private_ranges_in_sync(agent):
    assert tuple(agent.PRIVATE_RANGES) == tuple(config.PRIVATE_RANGES)


def test_agent_refuses_public_target_without_confirmation(agent):
    allowed, _ = agent.in_scope("8.8.8.8", False)
    assert allowed is False
    allowed, _ = agent.in_scope("8.8.8.8", True)
    assert allowed is True


def test_payload_with_a_private_and_a_public_host_is_refused():
    # Every host-bearing field is checked: the public url must not hide behind a private target.
    import server.tools as tools

    cfg = config.load()
    body, error = tools._prepare_run(
        cfg, "whatweb", {"target": "10.0.0.5", "url": "http://93.184.216.34/"}, 30,
        user_confirmed=False,
    )
    assert body is None and error[1] == 403
    # A confirmation only counts as a real JSON true from the user's own click.
    body, error = tools._prepare_run(
        cfg, "whatweb", {"url": "http://93.184.216.34/", "confirm_external": "yes"}, 30,
        user_confirmed=True,
    )
    assert body is None and error[1] == 403


def test_agent_timeout_keeps_partial_output(agent):
    result = agent.run_argv(
        [sys.executable, "-c", "import time; print('hello', flush=True); time.sleep(30)"],
        timeout=1,
    )
    assert result["rc"] == 124
    assert "hello" in result["stdout"]
    assert result["timed_out"] is True
