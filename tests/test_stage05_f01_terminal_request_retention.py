"""F01: every admitted terminal request retains its identity independently of LLM."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import queue
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


def _submit(server: daemon.JaznDaemonServer, **changes: Any):
    request: dict[str, Any] = {
        "request_id": "f01-synthetic", "user_text": "CANARY PRIVATE INPUT",
        "session_id": "synthetic-session", "input_field": "message",
        "no_carryover": False, "client": "synthetic-client",
    }
    request.update(changes)
    return server.submit_chat_job(**request)


@pytest.mark.parametrize("status", [
    "failed", "execution_timeout", "cancelled", "host_finalization_expired",
    "host_finalization_rejected", "recovered_after_restart",
])
def test_terminal_identity_survives_restart_eviction_and_snapshot_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str,
) -> None:
    first = _server(tmp_path, monkeypatch)
    ledger = first._chat_state_path
    try:
        job, created, error = _submit(first)
        assert job is not None and created and error is None
        assert first._chat_queue.get_nowait() is job
        first._chat_queue.task_done()
        job.status = status
        job.completed_at_utc = datetime.now(timezone.utc).isoformat()
        job.error = "CANARY PRIVATE EXCEPTION"
        job.result = {"ok": False, "error_code": "synthetic_failure",
                      "final_visible_text": "CANARY PRIVATE ANSWER"}
        job.host_turn_id = "synthetic-turn"
        job.host_trace_id = "synthetic-trace"
        job.host_request_contract_hash = "a" * 64
        job.host_finalization_reason = "CANARY PRIVATE REASON"
        job.done_event.set()
        with first._chat_jobs_lock:
            assert first._persist_chat_jobs_locked(stage="synthetic_terminal")
        raw = ledger.read_text(encoding="utf-8")
        assert "CANARY PRIVATE" not in raw
        row = json.loads(raw)["jobs"][0]
        assert row["status"] == status
        assert row["request_fingerprint"] == job.request_fingerprint
        assert row["result_error_code"] == "synthetic_failure"
    finally:
        first.close_sessions()
        first.server_close()

    for _ in range(2):
        second = _server(tmp_path, monkeypatch)
        try:
            recovered = second.get_chat_job("f01-synthetic")
            assert recovered is not None and recovered.terminal()
            assert recovered.status == status
            assert recovered.result is not None
            assert recovered.result["error_code"] == "synthetic_failure"
            assert recovered.result["automatic_replay_performed"] is False
            assert recovered.host_turn_id == "synthetic-turn"
            assert recovered.host_trace_id == "synthetic-trace"
            assert recovered.host_request_contract_hash == "a" * 64
            assert not recovered.user_text
            assert not recovered.snapshot()["ok"]
            again, created, error = _submit(second)
            assert again is recovered and not created and error is None
            for change in ({"user_text": "different"}, {"client": "different"},
                           {"command": "--chat-ollama"}):
                conflict, created, error = _submit(second, **change)
                assert conflict is None and not created and error is not None
                assert error["error_code"] == "request_id_conflict"
            recovered.completed_at_utc = (
                datetime.now(timezone.utc) - timedelta(days=30)
            ).isoformat()
            with second._chat_jobs_lock:
                second._cleanup_chat_jobs_locked()
                assert "f01-synthetic" not in second.chat_jobs
                assert second._persist_chat_jobs_locked(stage="synthetic_after_eviction")
            again, created, error = _submit(second)
            assert again is not None and again.status == status
            assert not created and error is None
            assert second._chat_queue.empty()
            assert second.chat_job_summary()["submitted_total"] == 0
            assert "CANARY PRIVATE" not in ledger.read_text(encoding="utf-8")
        finally:
            second.close_sessions()
            second.server_close()


def test_admission_write_failure_never_enqueues_or_acknowledges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server(tmp_path, monkeypatch)
    try:
        def fail() -> None:
            raise OSError("synthetic storage unavailable")
        monkeypatch.setattr(server, "_persist_chat_jobs_locked_unsafe", fail)
        job, created, error = _submit(server)
        assert job is None and created is False and error is not None
        assert error["error_code"] == "daemon_chat_state_persist_failed"
        assert error["must_not_resubmit_user_message"] is True
        assert server._chat_queue.empty()
        assert "f01-synthetic" not in server.chat_jobs
        assert server.chat_job_summary()["submitted_total"] == 0
        assert server.chat_job_summary()["pending_current"] == 0
        assert not server._chat_state_path.exists()
    finally:
        server.close_sessions()
        server.server_close()


def test_admission_persists_identity_before_queue_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server(tmp_path, monkeypatch)
    try:
        original_put = server._chat_queue.put_nowait
        observed: list[str] = []
        def check_before_put(job: daemon.DaemonChatJob | None) -> None:
            if job is not None:
                rows = json.loads(server._chat_state_path.read_text(encoding="utf-8"))["jobs"]
                assert any(row["request_id"] == job.request_id
                           and row["request_fingerprint"] == job.request_fingerprint
                           for row in rows)
                observed.append(job.request_id)
            original_put(job)
        monkeypatch.setattr(server._chat_queue, "put_nowait", check_before_put)
        job, created, error = _submit(server)
        assert job is not None and created and error is None
        assert observed == ["f01-synthetic"]
        again, created, error = _submit(server)
        assert again is job and not created and error is None
        assert observed == ["f01-synthetic"]
    finally:
        server.close_sessions()
        server.server_close()


def test_concurrent_duplicate_has_one_admission_and_one_queue_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server(tmp_path, monkeypatch)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(lambda _i: _submit(server), range(8)))
        assert sum(created for _, created, _ in outcomes) == 1
        assert all(error is None for _, _, error in outcomes)
        assert all(job is outcomes[0][0] for job, _, _ in outcomes)
        assert server._chat_queue.qsize() == 1
        assert server.chat_job_summary()["submitted_total"] == 1
        assert len(json.loads(server._chat_state_path.read_text(encoding="utf-8"))["jobs"]) == 1
    finally:
        server.close_sessions()
        server.server_close()


def test_queue_failure_after_admission_retains_terminal_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _server(tmp_path, monkeypatch)
    try:
        def fail(job: daemon.DaemonChatJob | None) -> None:
            if job is not None:
                raise queue.Full
        monkeypatch.setattr(first._chat_queue, "put_nowait", fail)
        job, created, error = _submit(first)
        assert job is not None and created and error is None
        assert job.terminal() and job.status == "failed"
        assert job.done_event.is_set()
        assert first.chat_job_summary()["submitted_total"] == 1
        assert first.chat_job_summary()["pending_current"] == 0
    finally:
        first.close_sessions()
        first.server_close()
    second = _server(tmp_path, monkeypatch)
    try:
        job, created, error = _submit(second)
        assert job is not None and not created and error is None
        assert job.terminal() and job.error == "daemon_chat_queue_full_after_admission"
        assert second._chat_queue.empty()
        assert second.chat_job_summary()["submitted_total"] == 0
    finally:
        second.close_sessions()
        second.server_close()
