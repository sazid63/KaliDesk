"""MCP server: protocol correctness and the file/tool sandbox."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import kws.paths as kws_paths
import server.db as db
import server.mcp_server as mcp

ROOT = Path(__file__).resolve().parent.parent


def rpc(server, method, params=None, id_=1):
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    return server.handle(msg)


@pytest.fixture()
def server():
    db.init_db()
    s = mcp.MCPServer()
    assert "result" in rpc(s, "initialize", {"protocolVersion": "2024-11-05"})
    return s


def test_must_initialize_first():
    reply = rpc(mcp.MCPServer(), "tools/list")
    assert reply["error"]["code"] == -32600 and reply["id"] == 1
    assert rpc(mcp.MCPServer(), "initialize", {})["error"]["code"] == -32602


def test_notifications_get_no_reply(server):
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle({"jsonrpc": "2.0", "id": 9, "result": {}}) is None


def test_envelopes_are_valid_jsonrpc(server):
    ok = rpc(server, "tools/list")
    assert ok["jsonrpc"] == "2.0" and ok["id"] == 1 and "error" not in ok
    assert {t["name"] for t in ok["result"]["tools"]} >= {"kali_desktop_run_tool"}
    err = rpc(server, "nope/nope")
    assert err["error"]["code"] == -32601 and "id" not in err["error"] and err["id"] == 1
    assert server.handle("garbage")["error"]["code"] == -32600


def test_file_tools_are_sandboxed_to_evidence_and_work(server):
    ev = kws_paths.evidence_dir()
    (ev / "note.txt").write_text("hello", encoding="utf-8")
    def call(tool, **a):
        return rpc(server, "tools/call", {"name": tool, "arguments": a})["result"]

    assert "note.txt" in call("kali_desktop_list_files", directory="evidence")["content"][0]["text"]
    assert call("kali_desktop_read_file", directory="evidence", name="note.txt")["content"][0][
        "text"] == "hello"
    # nothing outside the two folders, no traversal, no database
    for bad in ("../kws.sqlite3", "..\\kws.sqlite3", "sub/../note.txt", "", ".."):
        assert call("kali_desktop_read_file", directory="evidence", name=bad).get("isError"), bad
    assert call("kali_desktop_read_file", directory="data", name="kws.sqlite3").get("isError")
    assert call("kali_desktop_write_file", name="../evil.txt", content="x").get("isError")
    assert not call("kali_desktop_write_file", name="ok.txt", content="x").get("isError")
    assert (kws_paths.work_dir() / "ok.txt").read_text(encoding="utf-8") == "x"
    assert not (ev / "evil.txt").exists()


def test_resources(server):
    assert "contents" in rpc(server, "resources/read", {"uri": "findings://all"})["result"]
    assert rpc(server, "resources/read", {"uri": "file:///etc/passwd"})["error"]["code"] == -32002
    assert rpc(server, "resources/read", {"uri": "file://kws.sqlite3"})["error"]


def test_a_client_cannot_confirm_a_public_target(server):
    reply = rpc(server, "tools/call", {"name": "kali_desktop_run_tool", "arguments": {
        "tool_id": "nmap", "payload": {"target": "8.8.8.8", "confirm_external": True}}})
    result = reply["result"]
    assert result["isError"] is True and "out of scope" in result["content"][0]["text"]


def test_stdio_loop_on_a_real_process():
    """Runs on Windows too: no select() on pipes any more."""
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "server.mcp_server"], input="\n".join(map(json.dumps, lines)) + "\n",
        capture_output=True, text=True, cwd=ROOT, timeout=60,
    )
    replies = [json.loads(x) for x in proc.stdout.splitlines() if x.strip()]
    assert [r["id"] for r in replies] == [1, 2]
    assert replies[1]["result"]["tools"]
