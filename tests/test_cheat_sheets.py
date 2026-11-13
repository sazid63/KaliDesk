"""Cheat sheets stay in step with the catalog."""
from __future__ import annotations

import server.catalog as catalog
import server.cheat_sheets as cheat_sheets


def test_every_tool_has_a_sheet_and_every_sheet_has_a_tool():
    tools = {t["id"] for t in catalog.tools() if not t.get("builtin")}
    sheets = set(cheat_sheets.CHEAT_SHEETS)
    assert tools - sheets == set(), "tools without a cheat sheet"
    assert sheets - tools == set(), "cheat sheets for tools the app does not have"


def test_sheets_are_well_formed():
    for tool_id, sheet in cheat_sheets.CHEAT_SHEETS.items():
        assert sheet["title"].strip() and sheet["sections"], tool_id
        for section in sheet["sections"]:
            assert section["heading"].strip() and section["content_md"].strip(), tool_id


def test_routes(client):
    listing = client.get("/api/cheatsheets").get_json()["cheatsheets"]
    assert len(listing) >= 45
    assert client.get("/api/cheatsheets/nmap").get_json()["sections"]
    assert client.get("/api/cheatsheets/not-a-tool").status_code == 404
