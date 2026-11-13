"""MCP server for Kali Linux Windows Substitute.

Lets an MCP client (for example Claude Desktop) use this app's tools. It speaks a
subset of the Model Context Protocol (JSON-RPC 2.0, one message per line over stdio):

    python -m server.mcp_server

Tools
  kali_desktop_run_tool   run a catalog tool through the runtime agent
  kali_desktop_list_files list the evidence or work folder
  kali_desktop_read_file  read a file in the evidence or work folder
  kali_desktop_write_file write a text file into the work folder

Resources: findings://all and audit://all.

Safety: a tool run goes through the same scope guard and allow-list as the UI, and a
client can never confirm a public target (only a person clicking in the app can), so
only private/loopback targets are reachable from here. Files are limited to the
evidence and work folders; the database, secrets and everything else are out of reach.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import kws.paths as kws_paths
import server.config as config
import server.db as db
import server.history as history
import server.tools as tools_api
from kws.__about__ import __version__

PROTOCOL_VERSION = "2024-11-05"
MAX_READ = 512 * 1024
MAX_WRITE = 1024 * 1024
SERVER_INFO = {"name": "kali-desktop-mcp", "version": __version__}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "kali_desktop_run_tool",
        "description": (
            "Run a tool from the catalog in the private Kali runtime. Only private or "
            "loopback targets are allowed from here."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_id": {"type": "string", "description": "Tool id from the catalog"},
                "payload": {"type": "object", "description": "The tool's form fields"},
            },
            "required": ["tool_id", "payload"],
        },
    },
    {
        "name": "kali_desktop_list_files",
        "description": "List files in the evidence or work folder.",
        "inputSchema": {
            "type": "object",
            "properties": {"directory": {"type": "string", "enum": ["evidence", "work"]}},
            "required": ["directory"],
        },
    },
    {
        "name": "kali_desktop_read_file",
        "description": "Read a text file from the evidence or work folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "enum": ["evidence", "work"]},
                "name": {"type": "string", "description": "File name inside that folder"},
            },
            "required": ["directory", "name"],
        },
    },
    {
        "name": "kali_desktop_write_file",
        "description": "Write a text file into the work folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "File name (no folders)"},
                "content": {"type": "string"},
            },
            "required": ["name", "content"],
        },
    },
]

RESOURCES = [
    {"uri": "findings://all", "name": "Findings", "mimeType": "application/json",
     "description": "All findings recorded in the app"},
    {"uri": "audit://all", "name": "Audit log", "mimeType": "application/json",
     "description": "The app's audit log"},
]


class RPCError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _text(text: str, error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if error:
        result["isError"] = True
    return result


def _folder(name: str) -> Path | None:
    return {"evidence": kws_paths.evidence_dir(), "work": kws_paths.work_dir()}.get(name)


def _file_in(directory: str, name: str) -> Path | None:
    """A regular file directly inside the evidence/work folder (no subfolders, no links)."""
    base = _folder(directory)
    if base is None or not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    path = base / name
    if path.is_symlink():
        return None
    try:
        path.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return path


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "kali_desktop_run_tool":
        payload = args.get("payload")
        if not isinstance(payload, dict):
            return _text("payload must be an object", True)
        tool_id = str(args.get("tool_id", ""))
        started = time.time()
        # No user_confirmed: a client cannot grant itself permission to hit public hosts.
        result, status = tools_api.run(config.load(), tool_id, payload)
        duration_ms = round((time.time() - started) * 1000, 1)
        # Record the run as the app does, so MCP runs show in History and the audit log.
        rc, ok, preview = tools_api.run_outcome(result, status)
        target = tools_api._target_of(payload)  # every host field, as the scope guard saw them
        history.record_run(tool_id, target, payload, rc, duration_ms, preview, ok)
        db.audit("mcp", f"tool:{tool_id}", target, "ok" if ok else f"status {status}, rc {rc}")
        return _text(json.dumps(result), status != 200)

    if name == "kali_desktop_list_files":
        base = _folder(str(args.get("directory", "")))
        if base is None:
            return _text("directory must be 'evidence' or 'work'", True)
        files = sorted(p.name for p in base.iterdir() if p.is_file() and not p.is_symlink())
        return _text(json.dumps(files))

    if name == "kali_desktop_read_file":
        path = _file_in(str(args.get("directory", "")), str(args.get("name", "")))
        if path is None or not path.is_file():
            return _text("no such file", True)
        with path.open("rb") as handle:  # never load more than MAX_READ bytes
            data = handle.read(MAX_READ)
        return _text(data.decode("utf-8", errors="replace"))

    if name == "kali_desktop_write_file":
        path = _file_in("work", str(args.get("name", "")))
        content = str(args.get("content", ""))
        if path is None:
            return _text("file name must be a plain name inside the work folder", True)
        if len(content.encode("utf-8")) > MAX_WRITE:
            return _text("content too large", True)
        path.write_text(content, encoding="utf-8")
        return _text(f"wrote {len(content)} characters to work/{path.name}")

    return _text(f"unknown tool: {name}", True)


def read_resource(uri: str) -> dict[str, Any]:
    if uri == "findings://all":
        rows = db.findings()
    elif uri == "audit://all":
        rows = db.audits()
    else:
        raise RPCError(-32002, f"unknown resource: {uri}")
    return {"contents": [{"uri": uri, "mimeType": "application/json",
                          "text": json.dumps(rows, default=str)}]}


class MCPServer:
    """Handles one connection; ``handle`` maps a decoded message to a reply (or None)."""

    def __init__(self) -> None:
        self.initialized = False

    def dispatch(self, method: str, params: Any) -> Any:
        if method == "initialize":
            if not isinstance(params, dict) or not params.get("protocolVersion"):
                raise RPCError(-32602, "missing protocolVersion")
            self.initialized = True
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": SERVER_INFO,
            }
        if method == "ping":
            return {}
        if not self.initialized:
            raise RPCError(-32600, "server not initialized")
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            if not isinstance(params, dict):
                raise RPCError(-32602, "invalid params")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                raise RPCError(-32602, "arguments must be an object")
            return call_tool(str(params.get("name", "")), args)
        if method == "resources/list":
            return {"resources": RESOURCES}
        if method == "resources/read":
            if not isinstance(params, dict):
                raise RPCError(-32602, "invalid params")
            return read_resource(str(params.get("uri", "")))
        raise RPCError(-32601, f"method not found: {method}")

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32600, "message": "invalid request"}}
        method = message.get("method")
        if not isinstance(method, str):
            return None  # a response from the client; nothing to do
        if "id" not in message:
            return None  # notifications (e.g. notifications/initialized) get no reply
        try:
            result = self.dispatch(method, message.get("params"))
            return {"jsonrpc": "2.0", "id": message["id"], "result": result}
        except RPCError as exc:
            return {"jsonrpc": "2.0", "id": message["id"],
                    "error": {"code": exc.code, "message": exc.message}}
        except Exception as exc:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": message["id"],
                    "error": {"code": -32603, "message": f"internal error: {type(exc).__name__}"}}

    def run_stdio(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            if len(line) > 1_000_000:
                reply: dict[str, Any] | None = {
                    "jsonrpc": "2.0", "id": None,
                    "error": {"code": -32000, "message": "request too large"}}
            else:
                try:
                    reply = self.handle(json.loads(line))
                except json.JSONDecodeError:
                    reply = {"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "parse error"}}
            if reply is not None:
                print(json.dumps(reply), flush=True)


def main() -> int:
    db.init_db()
    try:
        MCPServer().run_stdio()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
