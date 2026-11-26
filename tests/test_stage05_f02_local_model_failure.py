"""F02: observed Ollama transport failure is not semantic retry or host phase-1."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as bridge
from latka_jazn.core.conversation_runner import _host_finalization_pending
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedSynthesis
from latka_jazn.core.model_transport_failure import (
    ollama_transport_failure, terminal_local_model_failure,
)
from latka_jazn.core.recovery_policy import RecoveryPolicy


def _response(code: str = "http_error_500", *, dispatched: bool = True) -> dict[str, Any]:
    return {
        "adapter_id": "local_llm_adapter", "provider": "ollama", "model": "synthetic",
        "generated": False, "status": code, "text": "",
        "transport": {
            "error_code": code,
            "attempts": [{
                "error_code": code, "status": code, "request_dispatched": dispatched,
                "model_transport_circuit": {"state": "open" if not dispatched else "closed"},
                "error": "CANARY_PRIVATE_PROVIDER_ERROR",
            }],
        },
    }


def _decision(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_executor_preflight": {"executor": "local_model"},
        "model_guided_synthesis": {"used": False, "adapter_response": response},
        "model_generated": False,
        "requires_host_model": True,
    }


@pytest.mark.parametrize(("code", "dispatched"), [
    ("http_error_500", True), ("model_request_timeout", True),
    ("model_circuit_open", False), ("ollama_chat_response_truncated", True),
])
def test_failure_evidence_contains_only_bounded_observed_fields(code: str, dispatched: bool) -> None:
    evidence = ollama_transport_failure(_response(code, dispatched=dispatched))
    assert evidence is not None
    assert evidence["error_code"] == code
    assert evidence["request_dispatched"] is dispatched
    assert evidence["automatic_retry_allowed"] is False
    assert evidence["host_generation_authorized"] is False
    assert "CANARY" not in repr(evidence)


def test_completed_semantic_candidate_and_unknown_or_unbound_failures_not_classified() -> None:
    assert ollama_transport_failure({**_response(), "status": "completed", "generated": True}) is None
    assert ollama_transport_failure(_response("CANARY_PRIVATE_PROVIDER_ERROR")) is None
    raw = _response()
    raw["transport"]["attempts"][0].pop("request_dispatched")
    assert ollama_transport_failure(raw) is None
    decision = _decision(_response())
    decision["model_executor_preflight"]["executor"] = "host_bridge"
    assert terminal_local_model_failure(decision) is None
    decision = _decision(_response())
    decision["model_guided_retry_synthesis"] = {"used": True, "adapter_response": {}}
    assert terminal_local_model_failure(decision) is None


def test_latest_failed_semantic_retry_preserves_actual_transport_cause() -> None:
    decision = _decision({"status": "completed", "generated": True})
    decision["model_guided_retry_synthesis"] = {
        "used": False, "adapter_response": _response("model_request_timeout"),
    }
    evidence = terminal_local_model_failure(decision)
    assert evidence is not None
    assert evidence["error_code"] == "model_request_timeout"


def test_recovery_does_not_repeat_failed_local_transport() -> None:
    response = _response()
    synthesis = ModelGuidedSynthesis(
        False, "synthetic draft", "available", "jazn_runtime", "runtime",
        "selected_runtime_fallback_candidate", [], adapter_response=response,
    )
    def unexpected_retry(**_kwargs: Any) -> Any:
        raise AssertionError("failed transport must not trigger a second inference")
    validation = SimpleNamespace(accepted=True, mismatch_reason="", missing_required_components=[])
    engine = SimpleNamespace(
        model_guided_response_synthesizer=SimpleNamespace(synthesize=unexpected_retry),
        template_registry=SimpleNamespace(classify_body=lambda *_a, **_k: {}),
        runtime_answer_validator=SimpleNamespace(validate=lambda **_k: validation),
        continuity_badge_policy=SimpleNamespace(apply=lambda body, _decision: (body, {})),
    )
    state = SimpleNamespace(
        detected_dialogue_intent="ordinary_conversation",
        handler_result=SimpleNamespace(data={}, body="synthetic draft"),
        model_synthesis=synthesis, first_validation=validation, template_origin={},
        model_executor=SimpleNamespace(executor="local_model", retry_allowed=True),
        decision_dict=_decision(response), adapter_status={"adapter_id": "local_llm_adapter"},
        handler_missing=[], handler_required=[], handler_satisfied=set(),
        request=SimpleNamespace(text="synthetic", client_context={}), body="synthetic draft",
    )
    RecoveryPolicy(cast(Any, engine)).resolve(cast(Any, state))
    assert state.decision_dict["model_guided_retry_suppressed_reason"] == "http_error_500"
    assert state.decision_dict["model_generated"] is False
    assert state.candidate_valid is False


def test_failed_local_executor_cannot_create_or_persist_host_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    result: dict[str, Any] = {
        "ok": False, "answer_ok": False,
        "conversation_decision": _decision(_response()),
        "runtime_turn_contract": {"requires_host_model": True, "fallback_classification": "cannot_answer_directly"},
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": False,
                               "errors": ["model_guided_speech_required"]},
        "trace": {"turn_id": "synthetic-turn", "trace_id": "synthetic-trace"},
        "daemon": {"request_id": "synthetic-request", "daemon_instance_id": "synthetic-instance"},
        "final_visible_text": "CANARY_REJECTED_BODY",
    }
    assert _host_finalization_pending(result, can_continue=True) == (False, [])
    assert bridge.chatgpt_result_requires_host_visible_reply(result) is False
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("local failure must not persist a host request")
    monkeypatch.setattr(bridge, "persist_pending_host_request", forbidden)
    config = JaznConfig(root=tmp_path)
    bridge.attach_chatgpt_host_contract(result, config=config, user_text="synthetic",
                                      chat_bridge_meta={"request_id": "synthetic-request"})
    contract = result["chatgpt_host_bridge"]
    assert contract["phase"] == "host_diagnostic_required"
    assert contract["diagnostic_reason"] == "http_error_500"
    assert contract["host_must_generate_visible_reply"] is False
    assert contract["host_reply_finalization_required"] is False
    assert "host_request_contract_hash" not in contract
    assert "host_generation_context" not in contract
    presentation = result["chatgpt_host_presentation"]
    assert presentation["action"] == "host_diagnostic"
    assert presentation["final_visible_text"] == ""
    assert presentation["diagnostic_reason"] == "http_error_500"
    assert presentation["must_not_claim_latka_voice"] is True
    assert bridge.public_phase1_authorization_error(
        config, result, request_id="synthetic-request", host="127.0.0.1", port=8787,
    ) is None
    # A contradictory pending public job still fails the original binding gate.
    result["daemon_job"] = {"phase_result_ready": True, "awaiting_host_finalization": True}
    assert bridge.public_phase1_authorization_error(
        config, result, request_id="synthetic-request", host="127.0.0.1", port=8787,
    ) == "phase1_public_job_binding_unverified"
