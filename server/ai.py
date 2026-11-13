"""Optional AI assistant.

Everything here is optional; the tools work without it. One small provider layer:

* ``ollama``    - a local model at http://127.0.0.1:11434 (no key)
* ``openai``    - any OpenAI-compatible endpoint (OpenAI, DeepSeek, LM Studio, LocalAI, ...)
* ``anthropic`` - the Anthropic Messages API
* ``gemini``    - the Google Gemini API

API keys are stored with Windows DPAPI (``kws.secrets``), one per provider, never in the
database, the repository or the logs. A key is only ever sent to the base URL that was
saved with it (or the provider's own default), and only over https unless the server is
on this machine, so a crafted request cannot make the app send your key elsewhere.

The assistant can *propose* a tool run. It never executes one: the reply carries an
``action`` object, the UI shows it, and only the user's own click runs it (through the
normal scope guard and allow-list).
"""

from __future__ import annotations

import ipaddress
import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

import kws.secrets as kws_secrets
import server.db as db

PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "label": "Ollama (local)", "url": "http://127.0.0.1:11434",
        "model": "llama3.1", "needs_key": False,
    },
    "openai": {
        "label": "OpenAI-compatible", "url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini", "needs_key": True,
    },
    "anthropic": {
        "label": "Anthropic", "url": "https://api.anthropic.com",
        "model": "claude-sonnet-4-5", "needs_key": True,
    },
    "gemini": {
        "label": "Google Gemini", "url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-2.0-flash", "needs_key": True,
    },
}
SECRET_KEY = "ai_api_key"  # the OpenAI-compatible key (kept for existing installs)
MAX_MESSAGES = 40
MAX_CONTENT = 8000

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


class AIError(RuntimeError):
    """A problem the user can act on (shown as the assistant's reply)."""


# --- settings and keys ------------------------------------------------------


def _secret_name(provider: str) -> str:
    return SECRET_KEY if provider == "openai" else f"ai_key_{provider}"


def get_config() -> dict[str, str]:
    provider = db.get_setting("ai_provider", "none") or "none"
    return {
        "provider": provider,
        "base_url": db.get_setting("ai_base_url", "") or "",
        "model": db.get_setting("ai_model", "") or "",
        "key_set": "yes" if provider in PROVIDERS and kws_secrets.has_secret(
            _secret_name(provider)) else "no",
    }


def set_config(provider: str, base_url: str, model: str) -> None:
    provider = (provider or "none").strip().lower()
    if provider != "none" and provider not in PROVIDERS:
        raise ValueError(f"unknown provider '{provider}'")
    base_url = (base_url or "").strip()
    if base_url:
        _check_url(base_url)
    db.set_setting("ai_provider", provider)
    db.set_setting("ai_base_url", base_url)
    db.set_setting("ai_model", (model or "").strip())


