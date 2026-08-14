from __future__ import annotations

from latka_jazn.nlp.control_text import extract_intent_control_text
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


SONG_WITH_VOICE_WORDS = '''To jej pomóż. Tak jak powinieneś.

„Jeszcze jeden świt”

[Zwrotka 1]
Noc położyła dłonie na dachach,
a wiatr poplątał ścieżki i kurz.
Zostało kilka słów po rozmowach,
których nie umiał unieść już głos.

[Refren]
Jeszcze jeden świt,
jeszcze jeden krok,
choćby cały świat
zgubił własny głos.
Jeszcze jedna nić,
co prowadzi nas.
'''


def test_structured_song_is_removed_from_control_text_not_from_original() -> None:
    report = extract_intent_control_text(SONG_WITH_VOICE_WORDS)
    assert "własny głos" not in report.control_text
    assert "To jej pomóż" in report.control_text
    assert report.original_text == SONG_WITH_VOICE_WORDS
    assert report.masked_span_count >= 2


def test_structured_song_words_do_not_trigger_voice_or_identity_diagnostic() -> None:
    report = DialogueIntentClassifier().classify(SONG_WITH_VOICE_WORDS)
    assert report.primary_intent == "creative_text_analysis"
    assert report.creative_material_present is True
    assert report.diagnostic_request is False


def test_explicit_voice_perspective_bug_still_routes_to_diagnostic() -> None:
    report = DialogueIntentClassifier().classify(
        "Dlaczego mówisz o sobie w trzeciej osobie jako Łatka?"
    )
    assert report.primary_intent == "voice_perspective_diagnostic_request"
    assert report.diagnostic_request is True


def test_creative_research_is_compound_not_plain_external_research() -> None:
    message = '''@Wyszukiwanie w sieci Wracając do piosenki.

„Jeszcze jeden świt”
[Zwrotka 1]
Noc położyła dłonie na dachach.
[Refren]
Choćby cały świat zgubił własny głos.

-----
Popatrz, jak znane wokalistki pisały teksty i oceń ten utwór.
'''
    report = DialogueIntentClassifier().classify(message)
    assert report.primary_intent == "creative_text_analysis"
    assert "external_research_request" in report.secondary_intents
    assert report.creative_material_present is True
    assert report.diagnostic_request is False


def test_system_patch_request_with_embedded_lyrics_remains_system_update() -> None:
    message = '''Przygotuj patch klasyfikatora, który naprawi ten błąd.
[Refren]
Choćby cały świat zgubił własny głos.
'''
    report = DialogueIntentClassifier().classify(message)
    assert report.primary_intent == "system_update_execution_request"
