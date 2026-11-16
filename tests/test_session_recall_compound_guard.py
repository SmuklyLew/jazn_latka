"""Regression for local Ollama session recall after a full daemon/Windows restart.

This tests the NLP/validator boundary only; persistent conversation-state
readback and live finalization require separate integration tests.
"""
from __future__ import annotations

import pytest

from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.nlp.utterance_components import analyse_utterance


WINDOWS_RESTART_RECALL = (
    "W tej sesji, przed wyłączeniem komputera, podałem Ci pewne hasło kontrolne. "
    "Czy potrafisz odtworzyć je dokładnie? Podaj tylko hasło. "
    "Jeśli nie masz dostępu do wcześniejszej wiadomości, powiedz o tym wprost."
)


@pytest.mark.parametrize("user_text", [
    WINDOWS_RESTART_RECALL,
    "W tej sesji podałem hasło. Czy potrafisz odtworzyć je dokładnie? Podaj hasło.",
    "Czy potrafisz przypomnieć mi hasło z pierwszej wiadomości tej sesji? Podaj samo hasło.",
    "W naszej rozmowie było hasło. Czy potrafisz przywołać je dokładnie? Podaj hasło.",
    "Jaka była treść mojej wcześniejszej wiadomości? Podaj tylko jej treść.",
])
def test_session_record_recall_is_not_falsely_compound(user_text: str) -> None:
    report = analyse_utterance(user_text)
    assert report.compound is False, report.to_dict()
    assert "capabilities" not in report.components, report.to_dict()
    assert "history" not in report.components, report.to_dict()


def test_rejected_windows_recall_candidate_no_longer_requires_unrelated_parts() -> None:
    report = DialogueIntentClassifier().classify(WINDOWS_RESTART_RECALL)
    assert report.primary_intent == "contextual_continuation_question", report.to_dict()
    assert report.question_object == "session_dialogue_history", report.to_dict()
    assert report.compound is False, report.to_dict()

    result = RuntimeAnswerValidator().validate(
        user_text=WINDOWS_RESTART_RECALL,
        body="bursztynowy tramwaj 47",
        route="ordinary_dialogue",
        detected_intent="contextual_continuation_question",
    )
    assert result.accepted, result.to_dict()
    assert not result.missing_required_components, result.to_dict()


def test_real_capability_question_is_still_detected() -> None:
    report = analyse_utterance("Czy potrafisz programować po polsku?")
    assert "capabilities" in report.components, report.to_dict()


def test_media_playback_ability_is_not_mistaken_for_session_recall() -> None:
    report = analyse_utterance("Czy potrafisz odtworzyć nagranie audio?")
    assert "capabilities" in report.components, report.to_dict()


@pytest.mark.parametrize("question", [
    "Kim jesteś i co potrafisz?",
    "Co potrafisz? Jaka jest twoja historia?",
    "Co zmieniło się we wcześniejszych wersjach? Co potrafisz teraz?",
])
def test_real_multi_goal_question_keeps_compound_gate(question: str) -> None:
    report = analyse_utterance(question)
    assert report.compound is True, report.to_dict()
    assert "capabilities" in report.components, report.to_dict()
    assert ("identity" in report.components or "history" in report.components), report.to_dict()


def test_real_compound_still_rejects_missing_capability_evidence() -> None:
    result = RuntimeAnswerValidator().validate(
        user_text="Kim jesteś i co potrafisz?",
        body="Jestem Łatką, działającą przez runtime.",
        route="identity_direct_question",
        detected_intent="identity_direct_question",
    )
    assert result.accepted is False
    assert result.mismatch_reason == "missing_compound_question_components"
    assert result.missing_required_components == ["capabilities"]
