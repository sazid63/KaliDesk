"""AI Provider Abstraction Layer.

This module provides a unified interface for multiple AI providers:
- Cloud providers: OpenAI, Anthropic, Gemini, DeepSeek
- Local providers: Ollama, LocalAI (llama.cpp), OpenCode
- Bridge providers: MCP (for tool access)

All API keys are encrypted via Windows DPAPI (kws_secrets).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

import kws.secrets as kws_secrets
import server.db as db

# Secret name prefixes for each provider
SECRET_PREFIXES = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "gemini_api_key",
    "deepseek": "deepseek_api_key",
    "deepseek_harness": "deepseek_harness_token",
}


class AIProvider(ABC):
    """Abstract base class for all AI providers."""

    @abstractmethod
    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return a completion for the given messages."""
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return list of available models."""
        pass

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Test if the provider is reachable and configured correctly."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for display."""
        pass


class _BaseHTTPProvider(AIProvider):
    """Base class for HTTP-based providers with common _post logic."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def _post(self, path: str, body: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def list_models(self) -> list[str]:
        """Default: return the configured model."""
        return [self.model] if self.model else []


class OpenAIProvider(_BaseHTTPProvider):
    """OpenAI or OpenAI-compatible provider."""

    def __init__(self,
                   base_url: str = "https://api.openai.com/v1",
                   model: str = "gpt-4o-mini",
                   api_key: str | None = None):
        super().__init__(base_url, model, api_key)

    @property
    def name(self) -> str:
        return "OpenAI"

    def complete(self, messages: list[dict[str, str]]) -> str:
        out = self._post("/chat/completions", {"model": self.model, "messages": messages})
        choices = out.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "")).strip()

    def test_connection(self) -> tuple[bool, str]:
        try:
            self._post("/chat/completions",
                         {"model": self.model,
                          "messages": [{"role": "user", "content": "test"}]},
                         timeout=15)
            return True, "Connection successful"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)


class AnthropicProvider(_BaseHTTPProvider):
    """Anthropic Claude provider."""

    def __init__(self,
                   base_url: str = "https://api.anthropic.com",
                   model: str = "claude-sonnet-4-20250514",
                   api_key: str | None = None):
        super().__init__(base_url, model, api_key)

    @property
    def name(self) -> str:
        return "Anthropic"

    def complete(self, messages: list[dict[str, str]]) -> str:
        # Anthropic uses a different format
        data = json.dumps({
            "model": self.model,
            "max_tokens": 4096,
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in messages if m["role"] != "system"
            ],
        }).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/v1/messages", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("x-api-key", self.api_key or "")
        req.add_header("anthropic-version", "2023-06-01")
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            out = json.loads(resp.read().decode("utf-8", errors="replace"))
        return str(out.get("content", [{}])[0].get("text", "")).strip()

    def test_connection(self) -> tuple[bool, str]:
        try:
            self.complete([{"role": "user", "content": "test"}])
            return True, "Connection successful"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)


class GeminiProvider(_BaseHTTPProvider):
    """Google Gemini provider."""

    def __init__(self,
                   base_url: str = "https://generativelanguage.googleapis.com/v1beta",
                   model: str = "gemini-2.5-pro",
                   api_key: str | None = None):
        super().__init__(base_url, model, api_key)

    @property
    def name(self) -> str:
        return "Gemini"

    def complete(self, messages: list[dict[str, str]]) -> str:
        # Gemini REST API
        url = f"{self.base_url}/models/{self.model}:generateContent"
        contents = [
            {"role": m["role"], "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        data = json.dumps({"contents": contents}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            out = json.loads(resp.read().decode("utf-8", errors="replace"))
        candidates = out.get("candidates") or []
        if not candidates:
            return ""
        return str(candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")).strip()

    def test_connection(self) -> tuple[bool, str]:
        try:
            self.complete([{"role": "user", "content": "test"}])
            return True, "Connection successful"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)


class OllamaProvider(_BaseHTTPProvider):
    """Ollama local provider (no API key)."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "llama3.1"):
        super().__init__(base_url, model, api_key=None)

    @property
    def name(self) -> str:
        return "Ollama"

    def complete(self, messages: list[dict[str, str]]) -> str:
        out = self._post("/api/chat", {"model": self.model, "messages": messages, "stream": False})
        return str(out.get("message", {}).get("content", "")).strip()

    def list_models(self) -> list[str]:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:  # noqa: BLE001
            return [self.model] if self.model else []

    def test_connection(self) -> tuple[bool, str]:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                json.loads(resp.read().decode("utf-8", errors="replace"))
            return True, f"Ollama online ({len(self.list_models())} models)"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)


