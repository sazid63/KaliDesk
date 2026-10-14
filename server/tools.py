"""Run tools through the in-runtime agent, and manage installed tools.

The agent lives inside the app's private WSL2 distribution and is the only
component that actually executes a binary. This module builds the request,
applies the scope guard, and interprets the reply. It never runs a process on
Windows itself.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import kws_paths
import kws_secrets
import server.catalog as catalog
import server.commands as commands
import server.security as security

AGENT_TOKEN_SECRET = "agent_token"
DEFAULT_TIMEOUT = 180


# --- agent transport ------------------------------------------------------

def _token() -> str:
    return kws_secrets.get_secret(AGENT_TOKEN_SECRET)


def _request(cfg, method: str, path: str, body: dict | None = None,
             timeout: int = 30) -> dict[str, Any]:
    url = cfg.agent_url.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    token = _token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def agent_get(cfg, path: str, timeout: int = 15) -> dict[str, Any]:
    return _request(cfg, "GET", path, None, timeout)


def agent_post(cfg, path: str, body: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    return _request(cfg, "POST", path, body, timeout)


def agent_online(cfg) -> bool:
    try:
        return bool(agent_get(cfg, "/health", timeout=5).get("ok"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


# --- helpers --------------------------------------------------------------

def _target_of(payload: dict[str, Any]) -> str:
    for key in ("target", "url", "query", "name", "file"):
        if payload.get(key):
            return str(payload[key])
    return ""


def _ctx(payload: dict[str, Any], tool_id: str) -> dict[str, Any]:
    work = kws_paths.work_dir()
    file_paths: dict[str, str] = {}
    for name, content in commands.files_for(tool_id, payload).items():
        path = work / name
        path.write_text(content, encoding="utf-8")
        file_paths[name] = kws_paths.to_wsl_path(path)

    evidence: dict[str, str] = {}
    ev_dir = kws_paths.evidence_dir()
    for item in ev_dir.iterdir() if ev_dir.exists() else []:
        if item.is_file():
            evidence[item.name] = kws_paths.to_wsl_path(item)

    return {
        "work": kws_paths.to_wsl_path(work),
        "files": file_paths,
        "evidence": evidence,
    }


# --- public operations ----------------------------------------------------

def technology_status(cfg) -> dict[str, Any]:
    online = agent_online(cfg)
    return {"online": online, "distro": cfg.runtime_distro}


def run(cfg, tool_id: str, payload: dict[str, Any], timeout: int = DEFAULT_TIMEOUT):
    tool = catalog.get(tool_id)
    if tool is None:
        return {"error": "unknown tool"}, 404

    target = _target_of(payload)
    confirmed = bool(payload.get("confirm_external"))
    allowed, reason = security.scope_allows(target, confirmed, cfg.private_ranges)
    if not allowed:
        return {"error": "target is out of scope", "detail": reason}, 403

    argv = commands.build(tool_id, payload, _ctx(payload, tool_id))
    if argv is None:
        return {
            "error": "this tool is not automated yet",
            "detail": (
                "The app knows this tool, but there is no safe one-click form "
                "for it. Open the runtime shell and run it interactively."
            ),
        }, 501

    body = {
        "tool": tool_id,
        "argv": argv,
        "target": target,
        "confirm_external": confirmed,
        "timeout": timeout,
    }
    try:
        result = agent_post(cfg, "/run", body, timeout + 15)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        return {"error": f"the runtime refused the request ({exc.code})",
                "detail": detail}, exc.code
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"error": "the runtime is not reachable",
                "detail": str(exc)}, 503
    return result, 200


def preview(cfg, tool_id: str, payload: dict[str, Any]):
    """Return the argv that would run, without running it."""
    if catalog.get(tool_id) is None:
        return {"error": "unknown tool"}, 404
    argv = commands.build(tool_id, payload, _ctx(payload, tool_id))
    if argv is None:
        return {"error": "this tool is not automated yet",
                "detail": "Run it from the runtime shell instead."}, 501
    return {"argv": argv}, 200


def install(cfg, tool_id: str, timeout: int = 1800):
    if catalog.get(tool_id) is None:
        return {"error": "unknown tool"}, 404
    try:
        return agent_post(cfg, "/tools/install", {"tool": tool_id}, timeout), 200
    except urllib.error.HTTPError as exc:
        return {"error": f"the runtime refused ({exc.code})",
                "detail": exc.read().decode(errors="replace")}, exc.code
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"error": "the runtime is not reachable", "detail": str(exc)}, 503


def remove(cfg, tool_id: str, timeout: int = 1800):
    if catalog.get(tool_id) is None:
        return {"error": "unknown tool"}, 404
    try:
        return agent_post(cfg, "/tools/remove", {"tool": tool_id}, timeout), 200
    except urllib.error.HTTPError as exc:
        return {"error": f"the runtime refused ({exc.code})",
                "detail": exc.read().decode(errors="replace")}, exc.code
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"error": "the runtime is not reachable", "detail": str(exc)}, 503


def manage_list(cfg) -> dict[str, Any]:
    rows = []
    present: dict[str, bool] = {}
    online = False
    try:
        status = agent_get(cfg, "/tools")
        present = {t.get("id"): bool(t.get("present")) for t in status.get("tools", [])}
        online = True
    except (urllib.error.URLError, TimeoutError, ValueError):
        online = False

    for tool in catalog.tools():
        tool_id = tool.get("id")
        if not tool.get("packages"):
            continue
        rows.append({
            "id": tool_id,
            "name": tool.get("name") or tool_id,
            "category": tool.get("category") or "other",
            "summary": tool.get("summary") or "",
            "packages": list(tool.get("packages") or []),
            "baseline": bool(tool.get("baseline")),
            "prerequisites": list(tool.get("prerequisites") or []),
            "present": present.get(tool_id, None) if online else None,
        })
    return {"online": online, "tools": rows}


def evidence_files() -> list[str]:
    ev = kws_paths.evidence_dir()
    if not ev.exists():
        return []
    return sorted(p.name for p in ev.iterdir() if p.is_file())
