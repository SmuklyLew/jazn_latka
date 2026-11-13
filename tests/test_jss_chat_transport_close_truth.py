"""JSS transport diagnostics must not fabricate an unresolved request.

These tests exercise operator-visible emissions without spawning a daemon,
modifying a checkpoint, or changing accepted turn/finalization contracts.
"""
from __future__ import annotations

from threading import RLock
from types import SimpleNamespace
from typing import cast

import pytest

from tools.jazn_run_studio.chat import ChatClient
from tools.jazn_run_studio.core import Controller


def _client(pending: str | None = None, *, awaiting_ack: str | None = None):
    events: list[tuple[str, str, str]] = []
    core = SimpleNamespace(
        emit=lambda key, kind, value: events.append((key, kind, value)),
    )
    client = ChatClient.__new__(ChatClient)
    # The typed stub implements only emit(), which is all these notices use.
    client.core = cast(Controller, core)
    client.lock = RLock()
    client.pending = pending
    client._awaiting_gui_ack = awaiting_ack
    return client, events


def test_clean_disconnect_with_no_pending_turn_does_not_claim_resume() -> None:
    client, events = _client()
    client._emit_transport_closed(failed=False)
    assert events == [
        ("chat", "chat_state",
         "Transport zamknięty. Brak nierozstrzygniętego żądania w tej sesji.")
    ]
    assert client.pending is None


def test_unexpected_transport_exit_without_request_reports_error_not_resumable() -> None:
    client, events = _client()
    client._emit_transport_closed(failed=True)
    assert len(events) == 1
    assert events[0][:2] == ("chat", "chat_state")
    assert "z błędem" in events[0][2]
    assert "Brak oczekującego żądania" in events[0][2]
    assert "Nierozstrzygnięte żądanie zachowano" not in events[0][2]


def test_disconnect_with_pending_request_preserves_resume_instruction() -> None:
    request = "studio-turn-0001"
    client, events = _client(request)
    client._emit_transport_closed(failed=False)
    assert events == [
        ("chat", "chat_state",
         "Transport zamknięty. Nierozstrzygnięte żądanie zachowano do wznowienia.")
    ]
    assert client.pending == request


def test_disconnect_awaiting_gui_ack_does_not_claim_unaccepted_turn() -> None:
    request = "studio-turn-0002"
    client, events = _client(request, awaiting_ack=request)
    client._emit_transport_closed(failed=False)
    assert len(events) == 1
    assert "Zaakceptowany wynik oczekuje" in events[0][2]
    assert "zachowano request_id" in events[0][2]
    assert "do wznowienia" not in events[0][2]
    assert client.pending == request
    assert client._awaiting_gui_ack == request


@pytest.mark.parametrize("pending", [None, "studio-turn-0003"])
def test_protocol_error_only_suggests_resume_if_request_exists(pending: str | None) -> None:
    client, events = _client(pending)
    client._emit_transport_protocol_error()
    assert len(events) == 1
    assert events[0][:2] == ("chat", "chat_state")
    if pending:
        assert "Zachowano request_id; użyj Wznów wynik" in events[0][2]
    else:
        assert "Brak request_id do wznowienia" in events[0][2]
        assert "użyj Wznów wynik" not in events[0][2]
    assert client.pending == pending
