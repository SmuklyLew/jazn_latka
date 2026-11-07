"""Read-only chat activity and opt-in transport history in the JSS GUI.

These are synthetic Qt tests: they do not generate an Ollama answer, start a
daemon, clear MEMORY, or acknowledge an unaccepted runtime result.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from tests.test_jazn_run_studio_layout import window  # noqa: F401


class FakeChat:
    def __init__(self) -> None:
        self.pending: str | None = None
        self.sent: list[str] = []
        self.resumes = 0
        self.acknowledged: list[str] = []
        self.terminal_failure = False

    def send(self, text: str) -> str:
        if self.pending:
            raise AssertionError("a second send would be an unwanted replay")
        self.sent.append(text)
        self.pending = "studio-turn-synthetic"
        return self.pending

    def resume(self) -> None:
        self.resumes += 1

    def can_resolve_terminal_failure(self) -> bool:
        return self.terminal_failure

    def acknowledge_final(self, request_id: str) -> None:
        if request_id != self.pending:
            raise AssertionError("wrong request")
        self.acknowledged.append(request_id)
        self.pending = None


def _sent_window(window):
    fake = FakeChat()
    window.core.chat = fake
    window.message.setPlainText("Testowa wiadomość bez prywatnych danych.")
    window.send_chat()
    return fake


def test_transport_identifiers_live_only_in_closed_history(window) -> None:
    fake = _sent_window(window)
    assert fake.pending == "studio-turn-synthetic"
    assert window.chat_history_panel.isHidden()
    assert "Oczekiwanie na wynik: studio-turn-synthetic" in window.chat_state.text()
    assert "studio-turn-synthetic" in window.chat_operation_history.toPlainText()
    assert "studio-turn-synthetic" not in window.chat_activity.text()
    assert "studio-turn-synthetic" not in window.conversation.toPlainText()
    assert "Jaźń obsługuje" in window.chat_activity.text()
    assert window.chat_activity_timer.isActive()
    assert not window.send_button.isEnabled()
    window.chat_history_toggle.setChecked(True)
    assert not window.chat_history_panel.isHidden()
    assert "studio-turn-synthetic" in window.chat_state.text()


def test_activity_animates_without_manufacturing_an_answer(window) -> None:
    _sent_window(window)
    original = window.conversation.toPlainText()
    before = window.chat_activity.text()
    window._animate_chat_activity()
    after = window.chat_activity.text()
    assert before != after
    assert window.conversation.toPlainText() == original
    assert "Łatka" not in after


def test_accepted_result_stops_animation_only_after_gui_append_and_ack(window) -> None:
    fake = _sent_window(window)
    accepted = {
        "request_id": "studio-turn-synthetic",
        "text": "Zaakceptowana syntetyczna odpowiedź.",
        "turn_id": "synthetic-turn-1",
        "trace_id": "synthetic-trace-1",
    }
    assert "Zaakceptowana syntetyczna odpowiedź" not in window.conversation.toPlainText()
    window.core.emit("chat", "chat_final", accepted)
    window.poll()
    assert "Zaakceptowana syntetyczna odpowiedź." in window.conversation.toPlainText()
    assert fake.acknowledged == ["studio-turn-synthetic"]
    assert not window.chat_activity_timer.isActive()
    assert window.chat_activity.isHidden()
    assert window.send_button.isEnabled()
    assert "synthetic-turn-1" in window.chat_operation_history.toPlainText()
    assert window.chat_history_panel.isHidden()


def test_terminal_error_stops_spinner_but_preserves_request(window) -> None:
    fake = _sent_window(window)
    fake.terminal_failure = True
    window.core.emit(
        "chat", "chat_state",
        "Potwierdzona nieudana tura: runtime_turn_not_accepted. "
        "Bez ponawiania wiadomości możesz wybrać Zamknij nieudaną turę.",
    )
    window.poll()
    assert fake.pending == "studio-turn-synthetic"
    assert fake.sent == ["Testowa wiadomość bez prywatnych danych."]
    assert not window.chat_activity_timer.isActive()
    # The live error points to the opted-in technical log; keep the natural
    # Polish declension ("w Historii operacji") as a strict UI regression.
    assert "Historii operacji" in window.chat_activity.text()
    assert not window.send_button.isEnabled()
    assert "runtime_turn_not_accepted" in window.chat_operation_history.toPlainText()
    assert "runtime_turn_not_accepted" not in window.conversation.toPlainText()


def test_transport_failure_and_resume_do_not_replay(window) -> None:
    fake = _sent_window(window)
    window.core.emit(
        "chat", "chat_state",
        "Transport zamknięty. Nierozstrzygnięte żądanie zachowano do wznowienia.",
    )
    window.poll()
    assert not window.chat_activity_timer.isActive()
    assert fake.pending == "studio-turn-synthetic"
    assert not window.send_button.isEnabled()

    window.resume_chat()
    assert fake.resumes == 1
    assert fake.sent == ["Testowa wiadomość bez prywatnych danych."]
    assert window.chat_activity_timer.isActive()
    assert "Sprawdzanie poprzedniego wyniku" in window.chat_activity.text()
    window.core.emit("chat:resume", "state", {
        "state": "failed", "error": "resume_exit:1", "pid": None,
    })
    window.poll()
    assert not window.chat_activity_timer.isActive()
    assert "Transport przerwany" in window.chat_activity.text()
    assert fake.pending == "studio-turn-synthetic"
