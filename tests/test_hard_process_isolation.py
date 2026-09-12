from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sqlite3
import time

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.chatgpt_host_pending_store import (
    calculate_host_request_contract_hash,
    persist_pending_host_request,
)
from latka_jazn.core.runtime_daemon import (
    DAEMON_CHAT_JOB_HOST_PENDING_STATE,
    DaemonChatJob,
    JaznDaemonHandler,
    JaznDaemonServer,
    daemon_chat_request_fingerprint,
)
from latka_jazn.core.turn_timeout import (
    HardIsolatedRuntimeSessionWorker,
    RuntimeTurnTimeoutError,
)


@dataclass(slots=True)
class _ProcessFixtureState:
    session_id: str

    def to_dict(self) -> dict[str, str]:
        return {"session_id": self.session_id}


class _ProcessScenarioSession:
    """Spawn-pickleable fixture for Windows process-boundary regressions."""

    def __init__(
        self,
        config: JaznConfig,
        *,
        session_id: str | None,
        no_carryover: bool,
        source_client: str,
    ) -> None:
        del no_carryover, source_client
        self.config = config
        self.state = _ProcessFixtureState(session_id or "process-fixture")

    def process_user_text(self, user_text: str, **kwargs: object) -> dict[str, object]:
        turn_context = kwargs.get("_turn_context")
        scenario = str(user_text)
        if scenario == "infinite-loop":
            sentinel = self.config.runtime_workspace_dir / "forbidden-partial-commit.txt"
            assert turn_context is not None
            turn_context.stage_semantic_write(  # type: ignore[union-attr]
                data_type="process_fixture",
                stage="candidate_persistence_staging",
                commit=lambda: sentinel.write_text("partial", encoding="utf-8"),
            )
            while True:
                time.sleep(0.01)
        if scenario == "sqlite-long-query":
            connection = sqlite3.connect(":memory:")
            try:
                connection.execute(
                    "WITH RECURSIVE counter(value) AS ("
                    "VALUES(0) UNION ALL SELECT value + 1 FROM counter WHERE value < 1000000000"
                    ") SELECT sum(value) FROM counter"
                ).fetchone()
            finally:
                connection.close()
        if scenario == "model-timeout":
            time.sleep(60.0)
        if scenario == "pending-host":
            turn_id = str(getattr(turn_context, "turn_id", "turn-pending"))
            trace_id = "trace-process-pending"
            bridge: dict[str, object] = {
                "phase": "host_visible_generation_requested",
                "turn_id": turn_id,
                "trace_id": trace_id,
                "timestamp_header": "[2026-08-23 12:00:00 CEST | Europe/Warsaw]",
                "timezone": "Europe/Warsaw",
                "timestamp_sample_iso": "2026-08-23T12:00:00+02:00",
                "timestamp_source": "process_fixture",
                "timestamp_trusted": True,
                "author_id": "latka",
                "author_label": "Latka",
                "author_source": "canonical",
                "state_emoticon": ":)",
                "user_text_sha256": "a" * 64,
                "finalization_contract_hash": "b" * 64,
                "runtime_context_sha256": "c" * 64,
                "daemon_request_id": str(getattr(turn_context, "request_id", "request-pending")),
            }
            bridge["host_request_contract_hash"] = calculate_host_request_contract_hash(bridge)
            persist_pending_host_request(self.config.root, bridge, ttl_seconds=600)
            bridge["pending_request_persisted"] = True
            bridge["pending_request_expires_at_utc"] = "2026-08-23T12:10:00+00:00"
            return {
                "ok": True,
                "host_finalization_pending": True,
                "chatgpt_host_bridge": bridge,
                "worker_pid": os.getpid(),
            }
        return {
            "ok": True,
            "final_visible_text": "fixture-ok",
            "worker_pid": os.getpid(),
        }

    def close(self) -> None:
        return


def _config(root: Path) -> JaznConfig:
    return JaznConfig(
        root=root,
        rest_cycle_enabled=False,
        hard_worker_process_isolation=True,
        worker_process_cancel_grace_seconds=0.1,
        worker_process_startup_timeout_seconds=10.0,
    )


