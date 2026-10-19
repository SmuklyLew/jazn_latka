from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter


class Response:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self.raw


def test_malformed_chat_json_preserves_responding_http_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", lambda *_a, **_kw: Response(b"{invalid"))
    adapter = LocalLlmAdapter(model="gemma3:4b")
    result = adapter.generate(ModelAdapterRequest(prompt="Test", system_context={}))
    assert result.generated is False
    assert result.status == "invalid_provider_response"
    assert result.transport["error_code"] == "ollama_chat_json_invalid"
    assert adapter._endpoint_reachable is True


def test_incomplete_chat_payload_preserves_responding_http_endpoint(monkeypatch) -> None:
    payload = json.dumps({"done": False, "message": {"content": "partial"}}).encode("utf-8")
    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", lambda *_a, **_kw: Response(payload))
    adapter = LocalLlmAdapter(model="gemma3:4b")
    result = adapter.generate(ModelAdapterRequest(prompt="Test", system_context={}))
    assert result.status == "invalid_provider_response"
    assert adapter._endpoint_reachable is True


def test_http_error_means_endpoint_responded_not_model_success(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise HTTPError("http://127.0.0.1:11434/api/chat", 503, "unavailable", {}, None)

    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", fail)
    adapter = LocalLlmAdapter(model="gemma3:4b")
    result = adapter.generate(ModelAdapterRequest(prompt="Test", system_context={}))
    assert result.status == "http_error_503"
    assert result.generated is False
    assert adapter._endpoint_reachable is True


def test_network_failure_is_not_promoted_to_endpoint_reachable(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", fail)
    adapter = LocalLlmAdapter(model="gemma3:4b")
    result = adapter.generate(ModelAdapterRequest(prompt="Test", system_context={}))
    assert result.generated is False
    assert adapter._endpoint_reachable is False


def test_invalid_tags_response_is_not_mislabeled_missing_model(monkeypatch) -> None:
    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", lambda *_a, **_kw: Response(b"{}"))
    adapter = LocalLlmAdapter(model="gemma3:4b")
    probe = adapter.probe()
    assert probe["probe_ok"] is False
    assert probe["endpoint_reachable"] is True
    assert probe["last_probe_error"] == "ollama_tags_response_invalid"


def test_http_tags_error_is_reachable_but_not_probe_ready(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise HTTPError("http://127.0.0.1:11434/api/tags", 401, "unauthorized", {}, None)

    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", fail)
    probe = LocalLlmAdapter(model="gemma3:4b").probe()
    assert probe["endpoint_reachable"] is True
    assert probe["probe_ok"] is False
    assert probe["last_probe_error"] == "http_error_401"
