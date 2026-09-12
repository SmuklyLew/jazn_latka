from __future__ import annotations

from dataclasses import dataclass

from latka_jazn.core.model_executor_preflight import resolve_model_executor
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.model_adapters.chatgpt_runtime_adapter import ChatgptRuntimeAdapter
from latka_jazn.model_adapters.null_model_adapter import NullModelAdapter


@dataclass
class LocalAdapter:
    calls: int = 0

    def describe(self) -> dict:
        return {
            "adapter_id": "local_test_model",
            "provider": "local",
            "model": "test",
            "status": "configured",
            "configured": True,
            "can_generate_model_guided_speech": True,
        }

    def generate(self, request):
        self.calls += 1
        from latka_jazn.model_adapters.base import ModelAdapterResponse
        return ModelAdapterResponse(text="Odpowiedź lokalna.", provider="local", model="test", status="completed")


def _synthesize(adapter):
    return ModelGuidedResponseSynthesizer().synthesize(
        adapter=adapter,
        user_text="Opowiedz coś.",
        draft_body="Szkic.",
        detected_intent="self_expression_request",
        route="self_expression",
        cognitive_frame={},
        response_policy={},
    )


def test_chatgpt_adapter_is_host_bridge_without_local_generation() -> None:
    adapter = ChatgptRuntimeAdapter()
    preflight = resolve_model_executor(adapter)
    result = _synthesize(adapter)
    assert preflight.executor == "host_bridge"
    assert preflight.retry_allowed is False
    assert result.used is False
    assert result.status == "host_visible_generation_requested"
    assert result.source_origin == "chatgpt_host_bridge"


def test_null_adapter_is_unavailable_without_fake_attempt() -> None:
    adapter = NullModelAdapter()
    preflight = resolve_model_executor(adapter)
    result = _synthesize(adapter)
    assert preflight.executor == "unavailable"
    assert preflight.retry_allowed is False
    assert result.used is False


def test_non_language_voice_adapter_is_unavailable() -> None:
    class VoiceLike:
        def describe(self):
            return {"adapter_id": "voice_model_adapter", "status": "configured", "configured": True}
    assert resolve_model_executor(VoiceLike()).executor == "unavailable"


def test_non_object_adapter_status_is_unavailable() -> None:
    class MalformedAdapter:
        def describe(self) -> object:
            return None

    preflight = resolve_model_executor(MalformedAdapter())

    assert preflight.executor == "unavailable"
    assert preflight.available is False
    assert preflight.retry_allowed is False


def test_configured_local_model_is_only_retry_eligible_executor() -> None:
    preflight = resolve_model_executor(LocalAdapter())
    assert preflight.executor == "local_model"
    assert preflight.available is True
    assert preflight.retry_allowed is True
