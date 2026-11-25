"""Owning-daemon recovery repairs a proved commit without accepting another turn."""
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.core import chatgpt_host_pending_store as store
from latka_jazn.core.conversation_turn_api import RunnerOperations


@pytest.mark.parametrize("case", ["complete", "historical", "wrong_hash", "wrong_request",
                                  "active_session", "partial", "failed_read"])
def test_owning_daemon_repairs_only_exact_committed_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str,
) -> None:
    server = object.__new__(daemon.JaznDaemonServer)
    server.config = JaznConfig(root=tmp_path)
    job = daemon.DaemonChatJob(
        request_id="r", user_text="", input_field="message", session_id="s",
        no_carryover=False, client="chatgpt_daemon_bridge", status="completed",
        user_text_sha256="b" * 64, host_turn_id="t", host_trace_id="x",
        host_request_contract_hash="a" * 64, result={"ok": True},
    )
    server.chat_jobs = {"r": job}
    record = {
        "binding": {"daemon_request_id": "r", "turn_id": "t", "trace_id": "x",
                    "user_text_sha256": "b" * 64},
        "request_contract_hash": "a" * 64,
    }
    if case == "historical":
        job.status = "recovered_after_restart"
        job.recovery_disposition = "completed_request_result_unavailable"
    if case == "wrong_hash":
        record["request_contract_hash"] = "c" * 64
    if case == "wrong_request":
        record["binding"]["daemon_request_id"] = "other"
    if case == "active_session":
        server.chat_jobs["other"] = daemon.DaemonChatJob(
            request_id="other", user_text="synthetic", input_field="message",
            session_id="s", no_carryover=False, client="test", status="running",
        )

    def read(*_a: Any, **_k: Any) -> dict[str, Any]:
        if case == "failed_read":
            raise store.HostRequestStoreError("synthetic")
        return record

    calls: list[tuple[str, str]] = []

    def repair(*, config: Any, turn_id: str, request_id: str) -> dict[str, Any]:
        assert config is server.config
        calls.append((turn_id, request_id))
        return {"acceptance_state": "already_committed",
                "capture": {"projection_status": "published"},
                "conversation": {"ok": True}, "session": {"saved": case != "partial"}}

    monkeypatch.setattr(store, "read_committed_host_request", read)
    monkeypatch.setattr(RunnerOperations, "recover_projection", staticmethod(repair))
    before = job.status
    server._recover_committed_job_projections_locked(job)
    expected = {"complete": "published", "historical": "published",
                "wrong_hash": "binding_mismatch", "wrong_request": "binding_mismatch",
                "active_session": "deferred_active_session", "partial": "pending_recovery",
                "failed_read": "pending_recovery"}[case]
    assert job.host_projection_recovery_status == expected
    assert job.status == before
    assert job.result == {"ok": True}
    assert calls == ([("t", "r")] if case in {"complete", "historical", "partial"} else [])
    server._recover_committed_job_projections_locked(job)
    if case in {"complete", "historical"}:
        assert calls == [("t", "r")]
    if case == "partial":
        assert calls == [("t", "r"), ("t", "r")]
