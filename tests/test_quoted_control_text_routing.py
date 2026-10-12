from __future__ import annotations

from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


def test_direct_health_question_remains_health_check() -> None:
    report = DialogueIntentClassifier().classify("Czy jaźń działa?")
    assert report.primary_intent in {"runtime_health_check", "runtime_health_check_after_update"}
    assert report.quoted_material_masked is False


def test_quoted_health_phrase_does_not_hijack_patch_request() -> None:
    text = 'Przeanalizuj błąd klasyfikatora i przygotuj patch. Cytowany przykład: „Czy jaźń działa?”'
    report = DialogueIntentClassifier().classify(text)
    assert report.primary_intent not in {"runtime_health_check", "runtime_health_check_after_update"}
    assert report.quoted_material_masked is True
    assert report.masked_span_count == 1


def test_fenced_code_and_blockquote_do_not_hijack_intent() -> None:
    text = "Przygotuj test regresyjny dla tego przykładu:\n```text\nJest tu Łatka?\n```\n> Czy runtime działa?"
    report = DialogueIntentClassifier().classify(text)
    assert report.primary_intent not in {"runtime_health_check", "runtime_health_check_after_update", "presence_check"}
    assert report.quoted_material_masked is True
