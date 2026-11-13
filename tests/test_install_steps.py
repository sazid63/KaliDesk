"""Tools that are not in apt install through catalog-defined steps."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def agent():
    spec = importlib.util.spec_from_file_location("kalisub_agent_steps", ROOT / "runtime/agent/agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def handler(agent, tools):
    return type("H", (agent.Handler,), {"tools": tools})


def test_manifest_carries_the_steps_for_volatility3():
    data = json.loads((ROOT / "runtime/rootfs/etc/kalisub/tools.json").read_text(encoding="utf-8"))
    vol = next(t for t in data["tools"] if t["id"] == "volatility3")
    assert vol["binary"] == "vol"
    assert vol["install_steps"][-1] == ["ln", "-sf", "/opt/volatility3/bin/vol", "/usr/local/bin/vol"]
    assert vol["remove_steps"] == [["rm", "-rf", "/opt/volatility3", "/usr/local/bin/vol"]]
    nikto = next(t for t in data["tools"] if t["id"] == "nikto")
    assert "install_steps" not in nikto  # normal apt tools are unchanged


def test_agent_uses_custom_steps_instead_of_apt(agent):
    tools = {"x": {"packages": ["y"], "install_steps": [["echo", "hi"]], "remove_steps": [["true"]]}}
    h = handler(agent, tools)
    steps, error = h._apt_steps(h, "x", "install")
    assert error is None and steps == [["echo", "hi"]]
    steps, error = h._apt_steps(h, "x", "remove")
    assert steps == [["true"]]


def test_agent_falls_back_to_apt_and_rejects_malformed_steps(agent):
    h = handler(agent, {"a": {"packages": ["nmap"]},
                        "b": {"packages": ["x"], "install_steps": [["ok"], "not-a-list"]},
                        "c": {"packages": ["x"], "install_steps": [["bad\narg"]]}})
    steps, _ = h._apt_steps(h, "a", "install")
    assert steps[-1][:4] == ["apt-get", "install", "-y", "--no-install-recommends"]
    assert h._apt_steps(h, "b", "install")[1][0] == 400
    assert h._apt_steps(h, "c", "install")[1][0] == 400


def test_photorec_installs_the_package_that_ships_the_binary():
    import server.catalog as catalog

    assert "photorec" in catalog.get("photorec")["packages"]
