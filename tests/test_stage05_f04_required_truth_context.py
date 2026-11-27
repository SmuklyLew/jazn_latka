"""F04: mandatory truth strings cannot disappear during local context fitting."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as bridge
from latka_jazn.core.conversation_runner import _host_finalization_pending
from latka_jazn.core.local_model_context_compiler import compile_local_model_context
from latka_jazn.core.model_transport_failure import (
    ollama_context_rejection, ollama_terminal_attempt_failure, ollama_transport_failure,
)
from latka_jazn.core.recovery_policy import RecoveryPolicy
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedSynthesis
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter


def test_required_truth_survives_item_and_section_limits_and_minimal_projection() -> None:
    forbidden = [f"synthetic-rule-{index}" for index in range(30)]
    boundaries = ["ż" * 1700 + " NIE WOLNO ZGADYWAĆ", "x" * 800]
    result = compile_local_model_context({
        "forbidden_claims": forbidden,
        "required_truth_boundaries": boundaries,
        "nlg_plan": {"summary": "p" * 1500},
        "operational_thought_frame": {"notes": "t" * 1100},
        "voice_source_contract": {"notes": "v" * 1500},
        "full_canon_model_context": {"immutable_canon": {
            "identity_core": "a" * 1500, "relation_canon": "b" * 1500,
            "symbolic_world": "c" * 1500,
        }},
    }, max_chars=8000)
    assert result.diagnostics["ok"] is True
    assert result.diagnostics["required_truth_sections_preserved"] is True
    assert result.diagnostics["context_compacted"] is True
    assert result.context["forbidden_claims"] == forbidden
    assert result.context["required_truth_boundaries"] == boundaries
    assert len(json.dumps(result.context, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))) <= 8000


@pytest.mark.parametrize(("context", "code"), [
    ({"required_truth_boundaries": ["CANARY" * 2000]},
     "local_context_required_truth_sections_overflow"),
    ({"forbidden_claims": {"raw_payload": "CANARY"}},
     "local_context_required_truth_sections_invalid"),
    ({"forbidden_claims": ["CANARY" * 700], "required_truth_boundaries": ["SECRET" * 700]},
     "local_context_total_budget_exceeded"),
])
def test_context_refusal_never_dispatches_or_authorizes_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, context: dict[str, Any], code: str,
) -> None:
    monkeypatch.setenv("JAZN_MODEL_CONTEXT_MAX_CHARS", "8000")

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("context rejection must not perform model HTTP or host phase-1")

    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", forbidden)
    adapter = LocalLlmAdapter(root=tmp_path, model="synthetic")
    before = adapter.describe()["model_transport_circuit"]
    result = adapter.generate(ModelAdapterRequest(prompt="synthetic", system_context=context))
    assert result.status == "context_rejected"
    assert result.generated is False and result.text == ""
    assert result.endpoint_used is None
    assert result.transport["error_code"] == code
    assert result.transport["retry_count"] == 0
    assert result.transport["attempts"][0]["request_dispatched"] is False
    assert result.transport["attempts"][0]["required_truth_sections_preserved"] is False
    assert result.status_snapshot is not None
    assert result.status_snapshot.endpoint_reachable is None
    assert adapter.describe()["model_transport_circuit"]["state"] == before["state"]
    failure = ollama_context_rejection(result.to_dict())
    assert failure is not None
    assert ollama_transport_failure(result.to_dict()) is None
    assert ollama_terminal_attempt_failure(result.to_dict()) == failure
    assert failure["failure_kind"] == "context_rejection"
    assert failure["request_dispatched"] is False
    assert failure["prior_attempt_dispatched"] is False
    assert failure["automatic_retry_allowed"] is False
    assert failure["host_generation_authorized"] is False
    assert "CANARY" not in repr(result.to_dict()) and "SECRET" not in repr(result.to_dict())
    decision: dict[str, Any] = {
        "model_executor_preflight": {"executor": "local_model"},
        "model_generated": False, "requires_host_model": True,
        "model_guided_synthesis": {"used": False, "adapter_response": result.to_dict()},
    }
    payload: dict[str, Any] = {
        "ok": False, "answer_ok": False, "conversation_decision": decision,
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
    assert _host_finalization_pending(payload, can_continue=True) == (False, [])
    assert bridge.chatgpt_result_requires_host_visible_reply(payload) is False
    monkeypatch.setattr(bridge, "persist_pending_host_request", forbidden)
    bridge.attach_chatgpt_host_contract(payload, config=JaznConfig(root=tmp_path),
                                       user_text="synthetic", chat_bridge_meta={})
    contract = payload["chatgpt_host_bridge"]
    assert contract["status"] == "local_model_context_rejected"
    assert contract["diagnostic_reason"] == code
    assert contract["model_context_rejection"] == failure
    assert contract["host_must_generate_visible_reply"] is False
    assert contract["host_reply_finalization_required"] is False
    assert contract["must_not_replay"] is True
    assert "host_request_contract_hash" not in contract
    presentation = payload["chatgpt_host_presentation"]
    assert presentation["action"] == "host_diagnostic"
    assert presentation["diagnostic_reason"] == code
    assert presentation["final_visible_text"] == ""

    synthesis = ModelGuidedSynthesis(
        False, "synthetic draft", "available", "jazn_runtime", "runtime",
        "selected_runtime_fallback_candidate", [], adapter_response=result.to_dict(),
    )
    validation = SimpleNamespace(accepted=True, mismatch_reason="", missing_required_components=[])
    engine = SimpleNamespace(
        model_guided_response_synthesizer=SimpleNamespace(synthesize=forbidden),
        template_registry=SimpleNamespace(classify_body=lambda *_a, **_k: {}),
        runtime_answer_validator=SimpleNamespace(validate=lambda **_k: validation),
        continuity_badge_policy=SimpleNamespace(apply=lambda body, _decision: (body, {})),
    )
    state = SimpleNamespace(
        detected_dialogue_intent="ordinary_conversation",
        handler_result=SimpleNamespace(data={}, body="synthetic draft"),
        model_synthesis=synthesis, first_validation=validation, template_origin={},
        model_executor=SimpleNamespace(executor="local_model", retry_allowed=True),
        decision_dict=decision, adapter_status={"adapter_id": "local_llm_adapter"},
        handler_missing=[], handler_required=[], handler_satisfied=set(),
        request=SimpleNamespace(text="synthetic", client_context={}), body="synthetic draft",
    )
    RecoveryPolicy(cast(Any, engine)).resolve(cast(Any, state))
    assert state.decision_dict["model_guided_retry_suppressed_reason"] == code
    assert state.decision_dict["model_generated"] is False
    assert state.candidate_valid is False


@pytest.mark.parametrize("damage", ["unknown_code", "dispatched", "unbound", "no_refusal"])
def test_context_failure_classification_requires_actual_bounded_evidence(damage: str) -> None:
    code = "local_model_prompt_token_budget_exceeded"
    attempt: dict[str, Any] = {
        "status": "context_rejected", "error_code": code,
        "request_dispatched": False, "fallback_required": True,
    }
    response: dict[str, Any] = {
        "adapter_id": "local_llm_adapter", "provider": "ollama", "generated": False,
        "status": "context_rejected", "transport": {"error_code": code, "attempts": [attempt]},
    }
    assert ollama_context_rejection(response) is not None
    if damage == "unknown_code":
        attempt["error_code"] = response["transport"]["error_code"] = "CANARY"
    elif damage == "dispatched":
        attempt["request_dispatched"] = True
    elif damage == "unbound":
        attempt.pop("request_dispatched")
    else:
        attempt["fallback_required"] = False
    assert ollama_context_rejection(response) is None
