"""Pending accepted GUI finals retain their durable request until explicit delivery ACK."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import chat as studio_chat
from tools.jazn_run_studio.core import StudioError


class _Core:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.settings = SimpleNamespace()
        self.events: list[tuple[str, str, dict]] = []

    def emit(self, key: str, kind: str, result: dict) -> None:
        self.events.append((key, kind, result))


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[studio_chat.ChatClient, _Core]:
    monkeypatch.setattr(studio_chat, "settings_path", lambda _root: tmp_path / "settings.json")
    monkeypatch.setattr(studio_chat, "python_executable", lambda _settings: "python")
    core = _Core(tmp_path)
    client = studio_chat.ChatClient(core)
    client.pending = "studio-turn-1"
    client._save()
    return client, core


def _accepted() -> dict:
    return {"accepted": True, "text": "test visible result",
            "request_id": "studio-turn-1", "session_id": "local",
            "turn_id": "turn-1", "trace_id": "trace-1"}


def _validation(monkeypatch: pytest.MonkeyPatch, *, accepted: bool = True) -> None:
    def fake_run(*_args, **_kwargs):
        payload = _accepted() if accepted else {"accepted": False, "error": "invalid"}
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode("utf-8"))
    monkeypatch.setattr(studio_chat, "run", fake_run)


def test_accepted_final_remains_pending_until_gui_ack_and_is_not_emitted_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, core = _client(tmp_path, monkeypatch)
    _validation(monkeypatch)
    client.receive({"request_id": "studio-turn-1"})
    assert client.pending == "studio-turn-1"
    assert json.loads(client.checkpoint.read_text())["request_id"] == "studio-turn-1"
    assert len(core.events) == 1 and core.events[0][1] == "chat_final"
    client.receive({"request_id": "studio-turn-1"})
    assert len(core.events) == 1
    with pytest.raises(StudioError):
        client.acknowledge_final("studio-turn-wrong")
    client.acknowledge_final("studio-turn-1")
    assert json.loads(client.checkpoint.read_text())["request_id"] is None
    assert client.pending is None


def test_checkpoint_failure_preserves_pending_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _core = _client(tmp_path, monkeypatch)
    _validation(monkeypatch)
    client.receive({"request_id": "studio-turn-1"})
    monkeypatch.setattr(client, "_save", lambda: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        client.acknowledge_final("studio-turn-1")
    assert client.pending == "studio-turn-1"
    assert json.loads(client.checkpoint.read_text())["request_id"] == "studio-turn-1"


def test_unaccepted_transport_result_stays_pending_without_gui_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, core = _client(tmp_path, monkeypatch)
    _validation(monkeypatch, accepted=False)
    client.receive({"request_id": "studio-turn-1"})
    assert client.pending == "studio-turn-1"
    assert not any(event[1] == "chat_final" for event in core.events)


def test_restart_reloads_pending_request_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, core = _client(tmp_path, monkeypatch)
    _validation(monkeypatch)
    client.receive({"request_id": "studio-turn-1"})
    restarted = studio_chat.ChatClient(core)
    assert restarted.pending == "studio-turn-1"
    assert restarted._awaiting_gui_ack is None
