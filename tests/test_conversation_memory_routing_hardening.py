from __future__ import annotations

import pytest

from latka_jazn.core.memory_intent_contract import (
    analyze_memory_intent,
    is_session_dialogue_reference,
)
from latka_jazn.core.message_envelope import clean_model_generated_body
from latka_jazn.core.model_context_compiler import compile_model_context
from latka_jazn.core.memory_grounded_generation_bridge import (
    enforce_memory_grounding,
    has_positive_memory_claim,
)
from latka_jazn.core.response_candidate import ResponseCandidate
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Cześć. To pierwszy test naszej rozmowy. Odpowiedz naturalnie po polsku "
            "i wyjaśnij krótko, z jakiego źródła korzystasz przy tworzeniu odpowiedzi.",
            "runtime_source_question",
        ),
        ("Z jakiego źródła pochodzi Twoja odpowiedź?", "runtime_source_question"),
        ("Podaj źródła tej odpowiedzi.", "runtime_source_question"),
        ("Sprawdź w internecie aktualne informacje i podaj źródła.", "external_research_request"),
        ("Cześć. Chciałbym po prostu z tobą porozmawiać.", "ordinary_conversation"),
    ],
)
def test_response_source_not_external_research(text: str, expected: str) -> None:
    assert DialogueIntentClassifier().classify(text).primary_intent == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Czy pamiętasz moją pierwszą wiadomość w tej sesji? Powtórz jej sens.", True),
        ("Co napisałem w poprzedniej wiadomości w tej rozmowie?", True),
        ("Jakie słowa padły w pierwszej wiadomości naszej sesji?", True),
        ("Czy pamiętasz pierwszą wiadomość w innej sesji?", False),
        ("Czy pamiętasz pierwszą wiadomość sprzed roku?", False),
        ("Co pamiętasz z naszych rozmów w 2025 roku?", False),
    ],
)
def test_session_reference_scoped_to_current_conversation(text: str, expected: bool) -> None:
    assert is_session_dialogue_reference(text) is expected


@pytest.mark.parametrize("history_available", [True, False])
def test_first_message_route_is_not_autobiographical(history_available: bool) -> None:
    text = "Czy pamiętasz moją pierwszą wiadomość w tej sesji? Powtórz jej sens."
    report = DialogueIntentClassifier().classify(text, conversation_history_available=history_available)
    assert report.primary_intent == "contextual_continuation_question"
    flag = "accepted_session_history_available" if history_available else "accepted_session_history_unavailable"
    assert flag in report.evidence
    assert analyze_memory_intent(text).content_requested is False


def test_historical_memory_stays_on_grounded_recall_route() -> None:
    report = DialogueIntentClassifier().classify("Co pamiętasz z naszych rozmów w 2025 roku?")
    assert report.primary_intent == "memory_experience_question"


def test_durable_short_session_context_is_not_promoted_to_autobiography() -> None:
    previous = "Cześć. Chciałbym po prostu z tobą porozmawiać."
    packet = compile_model_context(
        user_text="Co napisałem w pierwszej wiadomości tej sesji?",
        cognitive_frame={"client_context": {"conversation_history": {
            "session_id": "v1277-dialogue-smoke-02",
            "turns": [{"turn_id": "turn-1", "trace_id": "trace-1", "user_text": previous,
                       "assistant_text": "Cześć!", "source": "runtime"}],
            "total_turn_count": 1,
        }}},
        nlg_plan={"detected_intent": "contextual_continuation_question",
                  "memory_policy": "not_needed", "source_policy": "runtime_only"},
        thought_frame={},
        response_policy={},
    ).to_dict()
    assert packet["conversation_history"]["session_id"] == "v1277-dialogue-smoke-02"
    assert packet["conversation_history"]["turns"][0]["user_text"] == previous
    assert packet["allowed_memory_items"] == []
    instructions = " ".join(packet["output_instructions"])
    assert "conversation_history.turns" in instructions
    assert "pamięć autobiograficzną" in instructions


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("🌿 Łatka 🌿 Łatka Cześć!", "Cześć!"),
        ("🌿 Łatka\n\nCześć!", "Cześć!"),
        ("🌿 Łatka: Cześć!", "Cześć!"),
        ("🕒 2026-11-15 12:34:51\n🌿 Łatka\n\n🌿 Łatka Cześć!", "Cześć!"),
        ("Cześć, 🌿 Łatka jest tu cytatem.", "Cześć, 🌿 Łatka jest tu cytatem."),
        ("🌿 Łatka wspomina fragment opowiadania.", "🌿 Łatka wspomina fragment opowiadania."),
    ],
)
def test_generated_author_prefix_is_stripped_only_when_structural(raw: str, expected: str) -> None:
    assert clean_model_generated_body(raw) == expected


def test_unbacked_autobiographical_memory_claim_stays_blocked() -> None:
    candidate = ResponseCandidate(
        "unsafe_memory", "Pamiętam nasze rozmowy sprzed roku.", "model_adapter",
        "ollama", "gemma3:latest", "completed", [], "test",
    )
    assert has_positive_memory_claim(candidate.text)
    evaluation = enforce_memory_grounding(candidate, [])
    assert not evaluation.accepted
    assert "memory_claim_without_grounded_items" in evaluation.violations
