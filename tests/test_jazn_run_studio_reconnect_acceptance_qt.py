"""Regression for Studio reconnect, GUI final ACK and pinned daemon identity.

Synthetic GUI tests. These do NOT assert a real Ollama turn or service readiness.
"""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from tools.jazn_run_studio.chat import ChatClient
from tools.jazn_run_studio.core import Settings, StudioError
from tests.test_jazn_run_studio_layout import window


def test_invalid_route_does_not_reserve_chat_job(window) -> None:
    core = window.core
    core.settings = replace(core.settings, model="gemma3:latest",
                            daemon_url="http://127.0.0.1:8879")
    client = ChatClient(core)
    core.chat = client
    core.settings = replace(core.settings, daemon_url="http://127.0.0.1:8787")
    with pytest.raises(StudioError, match="Zmieniono endpoint"):
        client.connect()
    assert "chat" not in core.jobs
    assert client.job is None
    assert client.pending is None
    # Correcting the configuration must not leave a poisoned reservation.
    core.settings = replace(core.settings, daemon_url="http://127.0.0.1:8879")
    assert client.connection_command()[client.connection_command().index("--daemon-port") + 1] == "8879"


def test_qt_final_is_acked_only_after_display_and_reconnect_checkpoint(window) -> None:
    core = window.core
    core.settings = replace(core.settings, model="gemma3:latest",
                            daemon_url="http://127.0.0.1:8879")
    first = ChatClient(core)
    core.chat = first
    session_id = first.session_id
    first.pending = "studio-turn-test01"
    first._save()
    # Reloading the checkpoint represents a new GUI transport, not another user turn.
    reconnected = ChatClient(core)
    assert reconnected.session_id == session_id
    assert reconnected.pending == "studio-turn-test01"
    assert reconnected.resume_command("studio-turn-test01")[-1] == "8879"
    core.chat = reconnected
    reconnected._awaiting_gui_ack = "studio-turn-test01"
    accepted = {"request_id": "studio-turn-test01",
                "text": "Accepted synthetic final", "turn_id": "synthetic-turn-1",
                "trace_id": "synthetic-trace-1"}
    assert "Accepted synthetic final" not in window.conversation.toPlainText()
    core.emit("chat", "chat_final", accepted)
    window.poll()
    assert window.conversation.toPlainText().count("Accepted synthetic final") == 1
    assert reconnected.pending is None
    assert json.loads(reconnected.checkpoint.read_text(encoding="utf-8"))["request_id"] is None
    assert "synthetic-turn-1" in window.chat_state.text()


def test_pending_route_change_refuses_wrong_daemon_after_reconnect(window) -> None:
    core = window.core
    core.settings = replace(core.settings, model="gemma3:latest",
                            daemon_url="http://127.0.0.1:8879")
    first = ChatClient(core)
    first.pending = "studio-turn-pending01"
    first._save()
    core.settings = replace(core.settings, daemon_url="http://127.0.0.1:8787")
    with pytest.raises(StudioError, match="Checkpoint"):
        ChatClient(core)
    assert first.pending == "studio-turn-pending01"
    assert json.loads(first.checkpoint.read_text(encoding="utf-8"))["daemon_url"] == "http://127.0.0.1:8879"
