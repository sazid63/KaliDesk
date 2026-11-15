"""OpenAI-compatible servers on this computer (LM Studio and similar) need no API key;
remote hosts still do."""
from __future__ import annotations

import pytest

import server.ai as ai


def test_local_openai_compatible_server_needs_no_key(client):
    cfg = ai.resolve("openai", base_url="http://127.0.0.1:1234/v1", model="m")
    assert cfg["key"] == "" and cfg["url"] == "http://127.0.0.1:1234/v1"


def test_localhost_name_needs_no_key(client):
    assert ai.resolve("openai", base_url="http://localhost:1234/v1")["key"] == ""


def test_remote_openai_compatible_server_still_needs_a_key(client):
    with pytest.raises(ai.AIError, match="no API key"):
        ai.resolve("openai", base_url="https://api.example.com/v1")


def test_empty_answer_from_a_reasoning_model_is_an_explained_error(monkeypatch, client):
    cfg = ai.resolve("openai", base_url="http://127.0.0.1:1234/v1", model="m")

    def fake_http(method, url, body, headers, timeout=120):
        return {"choices": [{"message": {"role": "assistant", "content": "", "reasoning_content": "hmm"}}]}

    monkeypatch.setattr(ai, "_http", fake_http)
    with pytest.raises(ai.AIError, match="no answer text"):
        ai._chat_reply(cfg, [{"role": "user", "content": "hi"}])