class LocalAIProvider(_BaseHTTPProvider):
    """LocalAI (llama.cpp) provider via subprocess."""

    def __init__(self, model_path: str, quantization: str = "Q4_K_M"):
        self.model_path = model_path
        self.quantization = quantization
        super().__init__("", "", api_key=None)

    @property
    def name(self) -> str:
        return "LocalAI (llama.cpp)"

    def complete(self, messages: list[dict[str, str]]) -> str:
        # Placeholder: would call llama-cpp-python or llama.cpp binary
        # For now, return a stub message
        return f"[LocalAI] Would run {self.model_path} with {len(messages)} messages"

    def list_models(self) -> list[str]:
        return [self.model_path.split("/")[-1] or "local-model"]

    def test_connection(self) -> tuple[bool, str]:
        import os
        if os.path.exists(self.model_path):
            return True, f"Model file exists: {self.model_path}"
        return False, f"Model file not found: {self.model_path}"


class DeepSeekProvider(_BaseHTTPProvider):
    """DeepSeek provider (self-hosted or cloud)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 11434, model: str = "deepseek-coder"):
        base_url = f"http://{host}:{port}"
        super().__init__(base_url, model, api_key=None)

    @property
    def name(self) -> str:
        return "DeepSeek"

    def complete(self, messages: list[dict[str, str]]) -> str:
        out = self._post("/v1/chat/completions", {"model": self.model, "messages": messages})
        choices = out.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "")).strip()

    def test_connection(self) -> tuple[bool, str]:
        try:
            self.complete([{"role": "user", "content": "test"}])
            return True, "DeepSeek online"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)


class DeepSeekHarnessProvider(AIProvider):
    """DeepSeek Harness provider — wraps the DSH desktop app as an API gateway.

    DSH is an Electron app that connects to FreeLLMAPI (an OpenAI-compatible
    API server running on 127.0.0.1:31415 by default). This provider connects
    directly to FreeLLMAPI's /v1 endpoints to discover the models configured
    in DSH and proxy chat completions through them.

    The user configures their providers/models inside the DSH desktop app,
    and those models are auto-discovered and surfaced to KaliDesk's AI
    CyberSecurity tab.
    """

    def __init__(self,
                 freellmapi_host: str = "127.0.0.1",
                 freellmapi_port: int = 31415,
                 model: str = "auto",
                 api_key: str | None = None):
        self.freellmapi_host = freellmapi_host
        self.freellmapi_port = int(freellmapi_port)
        self.model = model
        self.base_url = f"http://{freellmapi_host}:{self.freellmapi_port}"
        # API key for FreeLLMAPI unified API (stored encrypted via DPAPI)
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "DeepSeek Harness"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, path: str, body: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, method="POST")
        for k, v in self._headers().items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def _get(self, path: str, timeout: int = 5) -> dict[str, Any]:
        req = urllib.request.Request(f"{self.base_url}{path}")
        for k, v in self._headers().items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def list_models(self) -> list[str]:
        """Discover models from FreeLLMAPI (which DSH uses as its backend)."""
        try:
            data = self._get("/v1/models")
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                if model_id:
                    models.append(model_id)
            return models if models else [self.model]
        except Exception:
            return [self.model] if self.model else []

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Proxy completion through FreeLLMAPI (DSH's backend)."""
        body = {
            "model": self.model if self.model != "auto" else "deepseek-chat",
            "messages": messages,
            "stream": False,
        }
        out = self._post("/v1/chat/completions", body)
        choices = out.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "")).strip()

    def test_connection(self) -> tuple[bool, str]:
        try:
            info = self._get("/v1/models")
            model_count = len(info.get("data", []))
            return True, f"FreeLLMAPI online ({model_count} models available)"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return True, "FreeLLMAPI online (API key required — configure in DSH or KaliDesk)"
            if e.code == 404:
                return True, "FreeLLMAPI reachable (v1 endpoint may differ)"
            return False, f"FreeLLMAPI returned {e.code}: {e.reason}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)


class MCPBridgeProvider(AIProvider):
    """MCP bridge for tool access (stdio or HTTP)."""

    def __init__(self, mcp_type: str = "stdio", config: dict[str, Any] | None = None):
        self.mcp_type = mcp_type
        self.config = config or {}

    @property
    def name(self) -> str:
        return "MCP Bridge"

    def complete(self, messages: list[dict[str, str]]) -> str:
        # MCP providers don't do completions; they expose tools
        return "[MCP] Tool bridge active"

    def list_models(self) -> list[str]:
        return []

    def test_connection(self) -> tuple[bool, str]:
        # Placeholder: would test MCP stdio/HTTP connection
        return True, f"MCP {self.mcp_type} configured"


