"""MCP Client for Kali Linux Windows Substitute.

Connects to an MCP server (stdlib or HTTP) and exposes tools/resources
to the AI chat backend.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from typing import Any


class MCPClient:
    """Client for communicating with an MCP server."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._running = False

    def connect_stdio(self, cmd: list[str]) -> bool:
        """Connect to an MCP server via stdio subprocess."""
        try:
            self._process = subprocess.Popen(  # noqa: S603
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            self._running = True
            # Send initialize
            self._send({"id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05"}})
            return True
        except (OSError, FileNotFoundError):
            return False

    def connect_http(self, url: str) -> bool:
        """Connect to an MCP server via HTTP."""
        self._url = url
        self._running = True
        return True

    def _send(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Send a JSON-RPC request via stdio and read the response."""
        if self._process is None or self._process.stdin is None:
            return None
        with self._lock:
            try:
                self._process.stdin.write(json.dumps(request) + "\n")
                self._process.stdin.flush()
                if self._process.stdout:
                    line = self._process.stdout.readline()
                    if line:
                        return json.loads(line.strip())
            except (OSError, json.JSONDecodeError):
                return None
        return None

    def _send_http(self, method: str,
                 params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Send a request via HTTP."""
        url = f"{self._url}/mcp" if hasattr(self, "_url") else None
        if url is None:
            return None
        body = json.dumps({"id": 1, "method": method, "params": params or {}}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from the MCP server."""
        result = self._send({"id": 2, "method": "tools/list"})
        if result is None:
            result = self._send_http("tools/list")
        tools = (result or {}).get("result", {}).get("tools", [])
        return tools if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the MCP server."""
        params = {"name": name, "arguments": arguments}
        result = self._send({"id": 3, "method": "tools/call", "params": params})
        if result is None:
            result = self._send_http("tools/call", params)
        return (result or {}).get("result", {}) if result else {}

    def list_resources(self) -> list[dict[str, Any]]:
        """List available resources from the MCP server."""
        result = self._send({"id": 4, "method": "resources/list"})
        if result is None:
            result = self._send_http("resources/list")
        resources = (result or {}).get("result", {}).get("resources", [])
        return resources if isinstance(resources, list) else []

    def read_resource(self, uri: str) -> str:
        """Read a resource from the MCP server."""
        params = {"uri": uri}
        result = self._send({"id": 5, "method": "resources/read", "params": params})
        if result is None:
            result = self._send_http("resources/read", params)
        contents = (result or {}).get("result", {}).get("contents", [])
        if isinstance(contents, list) and contents:
            return str(contents[0].get("text", ""))
        return ""

    def close(self) -> None:
        """Close the connection."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self._process.kill()
                except OSError:
                    pass
        self._running = False

    @staticmethod
    def auto_discover() -> MCPClient | None:
        """Auto-discover and connect to the built-in MCP server."""
        try:
            client = MCPClient()
            cmd = [sys.executable, "-m", "server.mcp_server"]
            if client.connect_stdio(cmd):
                client._discovered = True
                return client
            return None
        except Exception:  # noqa: BLE001
            return None
