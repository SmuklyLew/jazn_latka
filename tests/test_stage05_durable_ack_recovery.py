"""Stage 05: durable ACK recovery does not regenerate or downgrade acceptance."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.core import chatgpt_host_pending_store as store
from test_finalization_crash_atomicity import _request, _finalize


def test_delivered_outbox_is_monotonic_across_repeated_notifications(tmp_path: Path) -> None:
    reply = _request(tmp_path)
    result, errors = _finalize(tmp_path, reply)
    assert result is not None and not errors
    turn_id, digest = reply["turn_id"], reply["host_request_contract_hash"]

    def mark(delivered: bool) -> dict[str, Any]:
        return store.mark_daemon_finalization_notification(
            tmp_path, turn_id=turn_id, request_contract_hash=digest, delivered=delivered,
        )

    first = mark(True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        repeated = list(pool.map(mark, (False, True, False)))
    for value in repeated:
        assert value["daemon_finalization_notification_state"] == "delivered"
        assert value["daemon_finalization_notification_attempts"] == first["daemon_finalization_notification_attempts"]
    committed = store.read_committed_host_request(tmp_path, turn_id=turn_id)
    assert committed["final_visible_capture"]["final_visible_text"] == result["final_visible_text"]


@pytest.mark.parametrize("damage", ["none", "write_failed", "wrong_hash", "wrong_request", "wrong_user_hash", "already_delivered", "historical_tombstone"])
def test_ack_reconciliation_requires_exact_durable_capture_and_job_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str,
) -> None:
    server = object.__new__(daemon.JaznDaemonServer)
    server.config = JaznConfig(root=tmp_path)
    server._chat_jobs_lock = RLock()
    job = daemon.DaemonChatJob(
        request_id="r", user_text="", input_field="message", session_id="s",
        no_carryover=False, client="chatgpt_daemon_bridge", status="completed",
        user_text_sha256="b" * 64, host_turn_id="t", host_trace_id="x",
        host_request_contract_hash="a" * 64, result={"ok": True},
    )
    record: dict[str, Any] = {
        "binding": {"daemon_request_id": "r", "turn_id": "t", "trace_id": "x", "user_text_sha256": "b" * 64},
        "request_contract_hash": "a" * 64, "daemon_finalization_notification_state": "pending",
    }
    if damage == "wrong_hash":
        record["request_contract_hash"] = "c" * 64
    elif damage == "wrong_request":
        record["binding"]["daemon_request_id"] = "other"
    elif damage == "wrong_user_hash":
        record["binding"]["user_text_sha256"] = "c" * 64
    elif damage == "already_delivered":
        record["daemon_finalization_notification_state"] = "delivered"
    elif damage == "historical_tombstone":
        job.status = "recovered_after_restart"
        job.recovery_disposition = "completed_request_result_unavailable"
    calls: list[str] = []

    def persist(**_k: Any) -> bool:
        calls.append("persist")
        return damage != "write_failed"

    def mark(*_a: Any, **_k: Any) -> dict[str, Any]:
        calls.append("mark")
        return {"daemon_finalization_notification_state": "delivered"}

    monkeypatch.setattr(store, "read_committed_host_request", lambda *_a, **_k: record)
    monkeypatch.setattr(store, "mark_daemon_finalization_notification", mark)
    monkeypatch.setattr(server, "_persist_chat_jobs_locked", persist)
    result = server._reconcile_committed_notification_locked(job)
    if damage in {"none", "historical_tombstone"}:
        assert result is True
        assert calls == ["persist", "mark"]
    elif damage == "already_delivered":
        assert result is True
        assert not calls
    else:
        assert result is False
        assert calls == (["persist"] if damage == "write_failed" else [])
    assert job.result == {"ok": True}


def test_accepted_ack_reports_job_persistence_failure_and_retry_only_repairs_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = object.__new__(daemon.JaznDaemonServer)
    server.config = JaznConfig(root=tmp_path)
    server._chat_jobs_lock = RLock()
    server.state = daemon.DaemonRuntimeState(root=str(tmp_path), host="127.0.0.1", port=8787)
    job = daemon.DaemonChatJob(
        request_id="r", user_text="synthetic", input_field="message", session_id="s",
        no_carryover=False, client="chatgpt_daemon_bridge", status="awaiting_host_finalization",
        host_turn_id="t", host_trace_id="x", host_request_contract_hash="a" * 64,
    )
    server.chat_jobs = {"r": job}
    monkeypatch.setattr(server, "_advance_host_finalization_waiters_locked", lambda **_k: False)
    outcomes = iter([False, True])
    monkeypatch.setattr(server, "_persist_chat_jobs_locked", lambda **_k: next(outcomes))
    kwargs = {"request_id": "r", "turn_id": "t", "trace_id": "x",
              "request_contract_hash": "a" * 64, "outcome": "accepted",
              "reason": "synthetic", "terminal": True}
    first, error = server.note_host_finalization(**kwargs)
    assert first is job and error is not None
    assert error["error_code"] == "host_finalization_job_persist_failed"
    count = server.state.chat_job_completed_count
    retry, error = server.note_host_finalization(**kwargs)
    assert retry is job and error is None
    assert server.state.chat_job_completed_count == count == 1
