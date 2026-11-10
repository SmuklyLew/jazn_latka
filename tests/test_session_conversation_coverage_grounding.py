"""Regression: local Gemma/ChatGPT session recall is not autobiographical MEMORY.

The original Windows V127 case reported missing q2/q3 even for a correct
Polish answer grounded in the first accepted conversation-state record.
"""
from __future__ import annotations

import pytest

from latka_jazn.core.component_coverage_ledger import build_component_coverage_ledger
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator


QUESTION = (
    "To nasza druga wiadomość. "
    "Jakie słowo testowe podałem wcześniej? "
    "Przypomnij też, o co zapytałem w pierwszej wiadomości. "
    "Korzystaj wyłącznie z dostępnej historii naszej sesji."
)
FIRST_QUESTION = (
    "Witaj. Testujemy lokalną Jaźń V127 z Gemmą 3. "
    "W tej rozmowie naszym słowem testowym jest „latarnia”. "
    "Powiedz krótko, czy możesz teraz ze mną rozmawiać i jaki model odpowiada."
)
GOOD = (
    "Słowem testowym była latarnia. "
    "W pierwszej wiadomości zapytałeś, czy możesz teraz ze mną "
    "rozmawiać i jaki model odpowiada. "
    "Odpowiadam na podstawie historii tej sesji."
)


@pytest.fixture
def accepted_history() -> dict:
    return {
        "source_of_truth": "workspace_runtime/conversation_state per-turn accepted records",
        "session_id": "v127-tpa-ollama-001",
        "total_turn_count": 1,
        "selected_turn_count": 1,
        "omitted_turn_count": 0,
        "compaction_mode": "bounded_non_destructive_projection",
        "turns": [{
            "turn_id": "b310009c-7fc1-48f9-96da-95190e598acb",
            "user_text": FIRST_QUESTION,
            "assistant_text": "Witaj! Używam modelu Gemma 3.",
            "accepted_at_utc": "2026-11-10T07:54:03.808632+00:00",
            "source": "chat",
        }],
    }


def _ledger(body: str, history: dict | None) -> dict:
    return build_component_coverage_ledger(
        user_text=QUESTION, body=body, coverage_required=True,
        conversation_history=history,
    )


def test_grounded_inflected_polish_answer_covers_both_components(accepted_history):
    result = _ledger(GOOD, accepted_history)
    assert result["complete"] is True
    assert result["missing_component_ids"] == []
    assert [row["component_id"] for row in result["records"]] == ["q2", "q3"]
    assert [row["status"] for row in result["records"]] == ["covered", "covered"]
    assert any("accepted_session" in value for row in result["records"] for value in row["evidence"])


@pytest.mark.parametrize("wrong", [
    "Słowem testowym była gwiazda. W pierwszej wiadomości zapytałeś, czy możemy rozmawiać i jaki model odpowiada.",
    "Słowem testowym była gwiazda, nie latarnia. W pierwszej wiadomości zapytałeś, czy możemy rozmawiać i jaki model odpowiada.",
    "Słowem testowym była latarnia. W pierwszej wiadomości zapytałeś o pogodę.",
    "W pierwszej wiadomości zapytałeś, czy możemy rozmawiać i jaki model odpowiada.",
    "Słowem testowym była latarnia.",
])
def test_missing_conflicting_or_partial_answer_still_fails_closed(accepted_history, wrong):
    assert _ledger(wrong, accepted_history)["complete"] is False


@pytest.mark.parametrize("mutation", [
    lambda history: None,
    lambda history: {**history, "source_of_truth": "unverified_client_input"},
    lambda history: {**history, "omitted_turn_count": 1},
    lambda history: {**history, "total_turn_count": 2},
    lambda history: {**history, "turns": [{**history["turns"][0], "accepted_at_utc": ""}]},
    lambda history: {**history, "turns": [{**history["turns"][0], "assistant_text": ""}]},
])
def test_missing_or_unverified_session_history_does_not_certify_reply(accepted_history, mutation):
    assert _ledger(GOOD, mutation(accepted_history))["complete"] is False


def test_validator_propagates_session_history_without_memory_claim(accepted_history):
    validator = RuntimeAnswerValidator()
    result = validator.validate(
        user_text=QUESTION,
        body=GOOD,
        route="compound_dialogue",
        detected_intent="compound_dialogue_question",
        conversation_history=accepted_history,
    )
    assert result.component_coverage_ledger["complete"] is True
    assert "compound_component_coverage_incomplete" not in result.checks


def test_unrelated_question_does_not_get_session_coverage(accepted_history):
    question = "Czy sprawdziłaś stan daemona? Jakiej aktualizacji potrzebujemy?"
    result = build_component_coverage_ledger(
        user_text=question, body=GOOD, coverage_required=True,
        conversation_history=accepted_history,
    )
    assert not any(
        evidence.startswith("grounded:accepted_session")
        for row in result["records"] for evidence in row["evidence"]
    )
