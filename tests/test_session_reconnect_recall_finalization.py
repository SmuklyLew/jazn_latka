from __future__ import annotations

import io

import pytest

from latka_jazn.core.conversation_state_store import ConversationStateStore
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.core.handlers.ordinary_dialogue_handler import OrdinaryDialogueHandler
from latka_jazn.core.memory_intent_contract import (
    analyze_memory_intent,
    is_session_dialogue_reference,
)
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.runtime_chat import LatkaRuntimeShell
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


RECONNECT_QUESTION = (
    "Po ponownym połączeniu przypomnij mi liczbę testową "
    "z naszej wcześniejszej rozmowy. Odpowiedz tylko liczbą."
)


@pytest.mark.parametrize("question", [
    RECONNECT_QUESTION,
    "Jaką liczbę podałem w poprzedniej wiadomości? Odpowiedz krótko.",
    "Przypomnij mi hasło zapisane w tej rozmowie.",
])
def test_same_session_question_is_not_autobiographical_recall(question: str) -> None:
    semantics = analyze_memory_intent(question)
    result = DialogueIntentClassifier().classify(
        question,
        previous_text="Moja liczba testowa to 47.",
        carryover_allowed=True,
        conversation_history_available=True,
    )
    route = RouteRegistry().resolve(result.primary_intent)
    assert is_session_dialogue_reference(question)
    assert semantics.content_requested is False
    assert result.primary_intent == "contextual_continuation_question"
    assert route.handler_name == "OrdinaryDialogueHandler"
    assert "accepted_session_history_available" in result.evidence


@pytest.mark.parametrize("question", [
    "Przypomnij mi, co pamiętasz z 2025 roku.",
    "Powspominaj nasz spacer w czerwcu 2025.",
    "Przypomnij mi hasło z wczorajszej rozmowy.",
])
def test_historical_requests_stay_with_memory_policy(question: str) -> None:
    assert not is_session_dialogue_reference(question)
    assert analyze_memory_intent(question).content_requested is True


def test_reconnect_recovers_two_accepted_turns_without_memory(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "isolated_workspace"))
    session = "v1273-reconnect-47"
    initial = ConversationStateStore(tmp_path)
    assert initial.append_finalized_turn(
        session_id=session, turn_id="first", trace_id="trace-one",
        user_text="Moja liczba testowa to 47.",
        assistant_text="Rozumiem, liczba 47.", source="test",
    )["ok"]
    assert initial.append_finalized_turn(
        session_id=session, turn_id="second", trace_id="trace-two",
        user_text="Jaką liczbę podałem w poprzedniej wiadomości?",
        assistant_text="47.", source="test",
    )["ok"]

    reconnected = ConversationStateStore(tmp_path)
    projection = reconnected.load_context_projection(session)
    assert projection["total_turn_count"] == 2
    assert projection["invalid_record_count"] == 0
    assert any("47" in turn["user_text"] for turn in projection["turns"])
    result = DialogueIntentClassifier().classify(
        RECONNECT_QUESTION,
        previous_text=projection["turns"][-1]["user_text"],
        carryover_allowed=True,
        conversation_history_available=projection["selected_turn_count"] > 0,
    )
    assert result.primary_intent == "contextual_continuation_question"
    assert "accepted_session_history_available" in result.evidence


def _accepted(text: str) -> dict:
    return {
        "ok": True, "answer_ok": True,
        "execution_state": "final_visible_answer",
        "host_finalization_pending": False,
        "final_visible_text": text,
        "final_visible_integrity": {
            "valid": True, "consensus": True,
            "text_sha256": sha256_host_visible_text(text),
        },
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": True},
        "final_response_contract": {"author_source": "jazn_runtime"},
    }


