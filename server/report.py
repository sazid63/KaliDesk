"""Report rendering.

Everything from a tool is escaped before it lands in a report, so output can
never inject HTML/JS into a document you open in a browser.
"""
from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime, timezone
from typing import Any

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def to_json(findings: list[dict[str, Any]], app_name: str) -> str:
    payload = {
        "app": app_name,
        "generated": _stamp(),
        "finding_count": len(findings),
        "findings": findings,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def to_csv(findings: list[dict[str, Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["created", "tool", "target", "severity", "title", "detail"])
    for f in sorted(findings, key=lambda r: _SEV_ORDER.get(r.get("severity", "info"), 9)):
        writer.writerow(
            [
                f.get("created", ""),
                f.get("tool", ""),
                f.get("target", ""),
                f.get("severity", ""),
                f.get("title", ""),
                f.get("detail", ""),
            ]
        )
    return out.getvalue()


def to_html(findings: list[dict[str, Any]], app_name: str) -> str:
    rows = []
    for f in sorted(findings, key=lambda r: _SEV_ORDER.get(r.get("severity", "info"), 9)):
        sev = html.escape(str(f.get("severity", "info")))
        rows.append(
            "<tr>"
            f"<td>{sev}</td>"
            f"<td>{html.escape(str(f.get('tool', '')))}</td>"
            f"<td>{html.escape(str(f.get('target', '')))}</td>"
            f"<td>{html.escape(str(f.get('title', '')))}</td>"
            f"<td><pre>{html.escape(str(f.get('detail', '')))}</pre></td>"
            f"<td>{html.escape(str(f.get('created', '')))}</td>"
            "</tr>"
        )
    body = "\n".join(rows) if rows else "<tr><td colspan='6'>No findings recorded.</td></tr>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(app_name)} report</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111; }}
 h1 {{ font-size: 1.3rem; }}
 table {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
 th, td {{ border: 1px solid #ccc; padding: .4rem .5rem; text-align: left; vertical-align: top; }}
 th {{ background: #f2f2f2; }}
 pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
</style></head>
<body>
<h1>{html.escape(app_name)} &mdash; findings report</h1>
<p>Generated {html.escape(_stamp())}. {len(findings)} finding(s).</p>
<table>
<thead><tr><th>Severity</th><th>Tool</th><th>Target</th><th>Title</th><th>Detail</th><th>When</th></tr></thead>
<tbody>
{body}
</tbody></table>
</body></html>"""
