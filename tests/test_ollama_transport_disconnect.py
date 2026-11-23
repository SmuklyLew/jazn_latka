from http.client import IncompleteRead

import pytest

from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter


@pytest.mark.parametrize("suffix", ["", "/api/", "/api/chat"])
@pytest.mark.parametrize("failure", [TimeoutError(), IncompleteRead(b"{")])
def test_interrupted_chat_issues_one_post_and_preserves_failure(monkeypatch, suffix, failure):
    urls = []

    def interrupted(request, *, timeout):
        urls.append((request.method, request.full_url))
        raise failure

    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", interrupted)
    adapter = LocalLlmAdapter(model="test", api_base="http://localhost:11434" + suffix)
    result = adapter.generate(ModelAdapterRequest(prompt="test", system_context={}))
    assert urls == [("POST", "http://localhost:11434/api/chat")]
    assert result.generated is False
    assert result.transport["retry_count"] == 0
    assert result.transport["error_code"] == (
        "model_request_timeout" if isinstance(failure, TimeoutError) else "ollama_chat_response_truncated"
    )
