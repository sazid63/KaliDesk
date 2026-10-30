"""Optional AI bridge.

Two providers, both entirely optional:

* ``ollama``  - a local model at http://127.0.0.1:11434
* ``openai``  - any OpenAI-compatible endpoint (the API key is stored with
                Windows DPAPI, never in the repository or the database)

The chat can also *propose* a tool run. It never executes one: it returns an
``action`` object that the UI must show and the user must confirm. The normal
scope guard and allowlist still apply to the confirmed run.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import kws.secrets as kws_secrets
import server.db as db

OLLAMA_DEFAULT = "http://127.0.0.1:11434"
SECRET_KEY = "ai_api_key"

SYSTEM_PROMPT = (
    "You are the assistant inside 'Kali Linux Windows Substitute', a learning "
    "and authorised-testing toolkit. Be concise and practical. Explain commands "
    "in plain English and always remind the user to test only systems they own "
    "or are authorised to test.\n\n"
    "If - and only if - the user clearly asks you to run a tool, reply with a "
    "single JSON object and nothing else, of the form "
    '{"action":"run","tool":"<tool id>","payload":{...}} '
    "where payload matches that tool's form fields. Otherwise reply in prose."
)


def get_config() -> dict[str, str]:
    return {
        "provider": db.get_setting("ai_provider", "none") or "none",
        "base_url": db.get_setting("ai_base_url", "") or "",
        "model": db.get_setting("ai_model", "") or "",
        "key_set": "yes" if kws_secrets.has_secret(SECRET_KEY) else "no",
    }


def set_config(provider: str, base_url: str, model: str) -> None:
    db.set_setting("ai_provider", provider or "none")
    db.set_setting("ai_base_url", base_url or "")
    db.set_setting("ai_model", model or "")


def _post(url: str, body: dict[str, Any], headers: dict[str, str],
          timeout: int = 120) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"role": "system", "content": SYSTEM_PROMPT}, *messages]


def complete(messages: list[dict[str, str]]) -> str:
    cfg = get_config()
    provider = cfg["provider"]
    if provider == "none":
        raise RuntimeError("no AI provider is configured")

    if provider == "ollama":
        base = cfg["base_url"] or OLLAMA_DEFAULT
        model = cfg["model"] or "llama3"
        out = _post(
            f"{base.rstrip('/')}/api/chat",
            {"model": model, "messages": _messages(messages), "stream": False},
            {},
        )
        return str(out.get("message", {}).get("content", "")).strip()

    if provider == "openai":
        base = cfg["base_url"] or "https://api.openai.com/v1"
        model = cfg["model"] or "gpt-4o-mini"
        key = kws_secrets.get_secret(SECRET_KEY)
        if not key:
            raise RuntimeError("no API key is stored for the cloud provider")
        out = _post(
            f"{base.rstrip('/')}/chat/completions",
            {"model": model, "messages": _messages(messages)},
            {"Authorization": f"Bearer {key}"},
        )
        choices = out.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "")).strip()

    raise RuntimeError(f"unknown AI provider: {provider}")


def _maybe_action(text: str) -> dict[str, Any]:
    """Turn a JSON action reply into a structured proposal."""
    candidate = text.strip()
    if not candidate.startswith("{") or '"action"' not in candidate:
        return {"type": "message", "text": text}
    if not candidate.endswith("}"):
        return {"type": "message", "text": text}
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return {"type": "message", "text": text}
    if obj.get("action") == "run" and obj.get("tool"):
        return {"type": "action", "tool": obj["tool"],
                "payload": obj.get("payload") or {}, "text": text}
    return {"type": "message", "text": text}


def respond(messages: list[dict[str, str]]) -> dict[str, Any]:
    try:
        text = complete(messages)
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
        return {"type": "error", "text": f"The AI request failed: {exc}"}
    return _maybe_action(text)


def explain(tool_name: str, output: str) -> dict[str, Any]:
    prompt = (
        f"Explain the following output from the {tool_name} tool to a beginner. "
        "Say what it means, what to do next, and any safety note. Keep it short.\n\n"
        f"```\n{output[:8000]}\n```"
    )
    return respond([{"role": "user", "content": prompt}])