class _FakeDaemonClient:
    persistent_runtime_owner = "daemon"
    runtime_turn_timeout_managed = True

    def __init__(self, result: dict) -> None:
        self.result = result
        self.inputs: list[tuple[str, dict]] = []

    def process_user_text(self, user_text: str, **kwargs) -> dict:
        self.inputs.append((user_text, kwargs))
        return dict(self.result)


def test_terminal_never_displays_rejected_final_as_latka() -> None:
    fake = _FakeDaemonClient({
        **_accepted("NIEZATWIERDZONA ODPOWIEDŹ ŁATKI"),
        "ok": False, "answer_ok": False,
        "execution_state": "rejected",
        "error_code": "runtime_turn_not_accepted",
    })
    output = io.StringIO()
    shell = LatkaRuntimeShell(fake, stdin=io.StringIO(), stdout=output, session_id="reconnect")
    shell._handle_default("Przypomnij liczbę.")
    assert "NIEZATWIERDZONA ODPOWIEDŹ ŁATKI" not in output.getvalue()
    assert "local_runtime_final_not_accepted" in output.getvalue()
    assert shell._last_user_text is None
    assert shell._last_visible_text is None


def test_terminal_displays_only_hash_validated_accepted_final() -> None:
    visible = "🕒 2026-11-10 18:01:55\n🌿 Łatka\n\n47."
    fake = _FakeDaemonClient(_accepted(visible))
    output = io.StringIO()
    shell = LatkaRuntimeShell(fake, stdin=io.StringIO(), stdout=output, session_id="reconnect")
    shell._handle_default("Jaką liczbę podałem wcześniej?")
    assert visible in output.getvalue()
    assert shell._last_user_text == "Jaką liczbę podałem wcześniej?"
    assert shell._last_visible_text == visible


def test_grounded_session_dialogue_candidate_uses_prior_turns_not_autobiography() -> None:
    history = {
        "selected_turn_count": 2,
        "turns": [
            {"user_text": "Moja liczba testowa to 47.", "assistant_text": "Rozumiem."},
            {"user_text": "Jaka byla liczba?", "assistant_text": "47."},
        ],
    }
    result = OrdinaryDialogueHandler().handle(
        RECONNECT_QUESTION,
        {
            "intent": "contextual_continuation_question",
            "canonical_dialogue_cutover": True,
            "route_entry": {"route": "ordinary_dialogue"},
            "conversation_history": history,
        },
    )
    constraints = result.data["response_candidate"]["constraints"]
    assert "use_only_accepted_current_session_turns" in constraints
    assert "do_not_treat_conversation_history_as_autobiographical_memory" in constraints
    assert "current_turn_only" not in constraints
    assert "accepted_session_context_empty" not in constraints


def test_missing_session_history_is_not_silently_treated_as_evidence() -> None:
    result = OrdinaryDialogueHandler().handle(
        RECONNECT_QUESTION,
        {
            "intent": "contextual_continuation_question",
            "canonical_dialogue_cutover": True,
            "route_entry": {"route": "ordinary_dialogue"},
            "conversation_history": {"turns": [], "selected_turn_count": 0},
        },
    )
    constraints = result.data["response_candidate"]["constraints"]
    assert "accepted_session_context_empty" in constraints
    assert "if_prior_message_missing_disclose_unavailable_without_guessing" in constraints


def test_terminal_never_rewrites_hash_accepted_duplicate_into_latka_voice() -> None:
    visible = "🕒 2026-11-10 18:01:55\n🌿 Łatka\n\n47."
    fake = _FakeDaemonClient(_accepted(visible))
    output = io.StringIO()
    shell = LatkaRuntimeShell(fake, stdin=io.StringIO(), stdout=output, session_id="reconnect")
    shell._handle_default("Pierwsza wiadomosc")
    shell._handle_default("Druga wiadomosc")
    assert output.getvalue().count(visible) == 1
    assert "[runtime_turn_display_blocked] repeated_accepted_final" in output.getvalue()
    assert shell._last_user_text == "Pierwsza wiadomosc"
