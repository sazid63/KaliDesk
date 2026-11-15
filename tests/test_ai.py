"""The optional AI assistant: provider request shapes, key safety, confirmation rule."""
from __future__ import annotations

import http.server
import json
import threading

import pytest

import server.ai as ai
import server.db as db


class Fake(http.server.BaseHTTPRequestHandler):
    seen: list[dict] = []

    def log_message(self, *a):
        pass

    def _reply(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        Fake.seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
        p = self.path
        if p.endswith("/chat/completions"):
            out = {"choices": [{"message": {"content": "openai says hi"}}]}
        elif p.endswith("/api/chat"):
            out = {"message": {"content": "ollama says hi"}}
        elif p.endswith("/v1/messages"):
            out = {"content": [{"type": "text", "text": "claude says hi"}]}
        elif ":generateContent" in p:
            out = {"candidates": [{"content": {"parts": [{"text": "gemini says hi"}]}}]}
        elif p.endswith("/api/tags"):
            out = {"models": [{"name": "llama3.1"}, {"name": "qwen"}]}
        elif p.endswith("/models"):
            out = {"data": [{"id": "m-b"}, {"id": "m-a"}], "models": [{"name": "models/g-1"}]}
        elif p.endswith("/v1/models"):
            out = {"data": [{"id": "claude-x"}]}
        else:
            out = {}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = _reply  # noqa: N815


@pytest.fixture()
def fake():
    Fake.seen = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(autouse=True)
def clean_settings():
    db.init_db()
    for provider in ai.PROVIDERS:
        ai.set_key(provider, "")
    db.set_setting("ai_provider", "none")
    db.set_setting("ai_base_url", "")
    db.set_setting("ai_model", "")


def configure(provider, url, model="m", key=""):
    ai.set_config(provider, url, model)
    if key:
        ai.set_key(provider, key)


def test_nothing_configured_is_a_clear_message_not_a_crash():
    reply = ai.respond([{"role": "user", "content": "hi"}])
    assert reply["type"] == "error" and "no AI provider" in reply["text"]


def test_ollama_round_trip_and_models(fake):
    configure("ollama", fake, "llama3.1")
    reply = ai.respond([{"role": "user", "content": "hi"}])
    assert reply == {"type": "message", "text": "ollama says hi"}
    body = Fake.seen[-1]["body"]
    assert body["stream"] is False and body["messages"][0]["role"] == "system"
    assert ai.models()["models"] == ["llama3.1", "qwen"]


def test_openai_uses_bearer_key_and_system_prompt(fake):
    configure("openai", fake, "gpt", key="sk-test")
    assert ai.respond([{"role": "user", "content": "hi"}])["text"] == "openai says hi"
    seen = Fake.seen[-1]
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["body"]["messages"][0]["content"].startswith("You are the assistant")
    assert ai.models()["models"] == ["m-a", "m-b"]


def test_anthropic_sends_the_system_prompt_in_the_system_field(fake):
    configure("anthropic", fake, "claude", key="ak-test")
    assert ai.respond([{"role": "user", "content": "hi"}])["text"] == "claude says hi"
    seen = Fake.seen[-1]
    assert seen["headers"]["X-Api-Key"] == "ak-test"
    assert seen["headers"]["Anthropic-Version"]
    assert "assistant inside" in seen["body"]["system"]
    assert all(m["role"] in ("user", "assistant") for m in seen["body"]["messages"])


def test_gemini_uses_the_api_key_header_not_bearer(fake):
    configure("gemini", fake, "gem", key="gk-test")
    reply = ai.respond([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}])
    assert reply["text"] == "gemini says hi"
    seen = Fake.seen[-1]
    assert seen["headers"]["X-Goog-Api-Key"] == "gk-test"
    assert "Authorization" not in seen["headers"]
    assert [c["role"] for c in seen["body"]["contents"]] == ["user", "model"]
    assert seen["body"]["systemInstruction"]["parts"][0]["text"]
    assert ai.models()["models"] == ["g-1"]


def test_stored_key_is_never_sent_to_a_different_url(fake):
    configure("openai", fake, "gpt", key="sk-secret")
    # An attacker-controlled test request pointing at another server gets no key.
    result = ai.test("openai", "http://127.0.0.1:9/v1")
    assert result["ok"] is False  # nothing is listening there; the point is what was sent
    assert not any("sk-secret" in json.dumps(s["headers"]) for s in Fake.seen)
    # ...unless the user typed a key into the form for that test.
    assert ai.test("openai", fake, "gpt", api_key="typed-key")["ok"] is True
    assert Fake.seen[-1]["headers"]["Authorization"] == "Bearer typed-key"


def test_saved_key_is_bound_to_the_saved_host_not_the_default_one(fake):
    configure("openai", fake, "gpt", key="sk-bound")
    # The provider's default host is a different host from the saved one: no key for it.
    with pytest.raises(ai.AIError):
        ai.resolve("openai", "https://api.openai.com/v1")


def test_unexpected_provider_json_becomes_an_ai_error(fake, monkeypatch):
    configure("openai", fake, "gpt", key="k")
    monkeypatch.setattr(ai, "_http", lambda *a, **k: ["not", "an", "object"])
    reply = ai.respond([{"role": "user", "content": "hi"}])
    assert reply["type"] == "error" and "unexpected format" in reply["text"]


def test_keys_need_https_unless_the_server_is_local():
    with pytest.raises(ai.AIError):
        ai.resolve("openai", "http://example.com/v1", explicit_key="k")
    assert ai.resolve("openai", "http://127.0.0.1:1234/v1", explicit_key="k")["key"] == "k"
    assert ai.resolve("openai", "https://api.example.com/v1", explicit_key="k")["url"].startswith(
        "https://"
    )


@pytest.mark.parametrize("url", ["ftp://x", "javascript:alert(1)", "http://u:p@host/", "//nohost", "x"])
def test_bad_base_urls_are_rejected(url):
    with pytest.raises(ai.AIError):
        ai.set_config("ollama", url, "m")


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        ai.set_config("evil", "", "")
    with pytest.raises(ValueError):
        ai.set_key("evil", "k")


def test_keys_are_per_provider_and_reported():
    ai.set_key("anthropic", "a")
    ai.set_config("anthropic", "", "")
    assert ai.get_config()["key_set"] == "yes"
    ai.set_config("gemini", "", "")
    assert ai.get_config()["key_set"] == "no"


def test_json_action_reply_becomes_a_proposal_never_a_run(fake, monkeypatch):
    import server.tools as tools

    ran = []
    monkeypatch.setattr(tools, "run", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(tools, "start_job", lambda *a, **k: ran.append(a))
    text = '{"action":"run","tool":"nmap","payload":{"target":"8.8.8.8","confirm_external":true}}'
    assert ai._maybe_action(text)["type"] == "action"
    assert ai._maybe_action("just words")["type"] == "message"
    assert ai._maybe_action('{"action":"run"}')["type"] == "message"
    assert ran == []


def test_chat_route_validates_input(client):
    resp = client.post("/api/ai/chat", json={"messages": "nope"}, headers={"X-KWS-CSRF": "test-csrf"})
    assert resp.status_code == 400
    resp = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "x"}]},
                       headers={"X-KWS-CSRF": "test-csrf"})
    assert resp.get_json()["type"] == "error"  # nothing configured
    assert client.post("/api/ai/config", json={"provider": "evil"},
                       headers={"X-KWS-CSRF": "test-csrf"}).status_code == 400
