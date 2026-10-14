"""Reports must never let tool output inject markup."""
from __future__ import annotations

import json

import server.report as report

FINDINGS = [
    {
        "created": "2026-01-01T00:00:00+00:00",
        "tool": "nmap",
        "target": "192.168.1.10",
        "severity": "high",
        "title": "Open SSH",
        "detail": "<script>alert('x')</script>",
    }
]


def test_html_escapes_tool_output():
    body = report.to_html(FINDINGS, "Test App")
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_html_escapes_app_name():
    body = report.to_html([], "<img src=x onerror=alert(1)>")
    assert "<img src=x" not in body


def test_csv_has_a_header_and_a_row():
    body = report.to_csv(FINDINGS)
    lines = [line for line in body.splitlines() if line]
    assert lines[0].startswith("created,")
    assert "192.168.1.10" in lines[1]


def test_json_is_valid_and_counted():
    payload = json.loads(report.to_json(FINDINGS, "Test App"))
    assert payload["finding_count"] == 1
    assert payload["findings"][0]["tool"] == "nmap"


def test_empty_report_still_renders():
    assert "No findings recorded" in report.to_html([], "Test App")
