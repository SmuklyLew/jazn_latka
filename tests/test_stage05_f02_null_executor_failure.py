"""F02: auto/null is not an implicit authorization to execute a host model."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as bridge
from latka_jazn.core import llm_route_resolver as routes
from latka_jazn.core.conversation_runner import _host_finalization_pending
from latka_jazn.core.model_executor_preflight import resolve_model_executor
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.core.model_guided_speech_runtime import build_speech_adapter_for_turn
from latka_jazn.core.model_transport_failure import (
    model_failure_projection, terminal_local_model_failure, terminal_model_failure,
)
from latka_jazn.model_adapters.null_model_adapter import NullModelAdapter


@pytest.fixture
def null_decision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    for key, value in {
        "JAZN_MODEL_ADAPTER": "null", "JAZN_LLM_ROUTE": "auto",
        "JAZN_ASSUME_CHATGPT_HOST": "0", "JAZN_ALLOW_PAID_OPENAI": "0",
        "JAZN_MODEL_GUIDED_SPEECH": "1", "JAZN_LLM_ROUTE_SKIP_LOCAL_PROBE": "1",
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("JAZN_OLLAMA_MODEL", "JAZN_LOCAL_LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("unavailable null route must not dispatch inference or discovery")

    monkeypatch.setattr(routes, "probe_ollama", forbidden)
    monkeypatch.setattr(NullModelAdapter, "generate", forbidden)
    config = JaznConfig(root=tmp_path, model_adapter="null", llm_route_mode="auto",
                        local_model_name="", allow_network=False)
    adapter, status = build_speech_adapter_for_turn(
        config, command="--chat", probe_local=False,
    )
    assert isinstance(adapter, NullModelAdapter)
    preflight = resolve_model_executor(adapter)
    synthesis = ModelGuidedResponseSynthesizer().synthesize(
        adapter=adapter, user_text="synthetic", draft_body="CANARY_INTERNAL_DRAFT",
        detected_intent="ordinary_conversation", route="ordinary_conversation",
        cognitive_frame={}, response_policy={}, executor_preflight=preflight,
    )
    return {
        "model_executor_preflight": preflight.to_dict(),
        "model_guided_speech_status": status.to_dict(),
        "model_guided_synthesis": synthesis.to_dict(),
        "model_generated": False,
        "requires_host_model": True,
        "fallback_classification": "cannot_answer_directly",
    }


def test_null_executor_has_bounded_non_transport_evidence(null_decision: dict[str, Any]) -> None:
    assert terminal_local_model_failure(null_decision) is None
    failure = terminal_model_failure(null_decision)
    assert failure is not None
    assert failure["error_code"] == "external_model_not_configured"
    assert failure["failure_kind"] == "executor_unavailable"
    assert failure["request_dispatched"] is False
    assert failure["automatic_retry_allowed"] is False
    assert failure["host_generation_authorized"] is False
    assert "CANARY" not in repr(failure)
    assert "endpoint" not in failure
    assert model_failure_projection(failure) == (
        "model_executor_unavailable", "model_executor_unavailable",
    )


@pytest.mark.parametrize(("path", "replacement"), [
    (("requires_host_model",), False),
    (("model_generated",), True),
    (("fallback_classification",), "not_fallback"),
    (("model_executor_preflight", "executor"), "host_bridge"),
    (("model_guided_speech_status", "selected_route"), "chatgpt_host"),
    (("model_guided_speech_status", "can_complete_model_guided_speech_via_host"), True),
    (("model_guided_speech_status", "llm_route_status", "chatgpt_bridge", "declared"), True),
    (("model_guided_speech_status", "llm_route_status", "route_mode"), "none"),
    (("model_guided_speech_status", "llm_route_status", "paid_route"), True),
    (("model_guided_synthesis", "reason"), "verified_accepted_turn"),
    (("model_guided_synthesis", "host_generation_context"), {"synthetic": True}),
    (("model_guided_retry_synthesis",), {"used": True}),
])
def test_null_classifier_requires_consistent_runtime_evidence(
    null_decision: dict[str, Any], path: tuple[str, ...], replacement: Any,
) -> None:
    target = null_decision
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = replacement
    assert terminal_model_failure(null_decision) is None


@pytest.mark.parametrize("stale_bridge", [False, True])
def test_null_route_cannot_create_host_generation_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    null_decision: dict[str, Any], stale_bridge: bool,
) -> None:
    result: dict[str, Any] = {
        "ok": False, "answer_ok": False,
        "conversation_decision": null_decision,
        "runtime_turn_contract": {
            "requires_host_model": True, "fallback_classification": "cannot_answer_directly",
        },
        "runtime_truth_gate": {
            "ok": True, "normal_response_allowed": False, "errors": ["model_guided_speech_required"],
        },
        "trace": {"turn_id": "synthetic-turn", "trace_id": "synthetic-trace"},
        "daemon": {"request_id": "synthetic-request", "daemon_instance_id": "synthetic-instance"},
        "final_visible_text": "CANARY_REJECTED_BODY",
    }
    if stale_bridge:
        result["chatgpt_host_bridge"] = {
            "phase": "host_visible_generation_requested",
            "host_generation_context": {"synthetic": True},
        }
    assert _host_finalization_pending(result, can_continue=True) == (False, [])
    assert bridge.chatgpt_result_requires_host_visible_reply(result) is False

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("null route must not persist a phase-1 request")

    monkeypatch.setattr(bridge, "persist_pending_host_request", forbidden)
    config = JaznConfig(root=tmp_path)
    bridge.attach_chatgpt_host_contract(result, config=config, user_text="synthetic",
                                      chat_bridge_meta={"request_id": "synthetic-request"})
    contract = result["chatgpt_host_bridge"]
    assert contract["phase"] == "host_diagnostic_required"
    assert contract["status"] == "model_executor_unavailable"
    assert contract["diagnostic_reason"] == "external_model_not_configured"
    assert contract["model_executor_unavailable"]["request_dispatched"] is False
    assert contract["host_must_generate_visible_reply"] is False
    assert contract["host_reply_finalization_required"] is False
    assert contract["must_not_replay"] is True
    assert "host_request_contract_hash" not in contract
    assert "host_generation_context" not in contract
    assert "model_transport_failure" not in contract
    presentation = result["chatgpt_host_presentation"]
    assert presentation["action"] == "host_diagnostic"
    assert presentation["final_visible_text"] == ""
    assert presentation["diagnostic_reason"] == "external_model_not_configured"
    assert presentation["must_not_claim_latka_voice"] is True
    assert bridge.public_phase1_authorization_error(
        config, result, request_id="synthetic-request", host="127.0.0.1", port=8787,
    ) is None
