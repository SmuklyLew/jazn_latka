from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import time

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon


SAMPLE_ISO = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc).isoformat()
HEADER = "🕒 2026-08-29 14:00:00"


def _host_pending_result(suffix: str) -> dict:
    safe = suffix.replace(" ", "-")
    return {
        "ok": True,
        "host_finalization_pending": True,
        "execution_state": "awaiting_host_finalization",
        "runtime_version": "test-version",
        "trace": {
            "turn_id": f"turn-{safe}",
            "trace_id": f"trace-{safe}",
            "timestamp_header": HEADER,
            "timezone": "Europe/Warsaw",
        },
        "conversation_decision": {
            "handler_name": "RuntimeTurnTruthGate",
            "route": "ordinary_dialogue",
            "detected_user_intent": "ordinary_conversation",
            "requires_host_model": True,
            "timestamp_contract": {
                "timezone": "Europe/Warsaw",
                "sample_iso": SAMPLE_ISO,
                "source": "test",
                "trusted": True,
            },
        },
        "runtime_turn_contract": {
            "turn_id": f"turn-{safe}",
            "trace_id": f"trace-{safe}",
            "handler_name": "RuntimeTurnTruthGate",
            "requires_host_model": True,
            "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": f"turn-{safe}",
            "trace_id": f"trace-{safe}",
            "runtime_version": "test-version",
            "requires_host_model": True,
            "timestamp_header": HEADER,
            "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": SAMPLE_ISO,
            "timestamp_source": "test",
            "timestamp_trusted": True,
            "author_id": "latka_runtime",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
            "state_emoticon": "🌿",
        },
        "runtime_truth_gate": {
            "ok": True,
            "normal_response_allowed": False,
            "errors": ["model_guided_speech_required"],
        },
    }


class _CountingHostPendingSession:
    calls: list[str] = []
    instance_count = 0

    def __init__(self, _config, **kwargs) -> None:
        type(self).instance_count += 1
        self.state = SimpleNamespace(session_id=kwargs.get("session_id"))

    def process_user_text(self, user_text: str, **_kwargs) -> dict:
        type(self).calls.append(user_text)
        return deepcopy(_host_pending_result(user_text))

    def close(self) -> None:
        return None


def _server(root: Path) -> runtime_daemon.JaznDaemonServer:
    _CountingHostPendingSession.calls = []
    _CountingHostPendingSession.instance_count = 0
    resolved = root.resolve()
    return runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0),
        runtime_daemon.JaznDaemonHandler,
        config=JaznConfig(root=resolved),
        marker_path=resolved / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        session_factory=_CountingHostPendingSession,
        execution_timeout_seconds=15.0,
    )


def _submit(
    server: runtime_daemon.JaznDaemonServer,
    request_id: str,
) -> runtime_daemon.DaemonChatJob:
    job, created, error = server.submit_chat_job(
        user_text=request_id,
        input_field="message",
        session_id="session-v163251",
        no_carryover=False,
        client="chatgpt_daemon_bridge",
        request_id=request_id,
    )
    assert created is True and error is None and job is not None
    return job


