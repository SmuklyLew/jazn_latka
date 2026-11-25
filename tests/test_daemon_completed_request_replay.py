"""Durable daemon request identity must survive restart and local cache eviction.

Fixtures are synthetic, isolated and do not invoke live private MEMORY.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon import (
    DaemonChatJob,
    JaznDaemonHandler,
    JaznDaemonServer,
    daemon_chat_request_fingerprint,
)


def _server(root: Path) -> JaznDaemonServer:
    return JaznDaemonServer(
        ("127.0.0.1", 0),
        JaznDaemonHandler,
        config=JaznConfig(root=root, memory_mode="off"),
        marker_path=root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        hard_worker_process_isolation=False,
    )


def test_completed_request_tombstone_survives_multiple_daemon_restarts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "synthetic_system"
    root.mkdir()
    request = dict(
        user_text="CANARY-DO-NOT-PERSIST",
        session_id="synthetic-session",
        no_carryover=False,
        client="daemon_http",
    )
    request_id = "synthetic-completed-request"
    fingerprint = daemon_chat_request_fingerprint(
        **request,
        command="--chat",
        model_channel_config={},
        reset_session=False,
    )
    first = _server(root)
    try:
        job = DaemonChatJob(
            request_id=request_id,
            input_field="message",
            request_fingerprint=fingerprint,
            **request,
        )
        job.status = "completed"
        job.completed_at_utc = datetime.now(timezone.utc).isoformat()
        job.result = {"ok": True, "final_visible_text": "CANARY-SECRET-ANSWER"}
        first.chat_jobs[request_id] = job
        with first._chat_jobs_lock:
            assert first._persist_chat_jobs_locked(stage="synthetic_completed") is True
        raw = (root / "workspace_runtime" / "daemon_chat_jobs.json").read_text(encoding="utf-8")
        assert "CANARY-DO-NOT-PERSIST" not in raw
        assert "CANARY-SECRET-ANSWER" not in raw
        assert json.loads(raw)["jobs"][0]["status"] == "completed"
    finally:
        first.close_sessions()
        first.server_close()

    for _ in range(2):
        daemon = _server(root)
        try:
            recovered = daemon.get_chat_job(request_id)
            assert recovered is not None
            assert recovered.terminal()
            assert recovered.status == "recovered_after_restart"
            assert recovered.recovery_disposition == "completed_request_result_unavailable"
            assert recovered.snapshot()["ok"] is False
            again, created, error = daemon.submit_chat_job(
                request_id=request_id, input_field="message", **request
            )
            assert again is recovered and created is False and error is None
            different, created, conflict = daemon.submit_chat_job(
                request_id=request_id, input_field="message",
                **{**request, "user_text": "different"},
            )
            assert different is None and created is False
            assert conflict is not None and conflict["error_code"] == "request_id_conflict"
            # An expired in-memory result must not release its durable identity.
            recovered.completed_at_utc = (
                datetime.now(timezone.utc) - timedelta(days=3)
            ).isoformat()
            with daemon._chat_jobs_lock:
                daemon._cleanup_chat_jobs_locked()
            after_eviction, created, error = daemon.submit_chat_job(
                request_id=request_id, input_field="message", **request
            )
            assert after_eviction is not None and created is False and error is None
            assert after_eviction.result is not None
            assert after_eviction.result["automatic_replay_performed"] is False
            with daemon._chat_jobs_lock:
                assert daemon._persist_chat_jobs_locked(stage="tombstone_readback") is True
            raw = (root / "workspace_runtime" / "daemon_chat_jobs.json").read_text(encoding="utf-8")
            assert json.loads(raw)["jobs"][0]["status"] == "completed"
            assert "CANARY-DO-NOT-PERSIST" not in raw
        finally:
            daemon.close_sessions()
            daemon.server_close()
