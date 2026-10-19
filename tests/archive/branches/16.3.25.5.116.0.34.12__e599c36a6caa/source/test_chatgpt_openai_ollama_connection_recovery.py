from __future__ import annotations

import json

import pytest

from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter
from tools.chatgpt_mcp_connection_doctor import inspect_plugin_dir


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        (["not an object"], "ollama_chat_response_not_object"),
        ({"done": False, "message": {"content": "partial"}}, "ollama_chat_response_not_complete"),
        ({"message": {"content": "missing final"}}, "ollama_chat_response_not_complete"),
        ({"done": True, "message": []}, "ollama_chat_message_invalid"),
        ({"done": True, "message": {"content": {"unexpected": "object"}}}, "ollama_chat_content_invalid"),
    ],
)
def test_ollama_never_promotes_malformed_or_incomplete_response(monkeypatch, payload, error_code):
    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen",
        lambda *_args, **_kwargs: FakeResponse(payload),
    )
    adapter = LocalLlmAdapter(model="gemma3:4b")
    result = adapter.generate(
        ModelAdapterRequest(prompt="Powiedz coś.", system_context={"route": "ordinary_dialogue"})
    )
    assert result.generated is False
    assert result.status == "invalid_provider_response"
    assert result.text == ""
    assert result.transport["attempts"][0]["error_code"] == error_code
    assert result.transport["retry_count"] == 0


def test_ollama_probe_does_not_accept_a_different_size_tag(monkeypatch):
    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen",
        lambda *_args, **_kwargs: FakeResponse({"models": [{"name": "gemma3:4b"}]}),
    )
    exact = LocalLlmAdapter(model="gemma3:12b").probe()
    default = LocalLlmAdapter(model="gemma3").probe()
    assert exact["probe_ok"] is False
    assert default["probe_ok"] is False
    assert exact["endpoint_reachable"] is True


def test_ollama_probe_allows_explicit_default_latest(monkeypatch):
    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen",
        lambda *_args, **_kwargs: FakeResponse({"models": [{"name": "gemma3:latest"}]}),
    )
    assert LocalLlmAdapter(model="gemma3").probe()["probe_ok"] is True


def test_plugin_doctor_distinguishes_oauth_declaration_from_live_auth(tmp_path):
    metadata = {"mcpServers": {"jazn": {
        "type": "streamable-http", "url": "https://jazn.example.test/mcp",
        "extensions": {"com.openai": {"auth": {"type": "oauth"}}},
    }}}
    (tmp_path / "mcp.json").write_text(json.dumps(metadata), encoding="utf-8")
    declared = inspect_plugin_dir(tmp_path)
    assert declared["remote_oauth_declared"] is True
    assert declared["remote_oauth_verified"] is False
    assert declared["remote_runtime_verified"] is False

    metadata["mcpServers"]["jazn"].pop("extensions")
    (tmp_path / "mcp.json").write_text(json.dumps(metadata), encoding="utf-8")
    missing = inspect_plugin_dir(tmp_path)
    assert missing["remote_oauth_declared"] is False
    assert missing["endpoint_config_valid_for_remote_chatgpt"] is True
    assert missing["next_action"] == "add_oauth_declaration_and_verify_protected_resource_metadata"
