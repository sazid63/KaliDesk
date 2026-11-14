"""Achievements are earned from real history, and the UI only calls routes that exist."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import server.achievements as achievements
import server.app as app_module
import server.config as config
import server.db as db
import server.history as history

UI = Path(__file__).resolve().parent.parent / "ui"


@pytest.fixture(autouse=True)
def clean():
    db.init_db()
    with db.connect() as conn:
        conn.execute("DELETE FROM run_history")
        conn.execute("DELETE FROM achievements")


def run(tool, ok=True, ms=2000):
    history.record_run(tool, "10.0.0.1", {}, 0 if ok else 1, ms, "", ok)
    return achievements.evaluate()


def progress(key):
    return next(a for a in achievements.list_achievements() if a["key"] == key)


def test_nothing_is_unlocked_without_runs():
    assert achievements.evaluate() == []
    assert not any(a["unlocked"] for a in achievements.list_achievements())


def test_first_run_unlocks_once():
    assert run("whois") == ["First Blood"] or "First Blood" in run("whois")
    assert run("whois") == []  # already unlocked


def test_counted_goals_need_the_full_count():
    for _ in range(4):
        run("nmap")
    assert progress("port_scanner")["progress"] == 4 and not progress("port_scanner")["unlocked"]
    assert "Port Scanner" in run("masscan")  # nmap and masscan both count
    assert progress("port_scanner")["unlocked"]


def test_only_successful_runs_count_where_required():
    run("sqlmap", ok=False)
    assert not progress("vuln_hunter")["unlocked"]
    assert "Vulnerability Hunter" in run("sqlmap", ok=True)


def test_speed_demon_needs_a_fast_success():
    run("dns", ok=True, ms=5000)
    run("dns", ok=False, ms=10)
    assert not progress("speed_demon")["unlocked"]
    assert "Speed Demon" in run("dns", ok=True, ms=300)


def test_persistent_counts_distinct_tools():
    for tool in ("nmap", "whois", "dns", "nikto", "sqlmap", "john", "hashcat", "exiftool", "tshark"):
        run(tool)
    assert not progress("persistent")["unlocked"]
    assert "Persistent" in run("strace")


def test_catalog_ids_in_definitions_exist():
    import server.catalog as catalog

    known = {t["id"] for t in catalog.tools()}
    for key, ach in achievements.ACHIEVEMENTS.items():
        for tool in ach.get("tools", ()):
            assert tool in known, f"{key} refers to unknown tool {tool}"


def test_there_is_no_manual_unlock_route(client):
    assert client.post("/api/achievements/first_run/unlock", json={}).status_code in (403, 404, 405)
    resp = client.post("/api/achievements/first_run/unlock", json={},
                       headers={"X-KWS-CSRF": "test-csrf"})
    assert resp.status_code in (404, 405)


# --- the UI may only call routes the server really has ---------------------------------

_TERM = r'(?:"[^"]*"|[A-Za-z_][\w.\[\]]*(?:\([^)]*\))?)'
CALL = re.compile(
    r'\bapi\(\s*"(GET|POST|PUT|DELETE)"\s*,\s*(' + _TERM + r'(?:\s*\+\s*' + _TERM + r')*)'
)


def ui_calls():
    for js in sorted(UI.glob("*.js")):
        text = js.read_text(encoding="utf-8")
        for method, expr in CALL.findall(text):
            parts = [p.strip() for p in re.split(r"\s*\+\s*", expr)]
            path = "".join(p[1:-1] if p.startswith('"') else "<x>" for p in parts)
            if path.startswith("/api/"):
                yield js.name, method, path.split("?")[0]


def route_matcher():
    application = app_module.create_app(config.load(), "t", "c")
    rules = []
    for rule in application.url_map.iter_rules():
        pattern = re.sub(r"<[^>]+>", "[^/]+", rule.rule)
        rules.append((re.compile("^" + pattern + "$"), rule.methods))
    return rules


def test_every_ui_api_call_matches_a_server_route():
    rules = route_matcher()
    calls = list(ui_calls())
    assert len(calls) > 30, "the contract scan found too few calls - the regex is broken"
    missing = []
    for file, method, path in calls:
        probe = path.replace("<x>", "abc")
        if not any(rx.match(probe) and method in methods for rx, methods in rules):
            missing.append(f"{file}: {method} {path}")
    assert not missing, "UI calls routes that do not exist:\n" + "\n".join(missing)


def test_ui_scripts_do_not_leak_helper_names_into_the_global_scope():
    """Panel scripts are wrapped in an IIFE so same-named helpers cannot collide."""
    for name in ("achievements", "cheat_sheets", "containers", "history", "notebook",
                 "onboarding", "playground", "recordings"):
        text = (UI / f"{name}.js").read_text(encoding="utf-8").lstrip()
        assert text.startswith("(function () {"), name


RESPONSE_KEYS = [
    ("/api/audit", "audit"), ("/api/findings", "findings"), ("/api/history", "history"),
    ("/api/recordings", "recordings"), ("/api/achievements", "achievements"),
    ("/api/notebook/entries", "entries"), ("/api/cheatsheets", "cheatsheets"),
    ("/api/containers", "containers"), ("/api/evidence", "files"),
    ("/api/tools/manage", "tools"), ("/api/catalog", "tools"),
]


@pytest.mark.parametrize(("path", "key"), RESPONSE_KEYS)
def test_ui_reads_the_keys_the_server_actually_sends(client, path, key):
    """Regression: the audit panel read data.audits while the server sent data.audit."""
    body = client.get(path).get_json()
    assert key in body, f"{path} no longer returns '{key}'"
    ui = "\n".join(p.read_text(encoding="utf-8") for p in UI.glob("*.js"))
    assert f"data.{key}" in ui, f"no UI script reads data.{key}"