def set_key(provider: str, key: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider '{provider}'")
    key = (key or "").strip()
    if key:
        kws_secrets.set_secret(_secret_name(provider), key)
    else:
        kws_secrets.delete_secret(_secret_name(provider))


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _origin(url: str) -> tuple[str, str]:
    """(scheme, host[:port]) of a URL, lower-cased; used to bind a key to its host."""
    try:
        parts = urlsplit(url.strip())
        return parts.scheme.lower(), parts.netloc.lower()
    except ValueError:
        return "", ""


def _check_url(url: str, needs_key: bool = False) -> str:
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises ValueError on a malformed port or IPv6 literal
    except ValueError as exc:
        raise AIError("the base URL is not a valid address") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AIError("the base URL must start with http:// or https://")
    if parts.username or parts.password:
        raise AIError("the base URL must not contain a user name or password")
    if needs_key and parts.scheme != "https" and not _is_loopback(parts.hostname):
        raise AIError("API keys are only sent over https (or to a server on this computer)")
    return url.rstrip("/")


def resolve(
    provider: str, base_url: str = "", model: str = "", explicit_key: str = ""
) -> dict[str, Any]:
    """Settings for one provider with defaults filled in, and the key it may use.

    ``explicit_key`` is a key the user just typed in the form; it is used for this call only.
    """
    info = PROVIDERS.get(provider)
    if info is None:
        raise AIError("no AI provider is configured")
    url = (base_url or info["url"]).strip()
    key = ""
    if info["needs_key"]:
        saved = db.get_setting("ai_base_url", "") if db.get_setting(
            "ai_provider", "none") == provider else ""
        # The stored key belongs to the host it was saved with (or the provider's default
        # host). It is never sent to any other scheme, host or port.
        bound = saved or info["url"]
        if explicit_key.strip():
            key = explicit_key.strip()
        elif _origin(url) == _origin(bound):
            key = kws_secrets.get_secret(_secret_name(provider)) or ""
        if not key:
            raise AIError(
                f"no API key available for {info['label']} at {url}. Save the settings with "
                "a key first (a saved key is never sent to a different URL)."
            )
    return {
        "provider": provider,
        "url": _check_url(url, info["needs_key"]),
        "model": (model or info["model"]).strip(),
        "key": key,
    }


# --- HTTP -------------------------------------------------------------------


def _http(
    method: str, url: str, body: dict | None, headers: dict[str, str], timeout: int = 120
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for name, value in headers.items():
        req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise AIError(f"the AI service answered HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIError(f"could not reach the AI service: {getattr(exc, 'reason', exc)}") from exc
    except ValueError as exc:
        raise AIError("the AI service sent a reply that is not JSON") from exc


def _clean(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for item in messages[-MAX_MESSAGES:]:
        role = str(item.get("role", "user"))
        if role not in ("user", "assistant", "system"):
            role = "user"
        out.append({"role": role, "content": str(item.get("content", ""))[:MAX_CONTENT]})
    return out


def _chat(cfg: dict[str, Any], messages: list[dict[str, str]]) -> str:
    try:
        return _chat_reply(cfg, messages)
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise AIError("the AI service sent a reply in an unexpected format") from exc


def _chat_reply(cfg: dict[str, Any], messages: list[dict[str, str]]) -> str:
    provider, url, model, key = cfg["provider"], cfg["url"], cfg["model"], cfg["key"]
    messages = _clean(messages)
    system = SYSTEM_PROMPT
    turns = [m for m in messages if m["role"] != "system"]

    if provider == "ollama":
        out = _http("POST", f"{url}/api/chat", {
            "model": model, "stream": False,
            "messages": [{"role": "system", "content": system}, *turns],
        }, {})
        return str(out.get("message", {}).get("content", "")).strip()

    if provider == "openai":
        out = _http("POST", f"{url}/chat/completions", {
            "model": model, "messages": [{"role": "system", "content": system}, *turns],
        }, {"Authorization": f"Bearer {key}"})
        choices = out.get("choices") or []
        return str(choices[0].get("message", {}).get("content", "")).strip() if choices else ""

    if provider == "anthropic":
        out = _http("POST", f"{url}/v1/messages", {
            "model": model, "max_tokens": 2048, "system": system,
            "messages": [m for m in turns if m["role"] in ("user", "assistant")],
        }, {"x-api-key": key, "anthropic-version": "2023-06-01"})
        parts = out.get("content") or []
        return "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()

    if provider == "gemini":
        # The model name goes into the URL path, so only plain name characters are allowed.
        if not re.fullmatch(r"[A-Za-z0-9._-]+", model or ""):
            raise AIError("the Gemini model name may only use letters, digits, . _ and -")
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user",
             "parts": [{"text": m["content"]}]}
            for m in turns
        ]
        out = _http("POST", f"{url}/models/{model}:generateContent", {
            "systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
        }, {"x-goog-api-key": key})
        candidates = out.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts") or []
        return "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()

    raise AIError(f"unknown AI provider: {provider}")


def _models(cfg: dict[str, Any]) -> list[str]:
    try:
        return _model_names(cfg)
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise AIError("the AI service sent a reply in an unexpected format") from exc


def _model_names(cfg: dict[str, Any]) -> list[str]:
    provider, url, key = cfg["provider"], cfg["url"], cfg["key"]
    if provider == "ollama":
        out = _http("GET", f"{url}/api/tags", None, {}, timeout=10)
        return [m["name"] for m in out.get("models", []) if m.get("name")]
    if provider == "openai":
        out = _http("GET", f"{url}/models", None, {"Authorization": f"Bearer {key}"}, 15)
        return sorted(m["id"] for m in out.get("data", []) if m.get("id"))
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        out = _http("GET", f"{url}/v1/models", None, headers, 15)
        return [m["id"] for m in out.get("data", []) if m.get("id")]
    if provider == "gemini":
        out = _http("GET", f"{url}/models", None, {"x-goog-api-key": key}, 15)
        return [m["name"].removeprefix("models/") for m in out.get("models", []) if m.get("name")]
    return []


# --- public API ---------------------------------------------------------------


def complete(messages: list[dict[str, str]]) -> str:
    cfg = get_config()
    if cfg["provider"] == "none":
        raise AIError("no AI provider is configured (Settings > AI provider)")
    return _chat(resolve(cfg["provider"], cfg["base_url"], cfg["model"]), messages)


def test(
    provider: str, base_url: str = "", model: str = "", api_key: str = ""
) -> dict[str, Any]:
    """Check a provider with the given (unsaved) form values. Never raises."""
    try:
        models = _models(resolve(provider, base_url, model, api_key))
    except AIError as exc:
        return {"ok": False, "message": str(exc), "models": []}
    note = f"{len(models)} models available" if models else "connected"
    return {"ok": True, "message": f"Connection works ({note})", "models": models[:200]}


def _maybe_action(text: str) -> dict[str, Any]:
    """Turn a JSON action reply into a structured proposal."""
    candidate = text.strip()
    if not candidate.startswith("{") or '"action"' not in candidate or not candidate.endswith("}"):
        return {"type": "message", "text": text}
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return {"type": "message", "text": text}
    if obj.get("action") == "run" and obj.get("tool"):
        payload = obj.get("payload")
        payload = dict(payload) if isinstance(payload, dict) else {}
        # The model may not grant the external-target confirmation. Only the user's own tick
        # in the tool form (sent with their click) can set it, so strip it from the proposal.
        payload.pop("confirm_external", None)
        return {
            "type": "action",
            "tool": str(obj["tool"]),
            "payload": payload,
            "text": text,
        }
    return {"type": "message", "text": text}


def models() -> dict[str, Any]:
    cfg = get_config()
    if cfg["provider"] == "none":
        return {"models": []}
    return test(cfg["provider"], cfg["base_url"], cfg["model"])


def respond(messages: list[dict[str, str]]) -> dict[str, Any]:
    try:
        text = complete(messages)
    except AIError as exc:
        return {"type": "error", "text": f"The AI request failed: {exc}"}
    return _maybe_action(text)


def explain(tool_name: str, output: str) -> dict[str, Any]:
    prompt = (
        f"Explain the following output from the {tool_name} tool to a beginner. "
        "Say what it means, what to do next, and any safety note. Keep it short.\n\n"
        f"```\n{output[:8000]}\n```"
    )
    return respond([{"role": "user", "content": prompt}])