def _wait_status(job: runtime_daemon.DaemonChatJob, status: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if job.status == status:
            return
        time.sleep(0.01)
    raise AssertionError(f"job {job.request_id} stayed {job.status!r}, expected {status!r}: {job.result!r}")


def _accept(server: runtime_daemon.JaznDaemonServer, job: runtime_daemon.DaemonChatJob) -> None:
    completed, error = server.note_host_finalization(
        request_id=job.request_id,
        turn_id=str(job.host_turn_id),
        trace_id=str(job.host_trace_id),
        request_contract_hash=str(job.host_request_contract_hash),
        outcome="accepted",
        reason="host_visible_reply_finalized",
        terminal=True,
    )
    assert error is None
    assert completed is job
    assert job.status == "completed"


def test_second_turn_waits_for_prior_host_finalization_then_runs(tmp_path: Path) -> None:
    server = _server(tmp_path)
    try:
        first = _submit(server, "issue185-first")
        _wait_status(first, "awaiting_host_finalization")

        second = _submit(server, "issue185-second")
        _wait_status(second, "waiting_for_host_finalization")
        assert _CountingHostPendingSession.calls == ["issue185-first"]
        assert second.previous_request_id == first.request_id
        assert second.previous_runtime_turn_id == first.host_turn_id
        assert second.previous_trace_id == first.host_trace_id
        assert second.host_finalization_gate_state == "awaiting_host_finalization"

        _accept(server, first)
        _wait_status(second, "awaiting_host_finalization")
        assert _CountingHostPendingSession.calls == ["issue185-first", "issue185-second"]
        assert _CountingHostPendingSession.instance_count == 1
        assert second.host_turn_id != first.host_turn_id
        assert second.host_trace_id != first.host_trace_id
        summary = server.chat_job_summary()
        assert summary["host_finalization_gate_released_total"] == 1
        assert summary["host_finalization_gate_timeout_total"] == 0
    finally:
        server.close_sessions()
        server.server_close()


def test_two_rapid_successors_do_not_overtake_each_other(tmp_path: Path) -> None:
    server = _server(tmp_path)
    try:
        first = _submit(server, "issue185-order-1")
        _wait_status(first, "awaiting_host_finalization")
        second = _submit(server, "issue185-order-2")
        third = _submit(server, "issue185-order-3")
        _wait_status(second, "waiting_for_host_finalization")
        _wait_status(third, "waiting_for_host_finalization")
        assert third.previous_request_id == second.request_id
        assert _CountingHostPendingSession.calls == ["issue185-order-1"]

        _accept(server, first)
        _wait_status(second, "awaiting_host_finalization")
        assert third.status == "waiting_for_host_finalization"
        assert _CountingHostPendingSession.calls == ["issue185-order-1", "issue185-order-2"]

        _accept(server, second)
        _wait_status(third, "awaiting_host_finalization")
        assert _CountingHostPendingSession.calls == [
            "issue185-order-1",
            "issue185-order-2",
            "issue185-order-3",
        ]
    finally:
        server.close_sessions()
        server.server_close()


def test_waiting_turn_times_out_fail_closed_without_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JAZN_DAEMON_HOST_FINALIZATION_GATE_SECONDS", "0.15")
    server = _server(tmp_path)
    try:
        first = _submit(server, "issue185-timeout-1")
        _wait_status(first, "awaiting_host_finalization")
        second = _submit(server, "issue185-timeout-2")
        _wait_status(second, "waiting_for_host_finalization")
        assert second.done_event.wait(3.0)
        assert second.status == "failed"
        assert second.result is not None
        assert second.result["error_code"] == "host_finalization_timed_out"
        assert second.result["previous_request_id"] == first.request_id
        assert second.result["retryable"] is True
        assert _CountingHostPendingSession.calls == ["issue185-timeout-1"]
        assert server.chat_job_summary()["host_finalization_gate_timeout_total"] == 1

        _accept(server, first)
        third = _submit(server, "issue185-timeout-3")
        _wait_status(third, "awaiting_host_finalization")
        assert _CountingHostPendingSession.calls[-1] == "issue185-timeout-3"
    finally:
        server.close_sessions()
        server.server_close()


def test_terminal_finalization_failure_fails_waiter_without_execution(tmp_path: Path) -> None:
    server = _server(tmp_path)
    try:
        first = _submit(server, "issue185-reject-1")
        _wait_status(first, "awaiting_host_finalization")
        second = _submit(server, "issue185-reject-2")
        _wait_status(second, "waiting_for_host_finalization")

        completed, error = server.note_host_finalization(
            request_id=first.request_id,
            turn_id=str(first.host_turn_id),
            trace_id=str(first.host_trace_id),
            request_contract_hash=str(first.host_request_contract_hash),
            outcome="rejected",
            reason="host_presentation_failed",
            terminal=True,
        )
        assert error is None and completed is first
        assert first.status == "host_finalization_rejected"
        assert second.done_event.wait(2.0)
        assert second.status == "failed"
        assert second.result is not None
        assert second.result["error_code"] == "host_finalization_failed"
        assert second.result["previous_request_id"] == first.request_id
        assert _CountingHostPendingSession.calls == ["issue185-reject-1"]
        assert server.chat_job_summary()["host_finalization_gate_failed_total"] == 1
    finally:
        server.close_sessions()
        server.server_close()


def test_duplicate_accepted_ack_is_idempotent_and_late_ack_cannot_touch_new_turn(
    tmp_path: Path,
) -> None:
    server = _server(tmp_path)
    try:
        first = _submit(server, "issue185-idempotent-1")
        _wait_status(first, "awaiting_host_finalization")
        _accept(server, first)
        completed_count = server.state.chat_job_completed_count
        attempt_count = first.host_finalization_attempt_count
        reason = first.host_finalization_reason

        duplicate, error = server.note_host_finalization(
            request_id=first.request_id,
            turn_id=str(first.host_turn_id),
            trace_id=str(first.host_trace_id),
            request_contract_hash=str(first.host_request_contract_hash),
            outcome="accepted",
            reason="duplicate_late_ack",
            terminal=True,
        )
        assert error is None and duplicate is first
        assert first.status == "completed"
        assert first.host_finalization_attempt_count == attempt_count
        assert first.host_finalization_reason == reason
        assert server.state.chat_job_completed_count == completed_count

        second = _submit(server, "issue185-idempotent-2")
        _wait_status(second, "awaiting_host_finalization")
        second_status = second.status
        duplicate_again, error_again = server.note_host_finalization(
            request_id=first.request_id,
            turn_id=str(first.host_turn_id),
            trace_id=str(first.host_trace_id),
            request_contract_hash=str(first.host_request_contract_hash),
            outcome="accepted",
            reason="very_late_ack",
            terminal=True,
        )
        assert error_again is None and duplicate_again is first
        assert second.status == second_status == "awaiting_host_finalization"
        assert _CountingHostPendingSession.calls == ["issue185-idempotent-1", "issue185-idempotent-2"]
    finally:
        server.close_sessions()
        server.server_close()


def test_restart_recovers_predecessor_but_never_replays_waiting_successor(tmp_path: Path) -> None:
    first_server = _server(tmp_path)
    try:
        first = _submit(first_server, "issue185-restart-1")
        _wait_status(first, "awaiting_host_finalization")
        second = _submit(first_server, "issue185-restart-2")
        _wait_status(second, "waiting_for_host_finalization")
        assert _CountingHostPendingSession.calls == ["issue185-restart-1"]
        first_id = first.request_id
        second_id = second.request_id
    finally:
        first_server.close_sessions()
        first_server.server_close()

    second_server = _server(tmp_path)
    try:
        recovered_first = second_server.get_chat_job(first_id)
        recovered_second = second_server.get_chat_job(second_id)
        assert recovered_first is not None
        assert recovered_first.status == "awaiting_host_finalization"
        assert recovered_first.recovery_disposition == "host_finalization_pending_recovered"
        assert recovered_second is not None
        assert recovered_second.status == "recovered_after_restart"
        assert recovered_second.recovery_disposition == "failed_without_replay"
        assert recovered_second.result is not None
        assert recovered_second.result["automatic_replay_performed"] is False
        assert _CountingHostPendingSession.calls == []

        _accept(second_server, recovered_first)
        retry = _submit(second_server, "issue185-restart-2-retry")
        _wait_status(retry, "awaiting_host_finalization")
        assert _CountingHostPendingSession.calls == ["issue185-restart-2-retry"]
    finally:
        second_server.close_sessions()
        second_server.server_close()
