"""MCP Server for Kali Linux Windows Substitute.

Implements a subset of the Model Context Protocol (JSON-RPC 2.0 over stdio)
to expose KWS functionality to AI assistants.

Built-in tools:
  - kali_desktop_run_tool: run a tool via the agent
  - kali_desktop_read_file: read a file (sandboxed to user_data_dir)
  - kali_desktop_write_file: write a file (sandboxed to work_dir only)
  - kali_desktop_list_files: list files in a directory (sandboxed)

Built-in resources:
  - file://...: files within user_data_dir
  - findings://: all findings from the DB
  - audit://: all audit entries from the DB
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import kws_paths
import server.config as config
import server.db as db
import server.tools as tools_api

# --- Built-in tool definitions ------------------------------------------------

def _list_builtin_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "kali_desktop_run_tool",
            "description": "Run a tool in the runtime agent. Target must pass the scope guard.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tool_id": {"type": "string", "description": "Tool ID from the catalog"},
                    "payload": {"type": "object", "description": "Tool arguments"},
                },
                "required": ["tool_id", "payload"],
            },
        },
        {
            "name": "kali_desktop_read_file",
            "description": "Read a file within the user data directory (sandboxed).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to user_data_dir"},
                },
                "required": ["path"],
            },
        },
        {
            "name": "kali_desktop_write_file",
            "description": "Write a text file to the work directory (sandboxed).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Filename in work_dir"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "kali_desktop_list_files",
            "description": "List files in the evidence or work directory (sandboxed).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string",
                                   "enum": ["evidence", "work"],
                                   "description": "Which directory to list"},
                },
                "required": ["directory"],
            },
        },
    ]


def _list_builtin_resources() -> list[dict[str, Any]]:
    return [
        {
            "uri": "file://",
            "name": "User data files",
            "description": "Files within the user data directory",
            "mimeType": "application/json",
        },
        {
            "uri": "findings://all",
            "name": "Findings",
            "description": "All findings from the database",
            "mimeType": "application/json",
        },
        {
            "uri": "audit://all",
            "name": "Audit log",
            "description": "All audit entries from the database",
            "mimeType": "application/json",
        },
    ]


def _sandbox_path(relative: str) -> Path | None:
    """Resolve a relative path within user_data_dir, preventing escapes."""
    if not relative:
        return None
    base = kws_paths.user_data_dir()
    try:
        resolved = (base / relative).resolve()
    except (OSError, ValueError):
        return None
    # Ensure resolved is within base
    try:
        resolved.relative_to(base)
    except ValueError:
        return None
    return resolved


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a built-in tool and return the result."""
    if name == "kali_desktop_run_tool":
        tool_id = str(arguments.get("tool_id", ""))
        payload = arguments.get("payload", {})
        if not isinstance(payload, dict):
            return {"content": [{"type": "text", "text": "payload must be an object"}],
                    "isError": True}
        cfg = config.load()
        result, status = tools_api.run(cfg, tool_id, payload)
        return {"content": [{"type": "text", "text": json.dumps(result)}],
                "isError": status != 200}

    if name == "kali_desktop_read_file":
        path = str(arguments.get("path", ""))
        resolved = _sandbox_path(path)
        if resolved is None or not resolved.exists():
            return {"content": [{"type": "text", "text": f"Cannot read: {path}"}],
                    "isError": True}
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
            return {"content": [{"type": "text", "text": text}]}
        except OSError as exc:
            return {"content": [{"type": "text", "text": str(exc)}],
                    "isError": True}

    if name == "kali_desktop_write_file":
        path = str(arguments.get("path", ""))
        content = str(arguments.get("content", ""))
        # Only allow writes to the work directory
        work_dir = kws_paths.work_dir()
        try:
            resolved = (work_dir / path).resolve()
            resolved.relative_to(work_dir)
        except (OSError, ValueError):
            return {"content": [{"type": "text", "text": f"Cannot write: {path}"}],
                    "isError": True}
        try:
            resolved.write_text(content, encoding="utf-8")
            msg = f"Written {len(content)} bytes to {path}"
            return {"content": [{"type": "text", "text": msg}]}
        except OSError as exc:
            return {"content": [{"type": "text", "text": str(exc)}],
                    "isError": True}

    if name == "kali_desktop_list_files":
        directory = str(arguments.get("directory", ""))
        if directory == "evidence":
            target_dir = kws_paths.evidence_dir()
        elif directory == "work":
            target_dir = kws_paths.work_dir()
        else:
            return {"content": [{"type": "text", "text": f"Unknown directory: {directory}"}],
                    "isError": True}
        try:
            files = sorted(p.name for p in target_dir.iterdir() if p.is_file()
                           if not p.is_symlink())
            return {"content": [{"type": "text", "text": json.dumps(files)}]}
        except OSError as exc:
            return {"content": [{"type": "text", "text": str(exc)}],
                    "isError": True}

    return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True}


