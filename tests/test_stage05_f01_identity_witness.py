"""F01: a syntactically valid but altered admission ledger is not absence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def _submit(server: daemon.JaznDaemonServer, request_id: str):
    return server.submit_chat_job(
        request_id=request_id, user_text="synthetic input", session_id="synthetic-session",
        input_field="message", no_carryover=False, client="synthetic",
    )


@pytest.mark.parametrize("damage", ["empty", "replaced_id", "replaced_fingerprint", "missing_witness"])
def test_witness_blocks_valid_json_identity_loss_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str,
) -> None:
    first = _server(tmp_path, monkeypatch)
    try:
        job, created, error = _submit(first, "old-request")
        assert job is not None and created and error is None
        ledger, guard = first._chat_state_path, first._chat_ledger_guard_path
        raw = json.loads(ledger.read_text(encoding="utf-8"))
        witness = json.loads(guard.read_text(encoding="utf-8"))
        assert witness["identity_count"] == 1
        assert witness["schema_version"] == "daemon_chat_admission_established/v2"
        assert "old-request" not in repr(witness)
    finally:
        first.close_sessions()
        first.server_close()
    if damage == "empty":
        raw["jobs"] = []
    elif damage == "replaced_id":
        raw["jobs"][0]["request_id"] = "other-request"
    elif damage == "replaced_fingerprint":
        raw["jobs"][0]["request_fingerprint"] = "0" * 64
    else:
        guard.unlink()
    ledger.write_text(json.dumps(raw), encoding="utf-8")
    before = ledger.read_bytes()
    second = _server(tmp_path, monkeypatch)
    try:
        for request_id in ("old-request", "new-request"):
            job, created, error = _submit(second, request_id)
            assert job is None and not created and error is not None
            assert error["error_code"] == "daemon_chat_ledger_unresolved_record"
            assert error["must_not_resubmit_user_message"] is True
            with pytest.raises(ValueError, match="daemon_chat_ledger_unresolved_record"):
                second.get_chat_job(request_id)
        assert second._chat_queue.empty()
        assert second.chat_job_summary()["submitted_total"] == 0
        assert ledger.read_bytes() == before
    finally:
        second.close_sessions()
        second.server_close()


def test_interrupted_second_admission_witness_blocks_replay_and_new_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _server(tmp_path, monkeypatch)
    try:
        job, created, error = _submit(first, "first")
        assert job is not None and created and error is None
        before = first._chat_state_path.read_bytes()
        original = daemon.write_json_atomic

        def interrupted(path: Path, payload: Any, **kwargs: Any) -> None:
            if path == first._chat_state_path:
                raise OSError("synthetic interruption between witness and ledger")
            original(path, payload, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(daemon, "write_json_atomic", interrupted)
            job, created, error = _submit(first, "second")
        assert job is None and not created and error is not None
        assert error["error_code"] == "daemon_chat_state_persist_failed"
        assert first._chat_queue.qsize() == 1
        assert first._chat_state_path.read_bytes() == before
        assert json.loads(first._chat_ledger_guard_path.read_text(encoding="utf-8"))["identity_count"] == 2
    finally:
        first.close_sessions()
        first.server_close()
    second = _server(tmp_path, monkeypatch)
    try:
        for request_id in ("first", "second", "third"):
            job, created, error = _submit(second, request_id)
            assert job is None and not created and error is not None
            assert error["error_code"] == "daemon_chat_ledger_unresolved_record"
        assert second._chat_queue.empty()
        assert second._chat_state_path.read_bytes() == before
    finally:
        second.close_sessions()
        second.server_close()