def _worker(root: Path, *, timeout_seconds: float = 0.25) -> HardIsolatedRuntimeSessionWorker:
    return HardIsolatedRuntimeSessionWorker(
        session_factory=_ProcessScenarioSession,
        config=_config(root),
        session_id="hard-process-session",
        no_carryover=False,
        source_client="process-test",
        command="process-test",
        timeout_seconds=timeout_seconds,
        cancel_grace_seconds=0.1,
        startup_timeout_seconds=10.0,
    )


@pytest.mark.parametrize("scenario", ["infinite-loop", "sqlite-long-query", "model-timeout"])
def test_hard_deadline_kills_only_the_child_process(
    tmp_path: Path,
    scenario: str,
) -> None:
    parent_pid = os.getpid()
    worker = _worker(tmp_path)
    child_pid = worker.worker_pid

    with pytest.raises(RuntimeTurnTimeoutError):
        worker.process_user_text(scenario)

    assert os.getpid() == parent_pid
    assert child_pid != parent_pid
    assert worker.timed_out is True
    assert worker.usable is False
    assert worker.last_termination is not None
    assert worker.last_termination["cooperative_cancel_requested"] is True
    assert worker.last_termination["terminated"] or worker.last_termination["killed"]
    assert worker.last_termination["parent_process_alive"] is True
    worker.close()


def test_killed_precommit_turn_leaves_no_partial_state_and_next_worker_succeeds(
    tmp_path: Path,
) -> None:
    first = _worker(tmp_path)
    first_pid = first.worker_pid
    with pytest.raises(RuntimeTurnTimeoutError):
        first.process_user_text("infinite-loop")

    assert not (tmp_path / "workspace_runtime" / "forbidden-partial-commit.txt").exists()
    second = _worker(tmp_path)
    try:
        result = second.process_user_text("fast")
        assert result["ok"] is True
        assert result["final_visible_text"] == "fixture-ok"
        assert result["worker_pid"] == second.worker_pid
        assert second.worker_pid != first_pid
        assert result["hard_worker_process"] == {
            "active": True,
            "worker_pid": second.worker_pid,
            "parent_pid": os.getpid(),
            "start_method": "spawn",
            "replaceable": True,
            "cancel_grace_seconds": 0.1,
        }
    finally:
        first.close()
        second.close()


def test_daemon_status_claims_hard_isolation_only_when_really_active(tmp_path: Path) -> None:
    marker = tmp_path / "workspace_runtime" / "daemon.json"
    process_server = JaznDaemonServer(
        ("127.0.0.1", 0),
        JaznDaemonHandler,
        config=_config(tmp_path),
        marker_path=marker,
        session_factory=_ProcessScenarioSession,
        execution_timeout_seconds=0.5,
        hard_worker_process_isolation=True,
    )
    compatibility_server = JaznDaemonServer(
        ("127.0.0.1", 0),
        JaznDaemonHandler,
        config=_config(tmp_path / "compat"),
        marker_path=tmp_path / "compat" / "workspace_runtime" / "daemon.json",
        session_factory=_ProcessScenarioSession,
        execution_timeout_seconds=0.5,
    )
    try:
        process_status = process_server.chat_job_summary()["process_liveness"]
        compatibility_status = compatibility_server.chat_job_summary()["process_liveness"]
        assert process_status["hard_worker_process_isolation"] is True
        assert process_status["worker_process_start_method"] == "spawn"
        assert process_status["running_thread_hard_cancel_supported"] is False
        assert compatibility_status["hard_worker_process_isolation"] is False
        assert compatibility_status["worker_process_start_method"] is None
        assert compatibility_status["running_thread_hard_cancel_supported"] is False
    finally:
        process_server.close_sessions()
        process_server.server_close()
        compatibility_server.close_sessions()
        compatibility_server.server_close()


