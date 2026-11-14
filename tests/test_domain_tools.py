"""Domain-only tools refuse localhost and IP addresses with a clear reason."""
from __future__ import annotations

import pytest

import server.commands as commands


@pytest.mark.parametrize("tool, key", [("whois", "query"), ("dnsrecon", "target"), ("theharvester", "target")])
@pytest.mark.parametrize("value", ["localhost", "127.0.0.1", "10.0.0.5", "192.168.1.0/24"])
def test_private_targets_are_refused_with_a_reason(tool, key, value):
    with pytest.raises(commands.BadInput) as err:
        commands.build(tool, {key: value}, {})
    assert "domain" in str(err.value).lower() or "registry" in str(err.value).lower()


def test_public_domains_still_build():
    assert commands.build("dnsrecon", {"target": "example.com"}, {})[:3] == ["dnsrecon", "-d", "example.com"]
    assert commands.build("whois", {"query": "example.com"}, {}) == ["whois", "example.com"]
