"""Host selection must fail closed on contradictory executor evidence."""
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.core.model_executor_preflight import (
    host_generation_requested,
    resolve_model_executor,
)
from latka_jazn.model_adapters.chatgpt_runtime_adapter import ChatgptRuntimeAdapter


@pytest.mark.parametrize("status", [
    {"adapter_id": "local_llm_adapter", "host_visible_generation_required": True},
    {"adapter_id": "openai_responses_adapter", "host_visible_generation_required": True},
    {"adapter_id": "null_model_adapter", "host_visible_generation_required": True},
    {"host_visible_generation_required": True},
    {"adapter_id": "local_llm_adapter", "host_visible_generation_required": "false"},
    {"adapter_id": "chatgpt_runtime_adapter", "host_visible_generation_required": False},
    {"adapter_id": "chatgpt_runtime_adapter", "available": False},
    {"adapter_id": "chatgpt_runtime_adapter", "configured": False},
    {"adapter_id": "chatgpt_runtime_adapter", "adapter_contract": {"available": False}},
    {"adapter_id": "chatgpt_runtime_adapter", "adapter_contract": {"configured": False}},
    {"adapter_id": "chatgpt_runtime_adapter",
     "adapter_contract": {"adapter_id": "local_llm_adapter"}},
])
def test_adapter_request_flag_cannot_override_executor_evidence(status: dict[str, Any]) -> None:
    preflight = resolve_model_executor(SimpleNamespace(describe=lambda: status))
    assert preflight.executor == "unavailable"
    assert preflight.available is False
    assert preflight.retry_allowed is False
    assert preflight.reason == "conflicting_host_executor_evidence"


def test_canonical_host_and_name_only_legacy_adapter_remain_eligible() -> None:
    for adapter in (
        ChatgptRuntimeAdapter(),
        SimpleNamespace(describe=lambda: {"name": "chatgpt_runtime_adapter"}),
    ):
        preflight = resolve_model_executor(adapter)
        assert preflight.executor == "host_bridge"
        assert preflight.available is True
        assert preflight.retry_allowed is False


@pytest.mark.parametrize("projection", ["runtime_turn_contract", "final_response_contract"])
@pytest.mark.parametrize("evidence", [
    None,
    {},
    {"executor": "local_model", "available": True},
    {"executor": "external_model", "available": True},
    {"executor": "host_bridge", "available": False},
    {"executor": "host_bridge", "available": True, "adapter_id": "local_llm_adapter"},
])
def test_other_contract_projection_cannot_override_negative_executor_evidence(
    projection: str, evidence: dict[str, Any] | None,
) -> None:
    result: dict[str, Any] = {
        "conversation_decision": {
            "model_executor_preflight": {"executor": "host_bridge", "available": True},
            "model_generation_required": True,
            "requires_host_model": True,
        },
        projection: {"model_executor_preflight": evidence, "requires_host_model": True},
    }
    assert host_generation_requested(result) is False


def test_legacy_projection_with_explicit_non_host_evidence_is_refused() -> None:
    result = {
        "final_response_contract": {
            "requires_host_model": True,
            "model_executor_preflight": {"executor": "local_model", "available": True},
        },
    }
    assert host_generation_requested(result) is False


def test_legacy_host_without_executor_evidence_retains_existing_compatibility() -> None:
    assert host_generation_requested({"final_response_contract": {"requires_host_model": True}})


def test_modern_result_cannot_replace_missing_decision_with_positive_projection() -> None:
    assert not host_generation_requested({
        "runtime_turn_contract": {
            "requires_host_model": True,
            "model_generation_required": True,
            "model_executor_preflight": {"executor": "host_bridge", "available": True},
        },
    })


def test_consistent_explicit_host_projections_remain_eligible() -> None:
    evidence = {"executor": "host_bridge", "available": True, "adapter_id": "chatgpt_runtime_adapter"}
    assert host_generation_requested({
        "conversation_decision": {
            "requires_host_model": True,
            "model_generation_required": True,
            "model_executor_preflight": evidence,
        },
        "runtime_turn_contract": {"model_executor_preflight": dict(evidence)},
        "final_response_contract": {"model_executor_preflight": dict(evidence)},
    })
