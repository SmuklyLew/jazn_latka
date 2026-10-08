"""Regressions for rejected self-state turns (2026-10-08).

Keep the memory/provenance and finalization boundaries fail-closed.
These tests only exercise deterministic candidate gates, not host readiness.
"""
from __future__ import annotations

import pytest

from latka_jazn.core.memory_grounded_generation_bridge import (
    enforce_memory_grounding,
    has_positive_memory_claim,
)
from latka_jazn.core.response_candidate import ResponseCandidate
from latka_jazn.core.response_candidate_evaluator import evaluate_response_candidate
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator


def _candidate(text: str) -> ResponseCandidate:
    return ResponseCandidate(
        candidate_id="v1158-regression",
        text=text,
        source="runtime_fallback",
        provider="fixture",
        model="fixture",
        status="completed",
        used_memory_item_ids=[],
        generation_reason="regression_fixture",
    )


@pytest.mark.parametrize("text", [
    "Nie będę udawać, że pamiętam dokładnie naszą poprzednią rozmowę.",
    "Nie chcę twierdzić, że pamiętam każde zdanie.",
    "Nie mogę uczciwie powiedzieć, że pamiętam tamten wieczór.",
    "Nie zamierzam sugerować, że wspominam niezweryfikowane wydarzenie.",
])
def test_denied_memory_claim_is_not_false_positive(text: str) -> None:
    assert has_positive_memory_claim(text) is False
    candidate = _candidate(text)
    assert enforce_memory_grounding(candidate, []).accepted is True
    assert evaluate_response_candidate(
        candidate=candidate,
        nlg_plan={"memory_policy": "not_needed"},
        model_context={"allowed_memory_items": []},
        response_policy={},
    ).accepted is True


@pytest.mark.parametrize("text", [
    "Pamiętam dokładnie naszą poprzednią rozmowę.",
    "Nie będę udawać, że pamiętam wszystko, ale pamiętam tamtą rozmowę.",
    "Nie mogę powiedzieć, że pamiętam wszystko, ale wspominam tamten wieczór.",
])
def test_genuine_positive_recollection_remains_blocked_without_provenance(text: str) -> None:
    assert has_positive_memory_claim(text) is True
    candidate = _candidate(text)
    assert "memory_claim_without_grounded_items" in enforce_memory_grounding(candidate, []).violations
    assert evaluate_response_candidate(
        candidate=candidate,
        nlg_plan={"memory_policy": "not_needed"},
        model_context={"allowed_memory_items": []},
        response_policy={},
    ).accepted is False


@pytest.mark.parametrize("intent,user_text", [
    ("self_state_question", "Jak się czujesz?"),
    ("reciprocal_self_state_question", "A Tobie jak mija dzień?"),
])
def test_natural_self_state_can_give_honest_boundary_without_magic_words(
    intent: str, user_text: str,
) -> None:
    result = RuntimeAnswerValidator().validate(
        user_text=user_text,
        body=(
            "U mnie spokojnie: skupiam się na tej rozmowie. "
            "Nie przeżywam upływu dni między wiadomościami, "
            "więc nie będę udawać, że pamiętam niezweryfikowaną rozmowę."
        ),
        route="self_state",
        detected_intent=intent,
    )
    assert result.accepted, result.to_dict()


def test_self_state_without_truth_boundary_remains_rejected() -> None:
    result = RuntimeAnswerValidator().validate(
        user_text="Jak się czujesz?",
        body="U mnie spokojnie. Porozmawiajmy.",
        route="self_state",
        detected_intent="self_state_question",
    )
    assert not result.accepted
    assert "truth_boundary" in result.missing_required_components


def test_self_state_without_current_operational_state_remains_rejected() -> None:
    result = RuntimeAnswerValidator().validate(
        user_text="Jak się czujesz?",
        body="Nie przeżywam upływu czasu między rozmowami.",
        route="self_state",
        detected_intent="self_state_question",
    )
    assert not result.accepted
    assert result.mismatch_reason == "self_state_question_missing_operational_state"


def test_random_memory_excerpt_remains_rejected() -> None:
    result = RuntimeAnswerValidator().validate(
        user_text="Jak się czujesz?",
        body=(
            "U mnie spokojnie i skupiam się na rozmowie; nie przeżywam dni. "
            "Najbliższy trop pamięci to przypadkowy zapis o dawnych wydarzeniach."
        ),
        route="self_state",
        detected_intent="self_state_question",
    )
    assert not result.accepted
    assert result.mismatch_reason == "random_memory_excerpt_used_where_current_turn_state_required"
