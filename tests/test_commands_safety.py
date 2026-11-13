"""Every tool must be usable, and no form field may smuggle in an option or a command."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import server.catalog as catalog
import server.commands as commands

MANIFEST = Path(__file__).resolve().parent.parent / "runtime" / "rootfs" / "etc" / "kalisub" / "tools.json"
CTX = {
    "files": {"users.txt": "/w/u", "passwords.txt": "/w/p", "hashes.txt": "/w/h", "hash.txt": "/w/h"},
    "evidence": {"a.bin": "/e/a.bin"},
    "work": "/w",
}
GOOD = {
    "target": "10.0.0.1", "url": "https://10.0.0.1/FUZZ", "query": "x", "name": "example.com",
    "file": "a.bin", "user": "u", "users": "u", "passwords": "p", "hashes": "h", "hash": "h",
    "module": "auxiliary/scanner/http/http_version", "filter": "port 53", "port": "22",
    "lhost": "10.0.0.2", "password": "pw123", "min": "1", "max": "2", "charset": "ab",
}


def _manifest():
    return {t["id"]: t for t in json.loads(MANIFEST.read_text(encoding="utf-8"))["tools"]}


def test_every_tool_is_covered_one_way_or_another():
    """Each catalog tool has a form, a terminal command, or is a built-in feature."""
    for tool in catalog.tools():
        tool_id = tool["id"]
        if tool.get("builtin"):
            continue
        assert tool_id in commands.BUILDERS or tool_id in commands.TERMINAL_COMMANDS, (
            f"{tool_id} has neither a one-click form nor a terminal command"
        )


def test_builder_binary_matches_the_manifest():
    """argv[0] must equal the binary the agent's allowlist expects, or the run is refused."""
    manifest = _manifest()
    for tool_id in commands.automated_ids():
        argv = commands.build(tool_id, GOOD, CTX)
        assert argv[0] == manifest[tool_id]["binary"], tool_id


def test_terminal_commands_use_the_declared_binary():
    manifest = _manifest()
    for tool_id, argv in commands.TERMINAL_COMMANDS.items():
        assert argv[0] == manifest[tool_id]["binary"], tool_id


@pytest.mark.parametrize(
    ("tool_id", "field"),
    [
        ("nmap", "target"), ("whois", "query"), ("sqlmap", "url"), ("nikto", "url"),
        ("whatweb", "url"), ("dnsrecon", "target"), ("hydra", "target"), ("medusa", "user"),
        ("netcat", "target"), ("socat", "target"), ("metasploit", "target"), ("msfvenom", "lhost"),
        ("weevely", "password"), ("cewl", "url"), ("wapiti", "url"), ("aircrack-ng", "essid"),
    ],
)
def test_values_that_look_like_options_are_refused(tool_id, field):
    payload = {**GOOD, field: "--script=evil", "bssid": ""}
    with pytest.raises(commands.BadInput):
        commands.build(tool_id, payload, CTX)


def test_dns_and_searchsploit_and_tcpdump_refuse_option_words():
    for tool_id, field, value in (
        ("dns", "name", "example.com -f /etc/passwd"),
        ("dns", "name", "+tcp example.com"),
        ("searchsploit", "query", "apache -x"),
        ("tcpdump", "filter", "port 53 -z /bin/sh"),
        ("tcpdump", "filter", "-w /tmp/x"),
    ):
        with pytest.raises(commands.BadInput):
            commands.build(tool_id, {**GOOD, field: value}, CTX)


def test_metasploit_only_runs_auxiliary_scanner_modules():
    ok = commands.build("metasploit", GOOD, CTX)
    assert ok[:3] == ["msfconsole", "-q", "-x"]
    for module in (
        "exploit/windows/smb/ms17_010_eternalblue",
        "auxiliary/admin/smb/psexec",
        "auxiliary/scanner/x; use exploit/multi/handler",
        "auxiliary/scanner/../../x",
        "use auxiliary/scanner/x",
    ):
        with pytest.raises(commands.BadInput):
            commands.build("metasploit", {**GOOD, "module": module}, CTX)
    with pytest.raises(commands.BadInput):
        commands.build("metasploit", {**GOOD, "target": "10.0.0.1; use exploit/x"}, CTX)


def test_password_tools_use_rockyou_not_the_directory_list():
    assert commands.ROCKYOU in commands.build("john", GOOD, CTX)[1]
    hashcat = commands.build("hashcat", GOOD, CTX)
    assert hashcat[-1] == commands.ROCKYOU and "-a" in hashcat
    assert commands.DIRB_COMMON not in " ".join(hashcat)


def test_hashcat_mask_and_mode_are_validated():
    assert commands.build("hashcat", {**GOOD, "mask": "?d?d?d?d"}, CTX)[-1] == "?d?d?d?d"
    for bad in ({"mask": "-a 0"}, {"mode": "0 -o /tmp/x"}, {"mode": "abc"}):
        with pytest.raises(commands.BadInput):
            commands.build("hashcat", {**GOOD, **bad}, CTX)


def test_services_and_choices_must_match_a_fixed_list():
    for tool_id, field in (("hydra", "service"), ("medusa", "service"),
                           ("msfvenom", "payload"), ("msfvenom", "format"),
                           ("volatility3", "plugin")):
        with pytest.raises(commands.BadInput):
            commands.build(tool_id, {**GOOD, field: "evil; rm -rf /"}, CTX)


def test_missing_evidence_file_is_a_clear_error_not_an_empty_argument():
    with pytest.raises(commands.BadInput):
        commands.build("binwalk", {**GOOD, "file": "gone.bin"}, CTX)


def test_empty_wordlists_are_refused():
    with pytest.raises(commands.BadInput):
        commands.build("hydra", GOOD, {**CTX, "files": {}})


def test_steghide_keeps_an_empty_passphrase_so_it_never_prompts():
    argv = commands.build("steghide", GOOD, CTX)
    assert argv[argv.index("-p") + 1] == ""
    assert "-f" in argv


def test_ffuf_requires_fuzz_marker():
    with pytest.raises(commands.BadInput):
        commands.build("ffuf", {**GOOD, "url": "https://x.test/"}, CTX)


def test_tcpdump_is_bounded():
    argv = commands.build("tcpdump", {**GOOD, "count": "10"}, CTX)
    assert argv[argv.index("-c") + 1] == "10"
    assert commands.timeout_for("tcpdump", 180) == 30
    with pytest.raises(commands.BadInput):
        commands.build("tcpdump", {**GOOD, "count": "999999"}, CTX)


def test_crunch_cannot_explode():
    with pytest.raises(commands.BadInput):
        commands.build("crunch", {**GOOD, "min": "8", "max": "12", "charset": "abcdefghijklmnop"}, CTX)


def test_msfvenom_and_weevely_write_only_into_the_work_dir():
    assert commands.build("msfvenom", GOOD, CTX)[-1].startswith("/w/")
    assert commands.build("weevely", GOOD, CTX)[-1].startswith("/w/")
