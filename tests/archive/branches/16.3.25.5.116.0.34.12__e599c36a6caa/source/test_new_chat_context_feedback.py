"""Regression: a new chat is context, not a request to open another one."""
from __future__ import annotations

from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.core.operational_self_model import OperationalSelfModel


def test_new_chat_correction_routes_as_feedback_not_package_health() -> None:
    text = "Heh. Coś Ci nie poszło. Nowy czat, a Ty mówisz o jego otwieraniu... Hmm."
    report = DialogueIntentClassifier().classify(text, previous_text="Otwórz nowy czat")
    assert report.primary_intent == "negative_feedback_current_turn", report.to_dict()
    assert report.question_object == "current_turn_feedback"
    assert report.update_request is False


def test_explicit_patch_request_retains_write_route_after_feedback() -> None:
    text = "Coś ci nie poszło. Napraw teraz kod systemu Jaźni na nowym branchu."
    report = DialogueIntentClassifier().classify(text)
    assert report.primary_intent == "system_update_execution_request", report.to_dict()


def test_reply_correction_updates_operational_self_state_without_biology() -> None:
    state = OperationalSelfModel().current_state(
        user_text="Coś Ci nie poszło. Nowy czat, a Ty mówisz o jego otwieraniu."
    )
    assert "korekcie" in state.primary
    assert "błędu" in state.need
    assert "biologiczne" in state.truth_boundary
    assert state.emoticon == "🛠️"
