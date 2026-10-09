from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from latka_jazn.core.engine import JaznEngine

import pytest

from latka_jazn.core.message_envelope import clean_model_generated_body
from latka_jazn.core.response_candidate import CandidateEvaluation, ResponseCandidate
from latka_jazn.core.response_candidate_evaluator import (
    evaluate_response_candidate,
    select_best_candidate,
)
from latka_jazn.core.response_pipeline import ResponsePipeline
from latka_jazn.core.turn_pipeline_state import TurnPipelineState, TurnRequest
from latka_jazn.core.turn_pipeline_support import _model_guided_rejection_disclosure


def _candidate(identifier: str, source: str, text: str) -> ResponseCandidate:
    return ResponseCandidate(identifier, text, source, "ollama" if source == "model_adapter" else "jazn_runtime", "gemma3:latest" if source == "model_adapter" else "runtime", "completed", [], "test")


@pytest.mark.parametrize("route", [
    "ordinary_dialogue", "memory_experience_recall", "self_state",
    "creative_text", "capability_status", "fallback",
])
def test_safe_model_candidate_takes_precedence_over_runtime_draft_in_each_route(route):
    runtime = _candidate("runtime", "runtime_fallback", "Pierwszy szkic z runtime.")
    model = _candidate("model", "model_adapter", "Bezpieczna odpowiedź modelowa.")
    selected = select_best_candidate([runtime, model], [
        CandidateEvaluation(runtime.candidate_id, True, 0.99, [], [], False),
        CandidateEvaluation(model.candidate_id, True, 0.71, [], [], False),
    ])
    assert selected is model, route


@pytest.mark.parametrize("route", ["ordinary_dialogue", "memory_experience_recall", "self_state", "creative_text"])
def test_invalid_model_never_beats_safe_runtime_fallback(route):
    runtime = _candidate("runtime", "runtime_fallback", "Brak dowodów.")
    model = _candidate("model", "model_adapter", "Niepotwierdzona informacja.")
    chosen = select_best_candidate([runtime, model], [
        CandidateEvaluation("runtime", True, 0.5, [], [], False),
        CandidateEvaluation("model", False, 1.0, [], ["memory_claim_without_allowed_memory_payload"], True),
    ])
    assert chosen is runtime, route


def test_external_evidence_policy_and_exact_runtime_still_fail_closed():
    candidate = _candidate("model", "model_adapter", "Znalazłam źródła w internecie.")
    evaluation = evaluate_response_candidate(
        candidate=candidate,
        nlg_plan={"source_policy": "requires_external_web"},
        model_context={}, response_policy={"external_web_evidence_accepted": False, "exact_runtime_required": True},
    )
    assert evaluation.accepted is False
    assert "model_candidate_cannot_fake_external_web_sources" in evaluation.violations
    assert "exact_runtime_required_blocks_model_candidate" in evaluation.violations


@pytest.mark.parametrize("source", ["runtime_fallback", "model_adapter"])
def test_internal_memory_evidence_draft_is_not_a_visible_candidate(source):
    evidence = _candidate("candidate", source, "Materiał dowodowy do naturalnej odpowiedzi: - prywatny zapis")
    checked = evaluate_response_candidate(candidate=evidence, nlg_plan={}, model_context={}, response_policy={})
    assert checked.accepted is False
    assert "internal_memory_evidence_not_visible" in checked.violations


@pytest.mark.parametrize("raw,expected", [
    ("🕒 2026-10-09 01:39:43 Łatka.", "Łatka."),
    ("🕒 2026-10-09 01:39:43\n🌿 Łatka\n\nWitaj!", "Witaj!"),
    ("Witaj. 🕒 2026-10-09 01:39:43", "Witaj. 🕒 2026-10-09 01:39:43"),
    ("Wczoraj napisałam: 🕒 2026-10-09 01:39:43", "Wczoraj napisałam: 🕒 2026-10-09 01:39:43"),
])
def test_only_model_authored_prefix_is_stripped(raw, expected):
    assert clean_model_generated_body(raw) == expected


def test_rejected_fallback_never_claims_runtime_is_a_model():
    synthesis = SimpleNamespace(
        adapter_response={"status": "completed", "provider": "ollama", "model": "gemma3:latest"},
        status="available", provider="jazn_runtime", model="runtime", reason="selected_runtime_fallback_candidate",
        candidate_validation={"violations": []},
        candidate_evaluations=[{"source": "model_adapter", "violations": ["memory_claim_without_allowed_memory_payload"]}],
    )
    body, origin, quality, replied = _model_guided_rejection_disclosure(synthesis, SimpleNamespace(mismatch_reason=None, missing_required_components=[]))
    assert "ollama/gemma3:latest" in body
    assert "jazn_runtime/runtime" not in body
    assert "memory_claim_without_allowed_memory_payload" in body
    assert replied is True


def test_no_candidate_metadata_contains_raw_model_text():
    from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
    # The schema only contains evaluation metadata. The raw text must not be echoed into a list.
    assert "text" not in CandidateEvaluation("id", True, 0.6, [], [], False).to_dict()
    assert callable(ModelGuidedResponseSynthesizer._clean)


def test_response_pipeline_uses_one_turn_adapter_for_synthesis(monkeypatch):
    import latka_jazn.core.response_pipeline as pipeline
    adapter = Mock()
    adapter.describe.return_value = {"adapter_id": "local_llm_adapter", "provider": "ollama", "model": "gemma3:latest", "configured": True, "can_attempt_model_guided_speech": True}
    synth = Mock()
    synth.synthesize.return_value = SimpleNamespace(used=True, body="Działam.", to_dict=lambda: {"used": True})
    env = Mock()
    engine = SimpleNamespace(config=Mock(), model_adapter=Mock(), model_guided_response_synthesizer=synth,
                             _apply_model_synthesis_result=Mock(return_value=(adapter.describe(), True)),
                             guard=SimpleNamespace(enforce=lambda x: x))
    monkeypatch.setattr(pipeline, "build_speech_adapter_for_turn", lambda *args, **kwargs: (adapter, SimpleNamespace(to_dict=lambda: {"provider": "ollama"})))
    state = TurnPipelineState(request=TurnRequest("Cześć", {"command": "--chat-ollama", "model_channel_config": {"model": "gemma3:latest"}}))
    state.decision_dict = {"route": "ordinary_dialogue"}
    state.decision = SimpleNamespace(body="Fallback.")
    state.detected_dialogue_intent = "ordinary_conversation"
    state.route_entry = SimpleNamespace(route="ordinary_dialogue", handler_name="OrdinaryDialogueHandler")
    state.frame = {}
    state.turn_response_policy = SimpleNamespace(required_components=[], forbidden_topics=[], exact_runtime_required=False, to_dict=lambda: {})
    state.envelope = env
    ResponsePipeline(cast(JaznEngine, engine)).produce(state)
    assert synth.synthesize.call_args.kwargs["adapter"] is adapter
    assert engine._apply_model_synthesis_result.call_args.kwargs["adapter"] is adapter
    assert state.speech_adapter is adapter
