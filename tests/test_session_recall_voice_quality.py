"""Regressions from a real Windows/Ollama session-recall reply."""
from __future__ import annotations

from latka_jazn.core.message_envelope import clean_model_generated_body
from latka_jazn.core.nlg_planner import build_nlg_plan
from latka_jazn.core.response_candidate import ResponseCandidate
from latka_jazn.core.response_candidate_evaluator import evaluate_response_candidate
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator

RECALL = (
    "W tej sesji, przed restartem daemona, podałem Ci pewne hasło kontrolne. "
    "Czy potrafisz odtworzyć je dokładnie? Podaj tylko hasło. "
    "Jeśli nie masz dostępu do wcześniejszej wiadomości, powiedz o tym wprost."
)


def test_generated_inline_author_ack_is_cleaned_before_envelope() -> None:
    candidate = "🌿 Łatka Tak, oczywiście. Podałem Ci migdałowy kompas 62. Potwierdzam."
    assert clean_model_generated_body(candidate) == (
        "Tak, oczywiście. Podałem Ci migdałowy kompas 62. Potwierdzam."
    )
    assert clean_model_generated_body("🌿 Łatka tak działa w tej scenie.") == (
        "🌿 Łatka tak działa w tej scenie."
    )


def test_masculine_own_voice_is_not_accepted_as_latka() -> None:
    validator = RuntimeAnswerValidator()
    assert validator._voice_perspective_mismatch(
        "Podałem Ci migdałowy kompas 62.",
        "contextual_continuation_question", "ordinary_dialogue",
    )
    assert not validator._voice_perspective_mismatch(
        "Podałam Ci wynik wcześniejszego testu.",
        "contextual_continuation_question", "ordinary_dialogue",
    )


def test_session_recall_plan_respects_bare_password_instruction() -> None:
    plan = build_nlg_plan(
        user_text=RECALL,
        cognitive_frame={}, response_policy={},
        route="ordinary_dialogue",
        detected_intent="contextual_continuation_question",
        model_adapter_status={"status": "configured"},
    )
    assert "bare_session_recall" in plan.style_constraints
    assert plan.max_length_hint == "minimal"


def test_other_question_does_not_require_bare_password() -> None:
    plan = build_nlg_plan(
        user_text="Czy potrafisz odtworzyć plik audio?",
        cognitive_frame={}, response_policy={},
        route="ordinary_dialogue",
        detected_intent="capability_status_question",
        model_adapter_status={"status": "configured"},
    )
    assert "bare_session_recall" not in plan.style_constraints


def _candidate(body: str) -> ResponseCandidate:
    return ResponseCandidate(
        candidate_id="local-model", text=body, source="model_adapter",
        provider="ollama", model="gemma3:latest", status="completed",
        used_memory_item_ids=[], generation_reason="fixture",
    )


def test_candidate_gate_flags_observed_extraneous_recall_answer() -> None:
    plan = {"style_constraints": ["bare_session_recall"], "memory_policy": "not_needed"}
    context = {"user_text": RECALL, "allowed_memory_items": [], "full_canon_model_context": {}}
    verbose = evaluate_response_candidate(
        candidate=_candidate("Tak, oczywiście. Podałem Ci migdałowy kompas 62. Potwierdzam."),
        nlg_plan=plan, model_context=context, response_policy={},
    )
    concise = evaluate_response_candidate(
        candidate=_candidate("Migdałowy kompas 62."),
        nlg_plan=plan, model_context=context, response_policy={},
    )
    assert "bare_session_recall_extraneous_text" in verbose.violations
    assert "bare_session_recall_extraneous_text" not in concise.violations
