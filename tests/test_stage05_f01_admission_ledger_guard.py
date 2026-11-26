"""Synthetic Stage 05 F01 regressions: missing or invalid history is not absence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon


def _server(root: Path, monkeypatch: pytest.MonkeyPatch) -> daemon.JaznDaemonServer:
    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), daemon.JaznDaemonHandler,
        config=JaznConfig(root=root, memory_mode="off"),
        marker_path=root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        hard_worker_process_isolation=False,
    )
    monkeypatch.setattr(server, "start_chat_worker", lambda: None)
    monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
    return server


def _submit(server: daemon.JaznDaemonServer, request_id: str = "synthetic-request"):
    return server.submit_chat_job(
        request_id=request_id, user_text="synthetic input", session_id="synthetic-session",
        input_field="message", no_carryover=False, client="synthetic-client",
    )


def _assert_blocked(server: daemon.JaznDaemonServer, code: str, request_id: str = "synthetic-request") -> None:
    job, created, error = _submit(server, request_id)
    assert job is None and not created and error is not None
    assert error["error_code"] == code
    assert error["must_not_resubmit_user_message"] is True
    assert server._chat_queue.empty()
    assert server.chat_job_summary()["submitted_total"] == 0


@pytest.mark.parametrize("damage", ["{broken", "[]", '{"jobs":[null]}',
    '{"jobs":[{"request_id":"same"},{"request_id":"same"}]}'])
def test_invalid_ledger_quarantine_does_not_authorize_new_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str,
) -> None:
    path = tmp_path / "workspace_runtime" / "daemon_chat_jobs.json"
    path.parent.mkdir(parents=True)
    path.write_text(damage, encoding="utf-8")
    for _ in range(2):
        server = _server(tmp_path, monkeypatch)
        try:
            _assert_blocked(server, "daemon_chat_ledger_missing")
            assert not path.exists()
            evidence = list(path.parent.glob("daemon_chat_jobs.json.corrupt-*"))
            assert len(evidence) == 1
            assert evidence[0].read_text(encoding="utf-8") == damage
        finally:
            server.close_sessions()
            server.server_close()


def test_missing_established_ledger_blocks_admission_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _server(tmp_path, monkeypatch)
    try:
        job, created, error = _submit(first)
        assert job is not None and created and error is None
        assert first._chat_ledger_guard_path.is_file()
        path = first._chat_state_path
        assert json.loads(path.read_text(encoding="utf-8"))["jobs"][0]["request_id"] == job.request_id
    finally:
        first.close_sessions()
        first.server_close()
    path.unlink()
    second = _server(tmp_path, monkeypatch)
    try:
        _assert_blocked(second, "daemon_chat_ledger_missing")
        _assert_blocked(second, "daemon_chat_ledger_missing", "new-request")
        assert not path.exists()
    finally:
        second.close_sessions()
        second.server_close()


def test_unreadable_ledger_is_not_treated_as_new_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server(tmp_path, monkeypatch)
    original_read = Path.read_text
    try:
        def deny_ledger(path: Path, *args, **kwargs):
            if path == server._chat_state_path:
                raise PermissionError("synthetic read failure")
            return original_read(path, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", deny_ledger)
        _assert_blocked(server, "daemon_chat_ledger_unreadable")
    finally:
        server.close_sessions()
        server.server_close()


def test_unrehydratable_existing_identity_cannot_be_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server(tmp_path, monkeypatch)
    try:
        path = server._chat_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps({"jobs": [{"request_id": "synthetic-request",
            "status": "completed", "request_fingerprint": None}]})
        path.write_text(raw, encoding="utf-8")
        _assert_blocked(server, "daemon_chat_ledger_unresolved_record")
        assert path.read_text(encoding="utf-8") == raw
    finally:
        server.close_sessions()
        server.server_close()