def get_provider(provider_type: str, config: dict[str, Any]) -> AIProvider:
    """Factory function to create a provider from type and config."""
    provider_type = provider_type.lower()

    if provider_type == "openai":
        api_key = config.get("api_key") or kws_secrets.get_secret(SECRET_PREFIXES["openai"])
        return OpenAIProvider(
            base_url=config.get("base_url", "https://api.openai.com/v1"),
            model=config.get("model", "gpt-4o-mini"),
            api_key=api_key,
        )

    if provider_type == "anthropic":
        api_key = config.get("api_key") or kws_secrets.get_secret(SECRET_PREFIXES["anthropic"])
        return AnthropicProvider(
            base_url=config.get("base_url", "https://api.anthropic.com"),
            model=config.get("model", "claude-sonnet-4-20250514"),
            api_key=api_key,
        )

    if provider_type == "gemini":
        api_key = config.get("api_key") or kws_secrets.get_secret(SECRET_PREFIXES["gemini"])
        return GeminiProvider(
            base_url=config.get("base_url", "https://generativelanguage.googleapis.com/v1beta"),
            model=config.get("model", "gemini-2.5-pro"),
            api_key=api_key,
        )

    if provider_type == "ollama":
        return OllamaProvider(
            base_url=config.get("base_url", "http://127.0.0.1:11434"),
            model=config.get("model", "llama3.1"),
        )

    if provider_type == "localai":
        return LocalAIProvider(
            model_path=config.get("model_path", ""),
            quantization=config.get("quantization", "Q4_K_M"),
        )

    if provider_type == "deepseek":
        return DeepSeekProvider(
            host=config.get("host", "127.0.0.1"),
            port=int(config.get("port", 11434)),
            model=config.get("model", "deepseek-coder"),
        )

    if provider_type == "deepseek_harness":
        return DeepSeekHarnessProvider(
            freellmapi_host=config.get("freellmapi_host", "127.0.0.1"),
            freellmapi_port=int(config.get("freellmapi_port", 31415)),
            model=config.get("model", "auto"),
            api_key=config.get("api_key")
            or kws_secrets.get_secret(SECRET_PREFIXES["deepseek_harness"]),
        )

    if provider_type == "mcp":
        return MCPBridgeProvider(
            mcp_type=config.get("mcp_type", "stdio"),
            config=config,
        )

    raise ValueError(f"Unknown provider type: {provider_type}")


def list_configured_providers() -> list[dict[str, Any]]:
    """List all configured providers from the database."""
    providers = []
    for ptype in [
        "openai", "anthropic", "gemini", "ollama",
        "localai", "deepseek", "deepseek_harness", "mcp"
    ]:
        base_key = f"ai_{ptype}"
        provider_cfg = db.get_setting(f"{base_key}_config", "")
        if provider_cfg:
            try:
                cfg = json.loads(provider_cfg)
                has_key = bool(kws_secrets.get_secret(SECRET_PREFIXES.get(ptype, "")))
                providers.append({
                    "type": ptype,
                    "name": get_provider(ptype, cfg).name,
                    "configured": True,
                    "has_api_key": has_key if ptype in SECRET_PREFIXES else None,
                    "model": cfg.get("model", ""),
                    "base_url": cfg.get("base_url", ""),
                })
            except json.JSONDecodeError:
                pass
    return providers


def save_provider_config(provider_type: str, config: dict[str, Any]) -> None:
    """Save provider config to DB and encrypt API key."""
    base_key = f"ai_{provider_type}"
    # Store API key in secrets if present
    if "api_key" in config and config["api_key"]:
        secret_name = SECRET_PREFIXES.get(provider_type)
        if secret_name:
            kws_secrets.set_secret(secret_name, config["api_key"])
            config["api_key"] = "***encrypted***"  # Don't store in DB
    # Store rest in DB
    db.set_setting(f"{base_key}_config", json.dumps(config))


def delete_provider_config(provider_type: str) -> None:
    """Delete provider config and API key."""
    base_key = f"ai_{provider_type}"
    db.set_setting(f"{base_key}_config", "")
    secret_name = SECRET_PREFIXES.get(provider_type)
    if secret_name:
        kws_secrets.delete_secret(secret_name)
