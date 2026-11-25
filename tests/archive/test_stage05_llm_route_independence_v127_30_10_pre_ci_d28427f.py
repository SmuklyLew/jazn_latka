"""Stage 05: routing evidence is not an implicit model availability claim."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from latka_jazn.core import llm_route_resolver as router
from latka_jazn.core.model_guided_speech_runtime import build_speech_adapter_for_turn
from latka_jazn.core.runtime_environment import NULL_ADAPTER
from latka_jazn.model_adapters.null_model_adapter import NullModelAdapter


@dataclass
class Config:
    llm_route_mode: str = "auto"
    allow_paid_openai_api: bool = False
    model_adapter: str = "null"
    local_model_name: str = "synthetic:latest"
    local_model_api_base: str = "http://127.0.0.1:11434"
    model_name: str = "synthetic-external"


def _env(**values: str) -> dict[str, str]:
    return {"JAZN_LLM_ROUTE": "auto", **values}


def _synthetic_probe(_config: object, _env: object) -> dict[str, object]:
    return {
        "provider": "ollama",
        "adapter": "local_llm_adapter",
        "base_url": "http://127.0.0.1:11434",
        "model": "synthetic:latest",
        "configured_model": "synthetic:latest",
        "available": True,
        "endpoint_reachable": True,
        "reason": "synthetic_probe",
    }


def test_no_probe_does_not_turn_configured_model_into_ready_model() -> None:
    route = router.build_llm_route_status(
        Config(), env=_env(JAZN_OLLAMA_MODEL="synthetic:latest"),
        probe_local=False,
    )
    assert route.selected_route == router.ROUTE_NULL
    assert route.local["available"] is False
    assert route.local["checked"] is False
    assert route.local["candidate"]["reason"] == "probe_skipped_unverified"


def test_host_declaration_is_not_live_generator_proof() -> None:
    route = router.build_llm_route_status(
        Config(), command="--chat-gpt", env=_env(),
        probe_local=False,
    )
    assert route.chatgpt_bridge["declared"] is True
    assert route.chatgpt_bridge["generation_verified"] is False
    assert route.selected_route == router.ROUTE_NULL
    assert route.reason.endswith("without a generative model")


def test_explicit_verified_host_route_stays_distinct_from_local_model() -> None:
    route = router.build_llm_route_status(
        Config(), command="--chat-gpt",
        env=_env(JAZN_LLM_ROUTE="chatgpt_bridge", JAZN_CHATGPT_HOST_GENERATION_VERIFIED="1"),
        probe_local=False,
    )
    assert route.selected_route == router.ROUTE_CHATGPT_BRIDGE
    assert route.chatgpt_bridge["generation_verified"] is True
    assert route.local["available"] is False
    assert route.paid_route is False


@pytest.mark.parametrize("paid_flag", ["0", "1"])
def test_auto_never_uses_paid_api_as_implicit_fallback(paid_flag: str) -> None:
    route = router.build_llm_route_status(
        Config(),
        env=_env(OPENAI_API_KEY="synthetic-never-send",
                 JAZN_ALLOW_PAID_OPENAI=paid_flag),
        probe_local=False,
    )
    assert route.selected_route == router.ROUTE_NULL
    assert route.paid_route is False


def test_explicit_paid_route_requires_two_separate_guards() -> None:
    missing = router.build_llm_route_status(
        Config(), env=_env(JAZN_LLM_ROUTE="openai_api", OPENAI_API_KEY="synthetic"),
        probe_local=False,
    )
    assert missing.ok is False
    assert missing.paid_route is False
    enabled = router.build_llm_route_status(
        Config(), env=_env(JAZN_LLM_ROUTE="openai_api", OPENAI_API_KEY="synthetic",
                           JAZN_ALLOW_PAID_OPENAI="1"),
        probe_local=False,
    )
    assert enabled.selected_route == router.ROUTE_OPENAI_PAID
    assert enabled.paid_route is True


def test_local_only_route_is_preserved_with_real_probe_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(router, "probe_ollama", _synthetic_probe)
    route = router.build_llm_route_status(
        Config(), env=_env(), probe_local=True,
    )
    assert route.selected_route == router.ROUTE_LOCAL
    assert route.local["checked"] is True
    assert route.local["available"] is True
    assert route.paid_route is False


def test_host_and_local_priority_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(router, "probe_ollama", _synthetic_probe)
    route = router.build_llm_route_status(
        Config(), command="--chat-gpt",
        env=_env(JAZN_CHATGPT_HOST_GENERATION_VERIFIED="1"),
        probe_local=True,
    )
    assert route.selected_route == router.ROUTE_CHATGPT_BRIDGE
    assert route.local["available"] is True
    assert route.paid_route is False


def test_no_models_keeps_null_runtime_candidate_without_external_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = router.build_llm_route_status(Config(), env=_env(), probe_local=False)
    assert route.ok is True
    assert route.selected_route == router.ROUTE_NULL
    assert route.selected_adapter == NULL_ADAPTER
    assert route.error is None
