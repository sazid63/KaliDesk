"""The catalog is the single source of truth; these tests keep it honest."""
from __future__ import annotations

import server.catalog as catalog


def test_app_metadata_present():
    meta = catalog.app_meta()
    assert meta.get("name")
    assert "kali" in meta["name"].lower()


def test_categories_are_well_formed():
    cats = catalog.categories()
    assert cats, "the catalog must define at least one category"
    for cat in cats:
        assert cat["id"] and cat["name"]


def test_every_tool_has_the_required_fields():
    tools = catalog.tools()
    assert len(tools) >= 20, "expected a substantial catalog"
    category_ids = {c["id"] for c in catalog.categories()}
    seen: set[str] = set()
    for tool in tools:
        tool_id = tool.get("id")
        assert tool_id, f"a tool entry is missing an id: {tool!r}"
        assert tool_id not in seen, f"duplicate tool id: {tool_id}"
        seen.add(tool_id)
        for field in ("name", "category", "summary"):
            assert tool.get(field), f"{tool_id} is missing {field}"
        assert tool["category"] in category_ids, f"{tool_id} uses an unknown category"
        assert isinstance(tool.get("prerequisites"), list), f"{tool_id} prerequisites"
        assert tool.get("usage"), f"{tool_id} is missing usage text"


def test_baseline_tools_have_packages():
    for tool in catalog.tools():
        if tool.get("baseline"):
            assert tool.get("packages"), f"{tool['id']} is baseline but has no packages"


def test_lookup_by_id():
    assert catalog.get("nmap") is not None
    assert catalog.get("does-not-exist") is None
