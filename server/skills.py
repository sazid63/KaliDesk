"""Skills Framework for Kali Linux Windows Substitute.

A Skill is a predefined tool invocation template that can be executed
with user-supplied parameters. Skills make complex tool chains reusable
and discoverable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import server.config as config
import server.tools as tools_api


@dataclass
class Skill:
    """A reusable tool invocation template."""

    name: str
    description: str
    category: str
    tool_id: str
    args_template: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Skill:
        """Create a Skill from a DB row."""
        import json as _json
        return cls(
            name=row.get("name", ""),
            description=row.get("description", ""),
            category=row.get("category", "general"),
            tool_id=row.get("tool_id", ""),
            args_template=_json.loads(row.get("config", "{}")) if row.get("config") else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tool_id": self.tool_id,
            "args_template": self.args_template,
        }


BUILTIN_SKILLS: list[dict[str, Any]] = [
    {
        "name": "port-scan",
        "description": "Quick port scan with nmap on a target host",
        "category": "information-gathering",
        "tool_id": "nmap",
        "args_template": {"target": "{{target}}"},
    },
    {
        "name": "web-scan",
        "description": "Scan a web application with nikto",
        "category": "vulnerability-analysis",
        "tool_id": "nikto",
        "args_template": {"url": "{{url}}"},
    },
    {
        "name": "hash-crack",
        "description": "Crack password hashes with John the Ripper",
        "category": "password-attacks",
        "tool_id": "john",
        "args_template": {"hashes": "{{hashes}}"},
    },
    {
        "name": "forensics",
        "description": "File carving with foremost",
        "category": "forensics",
        "tool_id": "foremost",
        "args_template": {"file": "{{file}}"},
    },
    {
        "name": "report-gen",
        "description": "Generate an HTML report of findings",
        "category": "reporting",
        "tool_id": "report",
        "args_template": {},
    },
    {
        "name": "dns-recon",
        "description": "DNS enumeration with dnsrecon",
        "category": "information-gathering",
        "tool_id": "dnsrecon",
        "args_template": {"target": "{{target}}"},
    },
    {
        "name": "osint-gather",
        "description": "OSINT collection with theHarvester",
        "category": "information-gathering",
        "tool_id": "theharvester",
        "args_template": {"target": "{{target}}"},
    },
]


def _render_template(template: str, params: dict[str, Any]) -> str:
    """Simple Jinja2-like template rendering using str.replace."""
    result = template
    for key, value in params.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


def _render_args(args_template: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Render an args_template with params."""
    rendered = {}
    for key, value in args_template.items():
        if isinstance(value, str):
            rendered[key] = _render_template(value, params)
        elif isinstance(value, dict):
            rendered[key] = _render_args(value, params)
        elif isinstance(value, list):
            rendered[key] = [_render_template(str(v), params) if isinstance(v, str) else v
                             for v in value]
        else:
            rendered[key] = value
    return rendered


def load_skills() -> list[Skill]:
    """Load all skills: builtins plus DB-stored custom skills."""
    skills = [Skill(**{k: v for k, v in s.items() if k in ("name", "description",
                "category", "tool_id", "args_template")}) for s in BUILTIN_SKILLS]

    # Load custom skills from DB
    import server.db as db
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM skills WHERE enabled = 1"
            ).fetchall()
            for row in rows:
                row_dict = dict(row)
                if row_dict.get("name", "") in [s.name for s in skills]:
                    continue  # Skip if builtin with same name
                skills.append(Skill.from_row(row_dict))
    except Exception:  # noqa: BLE001
        pass

    return skills


def get_skill(name: str) -> Skill | None:
    """Get a skill by name."""
    for skill in load_skills():
        if skill.name == name:
            return skill
    return None


def save_skill(skill: Skill) -> bool:
    """Save or update a custom skill in the database."""
    import json as _json

    import server.db as db
    with db.connect() as conn:
        try:
            conn.execute(
                "INSERT INTO skills (name, description, category, config, enabled) "
                "VALUES (?, ?, ?, ?, 1) "
                "ON CONFLICT(name) DO UPDATE SET "
                "description=excluded.description, "
                "category=excluded.category, "
                "config=excluded.config, "
                "enabled=1",
                (skill.name, skill.description, skill.category,
                 _json.dumps(skill.args_template)),
            )
            return True
        except Exception:  # noqa: BLE001
            return False


def delete_skill(name: str) -> bool:
    """Delete a custom skill by name."""
    import server.db as db
    with db.connect() as conn:
        try:
            cur = conn.execute("DELETE FROM skills WHERE name = ?", (name,))
            return cur.rowcount > 0
        except Exception:  # noqa: BLE001
            return False


def execute_skill(name: str, params: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Execute a skill by rendering its args_template with params and running the tool."""
    skill = get_skill(name)
    if skill is None:
        return {"error": f"skill '{name}' not found"}, 404

    rendered_args = _render_args(skill.args_template, params)
    cfg = config.load()
    return tools_api.run(cfg, skill.tool_id, rendered_args)


def suggest_skills(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Suggest next skills based on context."""
    suggestions = []
    tool = context.get("tool", "")
    target = context.get("target", "")

    if tool and target:
        for skill in load_skills():
            if skill.tool_id == tool and skill.name not in ("port-scan", "web-scan",
                                                              "hash-crack", "forensics"):
                suggestions.append(skill.to_dict())

    if not suggestions and target:
        for skill in load_skills():
            if target in (skill.description or "") or skill.category == context.get("category", ""):
                suggestions.append(skill.to_dict())

    return suggestions[:5]
