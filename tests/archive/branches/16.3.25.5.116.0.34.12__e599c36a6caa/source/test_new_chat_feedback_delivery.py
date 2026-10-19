"""P0B/P2 accepted fallback: specific correction is not a generic debug apology."""
from __future__ import annotations

from latka_jazn.core.handlers.ordinary_dialogue_handler import OrdinaryDialogueHandler
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


def test_new_chat_correction_reaches_specific_ordinary_response() -> None:
    """A new-chat mistake must acknowledge that the chat already exists."""
    text = "Coś ci nie poszło. Nowy czat, a Ty mówisz o jego otwieraniu."
    intent = DialogueIntentClassifier().classify(text).primary_intent
    assert intent == "negative_feedback_current_turn"
    output = OrdinaryDialogueHandler().handle(text, {"intent": intent})
    assert "już w nowym czacie" in output.body
    assert "otwarcie" in output.body
    assert "Cofam ten szablon" not in output.body


def test_new_chat_correction_structured_candidate_carries_specific_constraint() -> None:
    """Host LLM cutover must retain correction context in its candidate plan."""
    text = "Nowy czat, a Ty mówisz o jego otwieraniu."
    result = OrdinaryDialogueHandler().handle(text, {
        "intent": "negative_feedback_current_turn",
        "canonical_dialogue_cutover": True,
    })
    constraints = result.data["response_candidate"]["constraints"]
    assert "acknowledge_chat_already_open_do_not_suggest_new_chat" in constraints
    assert result.body == ""
