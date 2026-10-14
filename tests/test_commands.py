"""Command builders must produce argv lists, never shell strings."""
from __future__ import annotations

import server.commands as commands


def test_nmap_profiles():
    assert commands.build("nmap", {"target": "10.0.0.1", "profile": "service"}, {}) == [
        "nmap", "-sV", "-T4", "10.0.0.1"
    ]
    assert commands.build("nmap", {"target": "10.0.0.1", "profile": "host-discovery"}, {}) == [
        "nmap", "-sn", "10.0.0.1"
    ]


def test_dns_query_tokens():
    assert commands.build("dns", {"name": "MX example.com"}, {}) == [
        "dig", "+short", "MX", "example.com"
    ]


def test_sqlmap_enumerate_adds_flag():
    assert "--dbs" not in commands.build("sqlmap", {"url": "https://x.test/a?id=1"}, {})
    assert "--dbs" in commands.build(
        "sqlmap", {"url": "https://x.test/a?id=1", "enumerate": True}, {}
    )


def test_hydra_uses_files_from_the_context():
    ctx = {"files": {"users.txt": "/w/users.txt", "passwords.txt": "/w/passwords.txt"}}
    assert commands.build("hydra", {"target": "10.0.0.5", "service": "ssh"}, ctx) == [
        "hydra", "-L", "/w/users.txt", "-P", "/w/passwords.txt", "ssh://10.0.0.5"
    ]
    assert commands.build("hydra", {"target": "10.0.0.5", "service": "http-get"}, ctx) == [
        "hydra", "-L", "/w/users.txt", "-P", "/w/passwords.txt", "10.0.0.5", "http-get", "/"
    ]


def test_files_for_returns_expected_names():
    assert set(commands.files_for("hydra", {"users": "a", "passwords": "b"})) == {
        "users.txt", "passwords.txt"
    }
    assert commands.files_for("john", {"hashes": "x"})["hashes.txt"] == "x"
    assert commands.files_for("nmap", {}) == {}


def test_every_automated_id_is_known_to_the_catalog():
    import server.catalog as catalog

    known = {t["id"] for t in catalog.tools()}
    for tool_id in commands.automated_ids():
        assert tool_id in known, f"{tool_id} is automated but not in the catalog"


def test_unknown_tool_has_no_builder():
    assert commands.build("nope", {}, {}) is None


def test_nothing_returns_a_shell_string():
    # argv entries are the only output shape; a single concatenated string is a bug.
    for tool_id in commands.automated_ids():
        payload = {
            "target": "10.0.0.1", "url": "https://10.0.0.1/", "query": "x",
            "name": "example.com", "file": "a.bin", "user": "u", "passwords": "p",
            "hashes": "h", "hash": "h", "min": "1", "max": "2", "charset": "ab",
            "module": "auxiliary/x", "filter": "port 53", "port": "22", "service": "ssh",
            "profile": "service", "mode": "0", "mask": "",
        }
        ctx = {"files": {"users.txt": "/w/u", "passwords.txt": "/w/p",
                         "hashes.txt": "/w/h", "hash.txt": "/w/h"},
               "evidence": {"a.bin": "/e/a.bin"}, "work": "/w"}
        argv = commands.build(tool_id, payload, ctx)
        assert isinstance(argv, list) and argv, tool_id
        assert all(isinstance(part, str) for part in argv), tool_id
