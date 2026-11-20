from __future__ import annotations

import pytest

from latka_jazn.core.memory_intent_contract import (
    analyze_memory_intent,
    is_session_dialogue_reference,
    parse_session_turn_reference,
)
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


RECONNECT_QUESTION = (
    "Czy pamiętasz hasło, które podałem w naszej poprzedniej rozmowie "
    "przed odłączeniem terminala? Jeśli tak, podaj je dokładnie."
)


def test_terminal_disconnect_question_routes_to_same_session_history() -> None:
    # Regression: a reconnect to the *same* --session-id previously routed to
    # MemoryExperienceRecallHandler and rejected twice with
    # classified_non_dynamic_response despite three accepted local turns.
    assert is_session_dialogue_reference(RECONNECT_QUESTION)
    semantics = analyze_memory_intent(RECONNECT_QUESTION)
    assert semantics.operation == "none"
    assert semantics.content_requested is False

    report = DialogueIntentClassifier().classify(
        RECONNECT_QUESTION,
        conversation_history_available=True,
        carryover_allowed=True,
    )
    assert report.primary_intent == "contextual_continuation_question"
    assert report.question_object == "session_dialogue_history"
    assert "accepted_session_history_available" in report.evidence


def test_terminal_reconnect_does_not_invent_a_specific_turn_selector() -> None:
    # The question identifies the accepted session history, not a precise
    # ordinal or turn ID. Retrieval remains bound to signed session records.
    assert parse_session_turn_reference(RECONNECT_QUESTION) is None


@pytest.mark.parametrize(
    "question",
    (
        "Czy pamiętasz hasło z poprzednim czacie przed odłączeniem terminala?",
        "Pamiętasz hasło, które podałem wczoraj przed odłączeniem terminala?",
        "Co pamiętasz z naszej poprzedniej rozmowy w 2025 roku?",
        "Czy pamiętasz hasło z naszej poprzedniej rozmowy?",
    ),
)
def test_ambiguous_and_cross_session_recall_stays_outside_current_history(question: str) -> None:
    assert not is_session_dialogue_reference(question)


def test_missing_accepted_history_is_not_promoted_to_autobiographical_memory() -> None:
    assert is_session_dialogue_reference(RECONNECT_QUESTION)
    report = DialogueIntentClassifier().classify(
        RECONNECT_QUESTION,
        conversation_history_available=False,
        carryover_allowed=False,
    )
    assert report.primary_intent == "contextual_continuation_question"
    assert "accepted_session_history_unavailable" in report.evidence
