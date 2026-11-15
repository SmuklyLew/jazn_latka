"""Fail-closed acceptance when canonical session store is not initialized."""
from __future__ import annotations

from latka_jazn.core.conversation_runner import _with_targeted_session_recall
from latka_jazn.core.model_context_compiler import compile_model_context


def test_missing_store_never_provides_unguarded_first_message() -> None:
    history = {
        "session_id": "test-session",
        "turns": [],
        "total_turn_count": 0,
    }
    result = _with_targeted_session_recall(
        None,
        "test-session",
        "Co napisałem w pierwszej wiadomości tej sesji?",
        history,
        allow_history=True,
    )
    assert result["targeted_recall"] == {
        "ok": False,
        "status": "history_unavailable",
    }
    packet = compile_model_context(
        user_text="Co napisałem w pierwszej wiadomości tej sesji?",
        cognitive_frame={"client_context": {"conversation_history": result}},
        nlg_plan={
            "detected_intent": "contextual_continuation_question",
            "memory_policy": "not_needed",
            "source_policy": "runtime_only",
        },
        thought_frame={},
        response_policy={},
    ).to_dict()
    assert packet["conversation_history"]["targeted_recall"] == {"status": "history_unavailable"}
    assert packet["allowed_memory_items"] == []


def test_missing_store_does_not_perturb_an_unrelated_turn() -> None:
    history = {"session_id": "test-session", "turns": [], "total_turn_count": 0}
    assert _with_targeted_session_recall(
        None, "test-session", "Cześć!", history, allow_history=True,
    ) is history


def test_disabled_history_has_priority_over_absent_store() -> None:
    result = _with_targeted_session_recall(
        None, "test-session", "Czy pamiętasz moją pierwszą wiadomość w tej sesji?",
        {"session_id": "test-session", "turns": []},
        allow_history=False,
    )
    assert result["targeted_recall"]["status"] == "history_disabled"
