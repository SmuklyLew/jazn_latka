"""Stage 05: model faults do not replay requests or share daemon circuit state."""
from pathlib import Path
from typing import Any
from email.message import Message
from urllib.error import HTTPError

import pytest

from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.openai_compatible_local_adapter import OpenAICompatibleLocalAdapter
from latka_jazn.model_adapters.openai_responses_adapter import OpenaiResponsesAdapter
from latka_jazn.model_adapters.siwc_plan_usage_adapter import SiwcPlanUsageAdapter, SIWC_REQUIRED_SCOPE


@pytest.mark.parametrize("provider", ["compatible", "paid", "siwc"])
def test_model_transport_circuit_survives_adapter_reconstruction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: str,
) -> None:
    calls: list[int] = []
    healthy = False

    def transport(*_a: Any, **_k: Any) -> Any:
        calls.append(1)
        if not healthy:
            raise TimeoutError("synthetic transport failure")
        if provider == "siwc":
            return iter([{"type": "response.completed", "response": {"status": "completed", "output_text": "OK"}}])
        return {"output_text": "OK"}

    def adapter() -> Any:
        if provider == "compatible":
            obj = OpenAICompatibleLocalAdapter(root=tmp_path, model="synthetic")
            monkeypatch.setattr(obj, "_post_json", transport)
        elif provider == "paid":
            obj = OpenaiResponsesAdapter(root=tmp_path, model="synthetic", api_key="synthetic-not-sent", operator_opt_in=True)
            monkeypatch.setattr(obj, "_post_json", transport)
        else:
            return SiwcPlanUsageAdapter(root=tmp_path, model="synthetic", access_token="synthetic-not-sent",
                granted_scopes=SIWC_REQUIRED_SCOPE, operator_opt_in=True, stream_transport=transport)
        return obj

    first = adapter()
    clock = [100.0]
    monkeypatch.setattr(first._transport_breaker, "_clock", lambda: clock[0])
    request = ModelAdapterRequest(prompt="synthetic")
    for _ in range(3):
        result = first.generate(request)
        assert not result.generated
    assert len(calls) == 3
    second = adapter()
    assert second._transport_breaker is first._transport_breaker
    assert second.generate(request).status == "model_circuit_open"
    assert len(calls) == 3
    healthy = True
    clock[0] += 16.0
    assert second.generate(request).generated
    assert len(calls) == 4
    assert second.describe()["model_transport_circuit"]["state"] == "closed"


@pytest.mark.parametrize("failure", ["timeout", "503", "401", "empty"])
def test_compatible_transport_does_not_replay_uncertain_or_denied_post(
    monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    calls: list[str] = []
    adapter = OpenAICompatibleLocalAdapter(model="synthetic")
    def post(endpoint: str, _payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(endpoint)
        if failure == "timeout":
            raise TimeoutError("synthetic")
        if failure == "empty":
            return {"output_text": ""}
        raise HTTPError("http://127.0.0.1", int(failure), "synthetic", Message(), None)
    monkeypatch.setattr(adapter, "_post_json", post)
    result = adapter.generate(ModelAdapterRequest(prompt="synthetic"))
    assert not result.generated
    assert calls == ["/responses"]


def test_compatible_explicit_unsupported_endpoint_can_negotiate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    adapter = OpenAICompatibleLocalAdapter(model="synthetic")
    def post(endpoint: str, _payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(endpoint)
        if endpoint == "/responses":
            raise HTTPError("http://127.0.0.1", 405, "unsupported", Message(), None)
        return {"choices": [{"message": {"content": "OK"}}]}
    monkeypatch.setattr(adapter, "_post_json", post)
    assert adapter.generate(ModelAdapterRequest(prompt="synthetic")).generated
    assert calls == ["/responses", "/chat/completions"]