def _read_resource(uri: str) -> dict[str, Any]:
    """Read a built-in resource."""
    if uri in ("findings://all", "findings://"):
        rows = db.findings()
        return {"contents": [{"uri": uri, "text": json.dumps(rows, default=str)}]}

    if uri in ("audit://all", "audit://"):
        rows = db.audits()
        return {"contents": [{"uri": uri, "text": json.dumps(rows, default=str)}]}

    if uri.startswith("file://"):
        rel = uri[len("file://"):]
        resolved = _sandbox_path(rel)
        if resolved is None or not resolved.exists():
            return {"contents": [{"uri": uri, "text": ""}]}
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
            return {"contents": [{"uri": uri, "text": text}]}
        except OSError:
            return {"contents": [{"uri": uri, "text": ""}]}

    return {"contents": [{"uri": uri, "text": ""}]}


class MCPServer:
    """MCP server (JSON-RPC 2.0 over stdio)."""

    def __init__(self) -> None:
        self._initialized = False

    def _handle_request(self, request_id: Any, method: str, params: Any) -> dict[str, Any]:
        if not self._initialized and method != "initialize":
            return {"error": {"code": -32600, "message": "Server not initialized"},
                    "id": request_id}

        if method == "initialize":
            self._initialized = True
            return {"id": request_id, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "kali-desktop-mcp", "version": "1.0.0"},
            }}

        if method == "initialized":
            return {"id": request_id, "result": None}

        if method == "tools/list":
            return {"id": request_id, "result": {"tools": _list_builtin_tools()}}

        if method == "tools/call":
            if not isinstance(params, dict):
                return {"error": {"code": -32602, "message": "Invalid params", "id": request_id}}
            name = str(params.get("name", ""))
            arguments = params.get("arguments", {})
            result = _call_tool(name, arguments)
            return {"id": request_id, "result": result}

        if method == "resources/list":
            return {"id": request_id, "result": {"resources": _list_builtin_resources()}}

        if method == "resources/read":
            if not isinstance(params, dict):
                return {"error": {"code": -32602, "message": "Invalid params", "id": request_id}}
            uri = str(params.get("uri", ""))
            result = _read_resource(uri)
            return {"id": request_id, "result": result}

        return {"error": {"code": -32601, "message": f"Method not found: {method}",
                           "id": request_id}}

    def run_stdio(self) -> None:
        """Run the MCP server over stdio, processing one request per line."""
        self._initialized = True  # Allow requests immediately for simplicity
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                resp = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "Parse error"}}
                print(json.dumps(resp), flush=True)
                continue

            request_id = req.get("id")
            method = str(req.get("method", ""))
            params = req.get("params")
            result = self._handle_request(request_id, method, params)
            resp = {"jsonrpc": "2.0", **result}
            print(json.dumps(resp), flush=True)


def main() -> int:
    server = MCPServer()
    try:
        server.run_stdio()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