def test_daemon_parent_survives_timeout_and_next_job_uses_fresh_process(tmp_path: Path) -> None:
    marker = tmp_path / "workspace_runtime" / "daemon.json"
    server = JaznDaemonServer(
        ("127.0.0.1", 0),
        JaznDaemonHandler,
        config=_config(tmp_path),
        marker_path=marker,
        session_factory=_ProcessScenarioSession,
        execution_timeout_seconds=0.25,
        hard_worker_process_isolation=True,
    )
    parent_pid = os.getpid()
    timeout_job = DaemonChatJob(
        request_id="daemon-hard-timeout",
        user_text="infinite-loop",
        input_field="text",
        session_id="replaceable-session",
        no_carryover=False,
        client="process-test",
        execution_timeout_seconds=0.25,
    )
    fast_job = DaemonChatJob(
        request_id="daemon-after-timeout",
        user_text="fast",
        input_field="text",
        session_id="replaceable-session",
        no_carryover=False,
        client="process-test",
        execution_timeout_seconds=0.5,
    )
    server.chat_jobs[timeout_job.request_id] = timeout_job
    server.chat_jobs[fast_job.request_id] = fast_job
    try:
        server._process_chat_job(timeout_job, worker_generation=1)
        assert timeout_job.status == "execution_timeout"
        assert timeout_job.result is not None
        termination = timeout_job.result["hard_worker_process_termination"]
        assert timeout_job.result["timeout_owner"] == "hard_isolated_runtime_worker_process"
        assert termination["parent_pid"] == parent_pid
        assert termination["terminated"] or termination["killed"]
        assert os.getpid() == parent_pid

        server._process_chat_job(fast_job, worker_generation=2)
        assert fast_job.status == "completed"
        assert fast_job.result is not None
        assert fast_job.result["worker_pid"] != termination["worker_pid"]
        assert fast_job.result["hard_worker_process"]["active"] is True
        assert not (tmp_path / "workspace_runtime" / "forbidden-partial-commit.txt").exists()
    finally:
        server.close_sessions()
        server.server_close()


def test_pending_host_continuation_survives_worker_replacement_and_daemon_restart(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "workspace_runtime" / "daemon.json"
    server = JaznDaemonServer(
        ("127.0.0.1", 0),
        JaznDaemonHandler,
        config=_config(tmp_path),
        marker_path=marker,
        session_factory=_ProcessScenarioSession,
        execution_timeout_seconds=2.0,
        hard_worker_process_isolation=True,
    )
    request_id = "pending-process-request"
    job = DaemonChatJob(
        request_id=request_id,
        user_text="pending-host",
        input_field="text",
        session_id="pending-process-session",
        no_carryover=False,
        client="process-test",
        request_fingerprint=daemon_chat_request_fingerprint(
            user_text="pending-host",
            session_id="pending-process-session",
            no_carryover=False,
            client="process-test",
        ),
        execution_timeout_seconds=2.0,
    )
    server.chat_jobs[request_id] = job
    try:
        server._process_chat_job(job, worker_generation=1)
        assert job.status == DAEMON_CHAT_JOB_HOST_PENDING_STATE
        assert job.phase_result_ready() is True
        worker = server.sessions["pending-process-session"]
        server._retire_session_worker(worker)
        assert job.status == DAEMON_CHAT_JOB_HOST_PENDING_STATE
        assert request_id not in server.sessions
    finally:
        server.close_sessions()
        server.server_close()

    recovered_server = JaznDaemonServer(
        ("127.0.0.1", 0),
        JaznDaemonHandler,
        config=_config(tmp_path),
        marker_path=marker,
        session_factory=_ProcessScenarioSession,
        execution_timeout_seconds=2.0,
        hard_worker_process_isolation=True,
    )
    try:
        recovered = recovered_server.chat_jobs[request_id]
        assert recovered.status == DAEMON_CHAT_JOB_HOST_PENDING_STATE
        assert recovered.recovery_disposition == "host_finalization_pending_recovered"
        assert recovered.host_turn_id == job.host_turn_id
        assert recovered.host_request_contract_hash == job.host_request_contract_hash
    finally:
        recovered_server.close_sessions()
        recovered_server.server_close()
