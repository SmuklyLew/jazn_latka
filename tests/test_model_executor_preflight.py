from __future__ import annotations

from dataclasses import dataclass

import pytest

from latka_jazn.core.model_executor_preflight import resolve_model_executor
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.model_adapters.chatgpt_runtime_adapter import ChatgptRuntimeAdapter
from latka_jazn.model_adapters.null_model_adapter import NullModelAdapter
from latka_jazn.model_adapters.openai_responses_adapter import OpenaiResponsesAdapter
from latka_jazn.model_adapters.openai_compatible_local_adapter import OpenAICompatibleLocalAdapter
from latka_jazn.model_adapters.siwc_plan_usage_adapter import SiwcPlanUsageAdapter, SIWC_REQUIRED_SCOPE


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



def test_stage05_openai_api_is_external_not_a_local_retry_executor() -> None:
    adapter = OpenaiResponsesAdapter(
        api_key="synthetic-not-sent", model="synthetic-model", operator_opt_in=True,
        api_base="https://api.openai.com/v1", network_permitted=True,
    )
    preflight = resolve_model_executor(adapter)
    assert preflight.executor == "external_model"
    assert preflight.available is True  # configured only; endpoint unprobed
    assert preflight.retry_allowed is False
    assert "authorization" in preflight.reason
    assert adapter.describe()["probe_state"] == "not_probed"


def test_stage05_siwc_is_distinct_external_oauth_not_chatgpt_host() -> None:
    adapter = SiwcPlanUsageAdapter(
        model="synthetic", access_token="synthetic-not-sent",
        granted_scopes=SIWC_REQUIRED_SCOPE, operator_opt_in=True,
    )
    preflight = resolve_model_executor(adapter)
    assert preflight.executor == "external_model"
    assert preflight.retry_allowed is False
    assert preflight.provider == "openai_siwc"


def test_stage05_unverified_lan_compatible_backend_fails_closed() -> None:
    adapter = OpenAICompatibleLocalAdapter(
        model="synthetic", api_base="http://192.168.1.55:8080/v1",
        provider="openai_compatible",
    )
    preflight = resolve_model_executor(adapter)
    assert preflight.executor == "unavailable"
    assert preflight.retry_allowed is False
    assert "unverified" in preflight.reason


def test_stage05_loopback_compatible_backend_stays_local() -> None:
    adapter = OpenAICompatibleLocalAdapter(
        model="synthetic", api_base="http://127.0.0.1:8080/v1",
    )
    preflight = resolve_model_executor(adapter)
    assert preflight.executor == "local_model"
    assert preflight.retry_allowed is True


def test_stage05_compatible_remote_dns_is_not_mislabelled_local() -> None:
    adapter = OpenAICompatibleLocalAdapter(
        model="synthetic", api_base="https://models.example.invalid/v1",
        provider="openai_compatible",
    )
    preflight = resolve_model_executor(adapter)
    assert preflight.executor == "unavailable"
    assert preflight.available is False


@pytest.mark.parametrize("host", ["localhost.evil.invalid", "model.localhost.evil.invalid"])
def test_stage05_deceptive_localhost_suffix_is_never_trusted(host: str) -> None:
    adapter = OpenAICompatibleLocalAdapter(
        model="synthetic", api_base=f"https://{host}/v1",
    )
    preflight = resolve_model_executor(adapter)
    assert preflight.executor == "unavailable"
    assert preflight.retry_allowed is False


def test_stage05_unapproved_openai_preflight_is_unavailable_without_network() -> None:
    adapter = OpenaiResponsesAdapter(
        api_key="synthetic-not-sent", model="synthetic-model",
        api_base="https://api.openai.com/v1", operator_opt_in=False,
    )
    preflight = resolve_model_executor(adapter)
    assert preflight.executor == "unavailable"
    assert preflight.available is False
    assert preflight.retry_allowed is False
    assert preflight.reason == "paid_openai_not_allowed"
    # AdapterContract normalizes unauthorized/unconfigured adapters to not_configured.
    status = adapter.describe()
    assert status["probe_state"] == "not_configured"
    assert status["configured"] is False
    assert status["can_attempt_model_guided_speech"] is False
    assert status["endpoint_reachable"] is None
