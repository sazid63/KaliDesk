"""Catalog loader.

``catalog/tools.yaml`` is the single source of truth for the tools the app
knows about. Everything the dashboard shows - tiles, prerequisites, usage and
the examples - comes from here.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

import kws.paths as kws_paths

CATALOG_PATH = Path(kws_paths.resource("catalog", "tools.yaml"))


@lru_cache(maxsize=4)
def _load(path: str | None = None) -> dict[str, Any]:
    src = Path(path) if path else CATALOG_PATH
    data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    data.setdefault("categories", [])
    data.setdefault("tools", [])
    return data


def app_meta() -> dict[str, Any]:
    return dict(_load().get("app", {}))


def categories() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for cat in _load().get("categories", []):
        if isinstance(cat, dict):
            cid = str(cat.get("id") or cat.get("name") or "")
            out.append({"id": cid, "name": str(cat.get("name") or cid)})
        else:
            out.append({"id": str(cat), "name": str(cat)})
    return out


def tools() -> list[dict[str, Any]]:
    return list(_load().get("tools", []))


def get(tool_id: str) -> dict[str, Any] | None:
    for tool in tools():
        if tool.get("id") == tool_id:
            return tool
    return None


def baseline_ids() -> list[str]:
    return [t.get("id") for t in tools() if t.get("baseline")]


def installable_ids() -> list[str]:
    return [t.get("id") for t in tools() if t.get("packages")]
