"""TTL recovery and explicit local-chat failure acknowledgement, without replay."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from tools.jazn_run_studio import chat as studio_chat
from tools.jazn_run_studio.core import Settings, StudioError


class _Core:
    def __init__(self, root: Path):
        self.root = root
        self.settings = Settings()
        self.events: list[tuple[str, str, Any]] = []

    def emit(self, key: str, kind: str, value: Any) -> None:
        self.events.append((key, kind, value))


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[studio_chat.ChatClient, _Core]:
    monkeypatch.setattr(studio_chat, "settings_path", lambda _root: tmp_path / "settings.json")
    core = _Core(tmp_path)
    client = studio_chat.ChatClient(core)  # type: ignore[arg-type]
    client.pending = "studio-turn-1"
    client._save()
    return client, core


def _failed_result(client: studio_chat.ChatClient, *, request_id: str = "studio-turn-1") -> dict[str, Any]:
    return {
        "ok": False, "request_id": request_id, "session_id": client.session_id,
        "job_status": "failed", "done": True, "phase_result_ready": False,
        "completed_at_utc": "2026-11-05T22:49:52+00:00",
        "result": {"ok": False, "error_code": "runtime_turn_not_accepted", "request_id": request_id},
    }


def test_only_verified_terminal_failure_can_be_archived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, core = _client(tmp_path, monkeypatch)
    client.receive(_failed_result(client))
    assert client.can_resolve_terminal_failure()
    assert not any(kind == "chat_final" for _key, kind, _value in core.events)
    client.resolve_terminal_failure("studio-turn-1")
    assert client.pending is None
    assert json.loads(client.checkpoint.read_text(encoding="utf-8"))["request_id"] is None
    archive = json.loads((tmp_path / "chat-terminal-failure-studio-turn-1.json").read_text(encoding="utf-8"))
    assert archive["accepted_finalization_claimed"] is False
    assert archive["automatic_replay_performed"] is False
    assert archive["contains_user_text"] is False
    assert archive["request_id"] == "studio-turn-1"


@pytest.mark.parametrize("changed", [
    "session_id", "request_id", "job_status", "done", "host_turn_id",
])
def test_inconsistent_failure_proof_never_unblocks_chat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str,
) -> None:
    client, _core = _client(tmp_path, monkeypatch)
    value = _failed_result(client)
    value[changed] = {
        "session_id": "other-session", "request_id": "other-request",
        "job_status": "running", "done": False, "host_turn_id": "host-turn",
    }[changed]
    client.receive(value)
    assert not client.can_resolve_terminal_failure()
    with pytest.raises(StudioError):
        client.resolve_terminal_failure("studio-turn-1")
    assert client.pending == "studio-turn-1"


def test_chat_job_not_found_is_not_evidence_of_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _core = _client(tmp_path, monkeypatch)
    client.receive({"ok": False, "error_code": "chat_job_not_found", "request_id": client.pending})
    assert not client.can_resolve_terminal_failure()
    assert client.pending == "studio-turn-1"


def test_restart_requires_fresh_failure_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, core = _client(tmp_path, monkeypatch)
    client.receive(_failed_result(client))
    restored = studio_chat.ChatClient(core)  # type: ignore[arg-type]
    assert restored.pending == "studio-turn-1"
    assert not restored.can_resolve_terminal_failure()


def test_terminal_recovery_tombstone_survives_ttl_and_another_persist(tmp_path: Path) -> None:
    server = runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0), runtime_daemon.JaznDaemonHandler,
        config=JaznConfig(root=tmp_path.resolve()),
        marker_path=tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
    )
    try:
        request_id = "studio-turn-retained"
        failed = runtime_daemon.DaemonChatJob(
            request_id=request_id, user_text="",
            user_text_sha256="a" * 64, input_field="message",
            session_id="studio-session", no_carryover=False,
            client="daemon_conversation_client", request_fingerprint="fingerprint-retained",
            command="--chat-ollama",
            completed_at_utc=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            status="failed", error="runtime_turn_not_accepted",
            result={"ok": False, "error_code": "runtime_turn_not_accepted", "request_id": request_id},
        )
        failed.done_event.set()
        server.chat_jobs[request_id] = failed
        assert server._persist_chat_jobs_locked(stage="test")
        server._cleanup_chat_jobs_locked()
        assert request_id not in server.chat_jobs
        assert server._persist_chat_jobs_locked(stage="later_write")
        persisted = json.loads(server._chat_state_path.read_text(encoding="utf-8"))
        assert any(row["request_id"] == request_id for row in persisted["jobs"])
        assert persisted["contains_user_text"] is False
        recovered = server.get_chat_job(request_id)
        assert recovered is not None
        assert recovered.status == "failed"
        assert recovered.user_text == ""
        assert recovered.result is not None and recovered.result["ok"] is False
        assert recovered.result["automatic_replay_performed"] is False
        assert recovered.session_id == "studio-session"
    finally:
        server.server_close()


def test_unknown_request_remains_unknown(tmp_path: Path) -> None:
    server = runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0), runtime_daemon.JaznDaemonHandler,
        config=JaznConfig(root=tmp_path.resolve()),
        marker_path=tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
    )
    try:
        assert server.get_chat_job("not-present") is None
    finally:
        server.server_close()
