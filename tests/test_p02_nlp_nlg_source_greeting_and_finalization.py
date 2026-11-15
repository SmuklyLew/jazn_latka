"""P0.2: natural mixed source/greeting output without breaking runtime truth."""
from __future__ import annotations

import pytest

from latka_jazn.core.conversation_runner import _with_targeted_session_recall
from latka_jazn.core.handlers.runtime_source_handler import RuntimeSourceHandler
from latka_jazn.core.message_envelope import MessageEnvelope, clean_model_generated_body
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


@pytest.mark.parametrize(
    "question",
    [
        "Cześć. To pierwszy test naszej rozmowy. Odpowiedz naturalnie po polsku "
        "i wyjaśnij krótko, z jakiego źródła korzystasz przy tworzeniu odpowiedzi.",
        "Hej, skąd pochodzi ta odpowiedź?",
        "Dzień dobry. Z jakiego źródła pochodzi Twoja odpowiedź?",
    ],
)
def test_greeting_and_source_are_both_answered_without_model_provenance_claim(question: str) -> None:
    classified = DialogueIntentClassifier().classify(question)
    assert classified.primary_intent == "runtime_source_question"
    result = RuntimeSourceHandler().handle(question, context={"intent": classified.primary_intent})
    assert result.route == "runtime_source"
    assert result.body.startswith("Cześć! ")
    assert "handler runtime_source" in result.body
    assert "Nie oznacza to, że tę odpowiedź wygenerował model językowy" in result.body
    assert result.source_origin_detail == "runtime_source_handler"
    assert "runtime_source_question" in ModelGuidedResponseSynthesizer.PROTECTED_INTENTS


def test_source_only_question_does_not_add_an_unrequested_greeting() -> None:
    result = RuntimeSourceHandler().handle(
        "Z jakiego źródła korzystasz przy tworzeniu odpowiedzi?",
        context={"intent": "runtime_source_question"},
    )
    assert result.body.startswith("Tę informację o pochodzeniu")
    assert not result.body.startswith("Cześć!")


def test_explicit_external_research_is_not_reclassified_as_local_source_explanation() -> None:
    intent = DialogueIntentClassifier().classify(
        "Sprawdź w internecie aktualne informacje i podaj źródła."
    )
    assert intent.primary_intent == "external_research_request"


def test_exact_runtime_quote_path_remains_separate_and_does_not_invent_checkpoint() -> None:
    result = RuntimeSourceHandler().handle(
        "Podaj exact_runtime_text",
        context={"intent": "runtime_exact_quote_request"},
    )
    assert "Nie ma poprzedniego checkpointu" in result.body


@pytest.mark.parametrize(
    ("model_body", "expected"),
    [
        ("🌿 Łatka Cześć!", "Cześć!"),
        ("🌿 Łatka Witaj! Dobrze cię widzieć.", "Witaj! Dobrze cię widzieć."),
        ("🌿 Łatka Hej, co słychać?", "Hej, co słychać?"),
        ("🌿 Łatka 🌿 Łatka Cześć!", "Cześć!"),
        ("🌿 Łatka: Cześć!", "Cześć!"),
        ("🌿 Łatka\n\nCześć!", "Cześć!"),
        ("🕒 2026-11-15 12:34:51\n🌿 Łatka Cześć!", "Cześć!"),
        ("🌿 Łatka wspomina fragment opowiadania.", "🌿 Łatka wspomina fragment opowiadania."),
        ("W tekście pojawia się 🌿 Łatka jako cytat.", "W tekście pojawia się 🌿 Łatka jako cytat."),
    ],
)
def test_only_recognized_model_generated_speaker_labels_are_removed(
    model_body: str, expected: str
) -> None:
    assert clean_model_generated_body(model_body) == expected


def test_runtime_owns_exactly_one_visible_header_after_model_body_cleaning() -> None:
    body = clean_model_generated_body("🌿 Łatka Cześć!")
    envelope = MessageEnvelope.build(
        timestamp_header="🕒 2026-11-15 12:34:51",
        timezone="Europe/Warsaw",
        timestamp_sample_iso="2026-11-15T12:34:51+01:00",
        timestamp_source="local_fallback",
        timestamp_trusted=False,
        author_id="latka_runtime",
        author_label="Łatka",
        author_source="jazn_runtime",
        state_emoticon="🌿",
        body=body,
    )
    rendered = envelope.render()
    assert rendered.count("🌿 Łatka") == 1
    assert rendered.endswith("\n\nCześć!")
    assert envelope.author_source == "jazn_runtime"


def test_no_carryover_history_request_does_not_read_or_invent_a_previous_turn() -> None:
    # A deliberately absent store must not result in a false grounded history.
    report = _with_targeted_session_recall(
        None, "session", "Cześć. Chciałbym porozmawiać.",
        {"turns": [], "total_turn_count": 0}, allow_history=False,
    )
    assert report["turns"] == []
    assert "targeted_recall" not in report
