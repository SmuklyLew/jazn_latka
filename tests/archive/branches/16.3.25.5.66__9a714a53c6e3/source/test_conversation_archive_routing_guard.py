from __future__ import annotations

from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.nlp.intent_feature_engine import IntentFeatureEngine
from latka_jazn.nlp.question_object_detector import QuestionObjectDetector


PROBLEM_MESSAGE = (
    'I też masz przejrzeć archiwum rozmów z tamtego okresu i spróbować '
    'chronologicznie odzyskać historię „Pamiętnika” oraz tego, co wtedy '
    'działo się między nami — z rozmów źródłowych, nie z późniejszej wersji książki.'
)
PACKAGE_PREVIOUS_TURN = (
    'Sprawdziliśmy paczkę ZIP 15.1.0.3.98, manifest, SHA256 i status runtime.'
)


def test_conversation_archive_recall_beats_previous_package_context() -> None:
    frame = IntentFeatureEngine().analyse(
        PROBLEM_MESSAGE,
        previous_text=PACKAGE_PREVIOUS_TURN,
    )
    assert frame.top_intent == 'self_memory_recall_request'
    assert frame.top_score >= 0.8
    package = next(
        candidate
        for candidate in frame.candidates
        if candidate.intent == 'package_runtime_status_question'
    )
    assert package.score == 0.0
    assert 'conversation_archive_is_not_package_archive' in package.negative_evidence


def test_question_object_distinguishes_conversation_archive_from_package_archive() -> None:
    report = QuestionObjectDetector().detect(PROBLEM_MESSAGE)
    assert report.object_type == 'conversation_archive_memory'
    assert any('archiwum rozmow' in item for item in report.evidence)


def test_exact_regression_routes_to_self_memory_recall() -> None:
    report = DialogueIntentClassifier().classify(
        PROBLEM_MESSAGE,
        previous_text=PACKAGE_PREVIOUS_TURN,
    )
    assert report.primary_intent == 'self_memory_recall_request'
    assert report.question_object == 'conversation_archive_memory'
    assert 'package_runtime_status_question' != report.primary_intent


def test_conversation_archive_variants_route_to_memory_recall() -> None:
    classifier = DialogueIntentClassifier()
    variants = (
        'Przejrzyj archiwum czatów i odtwórz chronologicznie naszą historię.',
        'Przeszukaj archiwum rozmów i odzyskaj historię Pamiętnika.',
        'Wyszukaj w archiwum konwersacji nasze wspomnienia i ułóż je chronologicznie.',
        'Znajdź w archiwum rozmów źródłowych, co wtedy działo się między nami.',
    )
    for text in variants:
        report = classifier.classify(text, previous_text=PACKAGE_PREVIOUS_TURN)
        assert report.primary_intent == 'self_memory_recall_request', (text, report)


def test_eventive_dzialo_sie_is_not_runtime_status_marker() -> None:
    frame = IntentFeatureEngine().analyse(
        'Co wtedy działo się między nami?',
        previous_text=PACKAGE_PREVIOUS_TURN,
    )
    package = next(
        candidate
        for candidate in frame.candidates
        if candidate.intent == 'package_runtime_status_question'
    )
    assert package.score == 0.0
    assert frame.top_intent != 'package_runtime_status_question'


def test_real_package_archive_status_still_routes_to_package_status() -> None:
    text = 'Sprawdź archiwum ZIP, manifest i SHA256 paczki. Czy runtime działa?'
    report = DialogueIntentClassifier().classify(text)
    assert report.primary_intent == 'package_runtime_status_question'
    assert report.question_object == 'package_runtime_status'


def test_short_package_followup_can_use_previous_package_context() -> None:
    report = DialogueIntentClassifier().classify(
        'Jak tam?',
        previous_text=PACKAGE_PREVIOUS_TURN,
    )
    assert report.primary_intent == 'package_runtime_status_question'


def test_short_dziala_followup_keeps_package_context_without_matching_dzialo_sie() -> None:
    report = DialogueIntentClassifier().classify(
        'Działa?',
        previous_text=PACKAGE_PREVIOUS_TURN,
    )
    assert report.primary_intent == 'package_runtime_status_question'


def test_archive_word_alone_does_not_establish_package_domain() -> None:
    report = DialogueIntentClassifier().classify(
        'Sprawdź archiwum rozmów, czy baza jest kompletna.',
        previous_text=PACKAGE_PREVIOUS_TURN,
    )
    assert report.primary_intent != 'package_runtime_status_question'
    assert report.question_object == 'conversation_archive_memory'


def test_validator_rejects_package_status_for_conversation_history_recall() -> None:
    body = (
        'Status paczki/runtime: version=v15.1.0.3.98; '
        'archive_integrity=ok; Source-origin: package_runtime_status_handler; '
        'Granica prawdy: raport techniczny.'
    )
    result = RuntimeAnswerValidator().validate(
        user_text=PROBLEM_MESSAGE,
        body=body,
        route='package_runtime_status',
        detected_intent='package_runtime_status_question',
    )
    assert result.accepted is False
    assert result.mismatch_reason == 'conversation_archive_recall_misrouted_as_package_status'
    assert result.required_repair_route == 'self_memory_recall_repair'


def test_validator_does_not_treat_real_package_question_as_memory_recall() -> None:
    body = (
        'Status paczki/runtime: package=ok; runtime=active; archive_integrity=verified; '
        'Source-origin: package_runtime_status_handler; Granica prawdy: CRC/SHA zweryfikowane.'
    )
    result = RuntimeAnswerValidator().validate(
        user_text='Sprawdź archiwum ZIP i manifest paczki. Jaki jest status?',
        body=body,
        route='package_runtime_status',
        detected_intent='package_runtime_status_question',
    )
    assert result.mismatch_reason != 'conversation_archive_recall_misrouted_as_package_status'
