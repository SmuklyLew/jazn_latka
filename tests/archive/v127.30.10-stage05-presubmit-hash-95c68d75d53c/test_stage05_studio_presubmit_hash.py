"""Bind new Studio checkpoints to the exact canonical submitted user text."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import chat as studio_chat
from tools.jazn_run_studio.core import StudioError
from test_jazn_run_studio_delivery_ack import _client, _accepted
from test_jazn_chat_terminal_recovery import _client as _failure_client, _failed_result, _live_validation


def test_hash_is_persisted_before_transport_write_and_survives_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, core = _client(tmp_path, monkeypatch)
    client.pending = None
    message = "  Test syntetyczny: ąę.  "
    digest = sha256(message.strip().encode("utf-8")).hexdigest()
    written = Event()
    observed = []

    def write(data: bytes) -> None:
        observed.append((json.loads(client.checkpoint.read_text(encoding="utf-8")), json.loads(data)))
        written.set()

    stdin = SimpleNamespace(write=write, flush=lambda: None)
    client.job = SimpleNamespace(proc=SimpleNamespace(poll=lambda: None, stdin=stdin), cancel=Event())
    request = client.send(message)
    assert written.wait(2)
    checkpoint, submitted = observed[0]
    assert checkpoint["request_id"] == request == submitted["request_id"]
    assert checkpoint["user_text_sha256"] == digest
    assert submitted["message"] == message
    assert "Test syntetyczny" not in client.checkpoint.read_text(encoding="utf-8")
    restored = studio_chat.ChatClient(core)
    assert restored.pending == request
    assert restored._pending_user_text_sha256 == digest


@pytest.mark.parametrize("receipt_hash", ["same", "other", "missing"])
def test_bound_checkpoint_rejects_substituted_final_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, receipt_hash: str) -> None:
    client, core = _client(tmp_path, monkeypatch)
    client._pending_user_text_sha256 = "a" * 64
    client._save()
    value = _accepted()
    if receipt_hash != "missing":
        value["user_text_sha256"] = ("a" if receipt_hash == "same" else "b") * 64
    monkeypatch.setattr(studio_chat, "run", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=json.dumps(value).encode()))
    client.receive({"request_id": "studio-turn-1"})
    if receipt_hash == "same":
        assert client._awaiting_gui_ack == client.pending
        client.acknowledge_final("studio-turn-1")
        assert "user_text_sha256" not in json.loads(client.checkpoint.read_text())
        assert client._pending_user_text_sha256 is None
    else:
        assert client._awaiting_gui_ack is None
        assert not any(event[1] == "chat_final" for event in core.recorded_events)
        assert client.pending == "studio-turn-1"
        assert json.loads(client.checkpoint.read_text())["user_text_sha256"] == "a" * 64


@pytest.mark.parametrize("same", [True, False])
def test_bound_checkpoint_requires_matching_independent_failure_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, same: bool) -> None:
    client, _core = _failure_client(tmp_path, monkeypatch)
    client._pending_user_text_sha256 = ("a" if same else "b") * 64
    client._save()
    _live_validation(client, monkeypatch)
    client.receive(_failed_result(client))
    assert client.can_resolve_terminal_failure() is same
    if same:
        client.resolve_terminal_failure("studio-turn-1")
        assert client.pending is None
        assert client._pending_user_text_sha256 is None
    else:
        with pytest.raises(StudioError):
            client.resolve_terminal_failure("studio-turn-1")
        assert client.pending == "studio-turn-1"


def test_corrupt_checkpoint_hash_refuses_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, core = _client(tmp_path, monkeypatch)
    saved = json.loads(client.checkpoint.read_text())
    saved["user_text_sha256"] = "invalid"
    client.checkpoint.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(StudioError, match="hash"):
        studio_chat.ChatClient(core)
