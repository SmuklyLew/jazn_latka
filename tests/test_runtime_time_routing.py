import pytest

from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.handlers.time_awareness_handler import TimeAwarenessHandler
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer

@pytest.mark.parametrize("question", [
    "Która jest teraz godzina w Polsce? Podaj aktualny czas runtime.",
    "Która jest godzina?",
    "Jaka jest godzina w Polsce?",
    "Podaj aktualny czas runtime.",
    "Jaka teraz jest godzina?",
    "Jaka jest teraz godzina?",
    "Podaj bieżący czas.",
    "Która godzina?",
])
def test_time_route(question):
    intent = DialogueIntentClassifier().classify(question).primary_intent
    entry = RouteRegistry().resolve(intent)
    assert entry.route == "time_awareness"
    assert entry.handler_name == "TimeAwarenessHandler"

@pytest.mark.parametrize("question", [
    "Jak zbudowano klasyfikator języka polskiego?",
    "Napisz wiersz o zegarze.",
])
def test_unrelated_route(question):
    intent = DialogueIntentClassifier().classify(question).primary_intent
    entry = RouteRegistry().resolve(intent)
    assert entry.handler_name != "TimeAwarenessHandler"

def test_legacy_intent():
    entry = RouteRegistry().resolve("current_time_question")
    assert entry.handler_name == "TimeAwarenessHandler"
    assert "current_time_question" in TimeAwarenessHandler.handled_intents

def test_protected_intents():
    protected = ModelGuidedResponseSynthesizer.PROTECTED_INTENTS
    assert "current_time_question" in protected
    assert "time_awareness_question" in protected
