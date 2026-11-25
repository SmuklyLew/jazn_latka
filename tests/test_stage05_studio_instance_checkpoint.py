"""Studio pin binding survives restart and rejects receipts from replacement instances."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import chat as studio_chat
from tools.jazn_run_studio.core import StudioError
from test_jazn_run_studio_delivery_ack import _client, _accepted
from test_jazn_chat_terminal_recovery import _client as _failure_client, _failed_result, _live_validation


@pytest.mark.parametrize("instance", ["original", "replacement", None])
def test_pinned_studio_final_requires_original_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, instance: str | None) -> None:
    client, core = _client(tmp_path, monkeypatch)
    client._pending_daemon_instance_id = "original"
    client._pending_user_text_sha256 = "a" * 64
    client._save()
    client = studio_chat.ChatClient(core)
    value = _accepted()
    value.update(daemon_instance_id=instance, user_text_sha256="a" * 64)
    monkeypatch.setattr(studio_chat, "run", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=json.dumps(value).encode()))
    client.receive({"request_id": "studio-turn-1"})
    if instance == "original":
        assert client._awaiting_gui_ack == client.pending
        client.acknowledge_final("studio-turn-1")
        assert "expected_daemon_instance_id" not in json.loads(client.checkpoint.read_text())
    else:
        assert client._awaiting_gui_ack is None
        assert client.pending == "studio-turn-1"
        assert not any(event[1] == "chat_final" for event in core.recorded_events)


@pytest.mark.parametrize("pin", ["synthetic-instance", "old-instance"])
def test_terminal_failure_receipt_must_match_presubmit_pin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pin: str) -> None:
    client, _core = _failure_client(tmp_path, monkeypatch)
    client._pending_daemon_instance_id = pin
    client._pending_user_text_sha256 = "a" * 64
    client._save()
    _live_validation(client, monkeypatch)
    client.receive(_failed_result(client))
    assert client.can_resolve_terminal_failure() is (pin == "synthetic-instance")
    if pin != "synthetic-instance":
        with pytest.raises(StudioError):
            client.resolve_terminal_failure("studio-turn-1")
        assert client.pending == "studio-turn-1"


@pytest.mark.parametrize("bad", ["", None, 123, "bad pin"])
def test_invalid_persisted_pin_is_not_silently_downgraded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: object) -> None:
    client, core = _client(tmp_path, monkeypatch)
    saved = json.loads(client.checkpoint.read_text())
    saved["user_text_sha256"] = "a" * 64
    saved["expected_daemon_instance_id"] = bad
    client.checkpoint.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(StudioError, match="instancja"):
        studio_chat.ChatClient(core)
