from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError,
    calculate_host_request_contract_hash,
    claim_pending_host_request,
    consume_claimed_host_request,
    host_request_lifecycle_by_daemon_request_id,
    persist_pending_host_request,
)
from latka_jazn.core.host_response_candidate_guard import (
    build_host_generation_context,
    evaluate_host_response_candidate,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def _server(root: Path) -> runtime_daemon.JaznDaemonServer:
    return runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0),
        runtime_daemon.JaznDaemonHandler,
        config=JaznConfig(root=root.resolve()),
        marker_path=root.resolve() / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        session_factory=lambda *_args, **_kwargs: None,
        execution_timeout_seconds=15.0,
    )


def _bridge(*, request_id: str, turn_id: str, trace_id: str, user_text: str) -> dict:
    value = {
        "schema_version": "chatgpt_host_bridge_turn/v1",
        "runtime_version": "test-v62",
        "phase": "host_visible_generation_requested",
        "turn_id": turn_id,
        "trace_id": trace_id,
        "timestamp_header": "🕒 2026-09-11 13:30:00",
        "timezone": "Europe/Warsaw",
        "timestamp_sample_iso": "2026-09-11T11:30:00+00:00",
        "timestamp_source": "test",
        "timestamp_trusted": True,
        "author_id": "latka_runtime",
        "author_label": "Łatka",
        "author_source": "jazn_runtime",
        "state_emoticon": "🌿",
        "user_text_sha256": hashlib.sha256(user_text.encode("utf-8")).hexdigest(),
        "finalization_contract_hash": HASH_A,
        "runtime_context_sha256": HASH_B,
        "daemon_request_id": request_id,
        "host_generation_policy": {},
        "host_generation_rules": [],
        "host_generation_context": {},
        "runtime_summary": {},
        "session_continuity_commit": {},
    }
    value["host_request_contract_hash"] = calculate_host_request_contract_hash(value)
    return value


def _failed_job(*, request_id: str, session_id: str, user_text: str, error_code: str = "runtime_turn_not_accepted") -> runtime_daemon.DaemonChatJob:
    job = runtime_daemon.DaemonChatJob(
        request_id=request_id,
        user_text=user_text,
        input_field="message",
        session_id=session_id,
        no_carryover=False,
        client="chatgpt_daemon_bridge",
        request_fingerprint=f"fingerprint-{request_id}",
        status="failed",
        error=error_code,
        result={"ok": False, "error_code": error_code, "request_id": request_id},
        completed_at_utc=runtime_daemon.utc_now_iso(),
    )
    job.done_event.set()
    return job


def test_consumed_durable_settlement_recovers_runtime_turn_not_accepted_job(tmp_path: Path) -> None:
    request_id = "request-v62-consumed"
    turn_id = "turn-v62-consumed"
    trace_id = "trace-v62-consumed"
    user_text = "Domknij tę samą turę po recovery."
    bridge = _bridge(request_id=request_id, turn_id=turn_id, trace_id=trace_id, user_text=user_text)
    pending = persist_pending_host_request(tmp_path, bridge)
    claim_pending_host_request(tmp_path, turn_id=turn_id, request_contract_hash=pending["request_contract_hash"])
    consume_claimed_host_request(tmp_path, turn_id=turn_id, request_contract_hash=pending["request_contract_hash"])

    server = _server(tmp_path)
    try:
        job = _failed_job(request_id=request_id, session_id="session-v62", user_text=user_text)
        server.chat_jobs[request_id] = job
        server.state.chat_job_failed_count = 1

        target, error = server.note_host_finalization(
            request_id=request_id,
            turn_id=turn_id,
            trace_id=trace_id,
            request_contract_hash=pending["request_contract_hash"],
            outcome="accepted",
            reason="host_visible_reply_finalized",
            terminal=True,
        )

        assert error is None
        assert target is job
        assert job.status == "completed"
        assert job.recovery_disposition == "durable_host_settlement_rebound_after_runtime_rejection"
        assert job.host_turn_id == turn_id
        assert job.host_trace_id == trace_id
        assert job.host_request_contract_hash == pending["request_contract_hash"]
        assert server.state.chat_job_failed_count == 0
        assert server.state.chat_job_completed_count == 1
    finally:
        server.close_sessions()
        server.server_close()


def test_pending_durable_settlement_becomes_unsettled_predecessor(tmp_path: Path) -> None:
    request_id = "request-v62-pending"
    turn_id = "turn-v62-pending"
    trace_id = "trace-v62-pending"
    user_text = "Nie przepuszczaj następnej tury przed finalizacją."
    bridge = _bridge(request_id=request_id, turn_id=turn_id, trace_id=trace_id, user_text=user_text)
    pending = persist_pending_host_request(tmp_path, bridge)

    server = _server(tmp_path)
    try:
        job = _failed_job(request_id=request_id, session_id="session-v62", user_text=user_text)
        server.chat_jobs[request_id] = job
        server.state.chat_job_failed_count = 1
        with server._chat_jobs_lock:
            predecessor = server._latest_unsettled_session_job_locked(
                session_id="session-v62",
                exclude_request_id="next-request",
            )
        assert predecessor is job
        assert job.status == runtime_daemon.DAEMON_CHAT_JOB_HOST_PENDING_STATE
        assert job.phase_result_ready() is True
        assert job.host_turn_id == turn_id
        assert job.host_request_contract_hash == pending["request_contract_hash"]
        assert server.state.chat_job_failed_count == 0
        assert server.state.chat_job_pending_count == 1
    finally:
        server.close_sessions()
        server.server_close()


def test_nonrecoverable_worker_failure_cannot_adopt_host_settlement(tmp_path: Path) -> None:
    request_id = "request-v62-hard-fail"
    turn_id = "turn-v62-hard-fail"
    trace_id = "trace-v62-hard-fail"
    user_text = "Nie maskuj prawdziwego błędu workera."
    bridge = _bridge(request_id=request_id, turn_id=turn_id, trace_id=trace_id, user_text=user_text)
    pending = persist_pending_host_request(tmp_path, bridge)

    server = _server(tmp_path)
    try:
        job = _failed_job(
            request_id=request_id,
            session_id="session-v62",
            user_text=user_text,
            error_code="runtime_worker_failed",
        )
        server.chat_jobs[request_id] = job
        server.state.chat_job_failed_count = 1
        target, error = server.note_host_finalization(
            request_id=request_id,
            turn_id=turn_id,
            trace_id=trace_id,
            request_contract_hash=pending["request_contract_hash"],
            outcome="accepted",
            reason="must_not_override_worker_failure",
            terminal=True,
        )
        assert target is job
        assert error is not None
        assert error["error_code"] == "host_finalization_job_binding_mismatch"
        assert job.status == "failed"
        assert job.error == "runtime_worker_failed"
    finally:
        server.close_sessions()
        server.server_close()


def test_reconstructed_phase1_uses_same_runtime_answer_validator_gate() -> None:
    context = build_host_generation_context(
        {
            "user_text": "Dlaczego finalizacja runtime jest niespójna?",
            "nlg_plan": {"answer_kind": "runtime_diagnostic"},
        },
        detected_intent="system_diagnostic_question",
        route="runtime_diagnostic",
        context_origin="phase1_reconstructed_compatibility",
    )
    evaluation = evaluate_host_response_candidate(
        final_text="Problem dotyczy niespójności finalizacji tury.",
        host_generation_context=context,
        used_memory_item_ids=[],
    )
    assert evaluation["runtime_validation"]["accepted"] is False
    assert evaluation["runtime_validation"]["can_show_to_user"] is False
    assert evaluation["runtime_validation_enforced"] is True
    assert evaluation["accepted"] is False
    assert evaluation["requires_repair"] is True


def test_daemon_request_reverse_lookup_fails_closed_on_ambiguous_binding(tmp_path: Path) -> None:
    request_id = "request-v62-ambiguous"
    for suffix in ("a", "b"):
        persist_pending_host_request(
            tmp_path,
            _bridge(
                request_id=request_id,
                turn_id=f"turn-v62-{suffix}",
                trace_id=f"trace-v62-{suffix}",
                user_text=f"tekst {suffix}",
            ),
        )
    with pytest.raises(HostRequestStoreError, match="daemon_request_binding_ambiguous"):
        host_request_lifecycle_by_daemon_request_id(
            tmp_path,
            daemon_request_id=request_id,
        )


def test_recoverable_failed_job_survives_daemon_restart_and_rebinds(tmp_path: Path) -> None:
    request_id = "request-v62-restart"
    turn_id = "turn-v62-restart"
    trace_id = "trace-v62-restart"
    user_text = "Zachowaj settlement przez restart daemona."
    bridge = _bridge(request_id=request_id, turn_id=turn_id, trace_id=trace_id, user_text=user_text)
    persist_pending_host_request(tmp_path, bridge)

    first = _server(tmp_path)
    try:
        job = _failed_job(request_id=request_id, session_id="session-v62-restart", user_text=user_text)
        first.chat_jobs[request_id] = job
        first.state.chat_job_failed_count = 1
        with first._chat_jobs_lock:
            assert first._persist_chat_jobs_locked(stage="test_recoverable_failed_restart") is True
    finally:
        first.close_sessions()
        first.server_close()

    second = _server(tmp_path)
    try:
        recovered = second.chat_jobs.get(request_id)
        assert recovered is not None
        assert recovered.status == runtime_daemon.DAEMON_CHAT_JOB_HOST_PENDING_STATE
        assert recovered.host_turn_id == turn_id
        assert recovered.host_trace_id == trace_id
        assert recovered.recovery_disposition == "durable_host_settlement_rebound_after_runtime_rejection"
        assert recovered.phase_result_ready() is True
    finally:
        second.close_sessions()
        second.server_close()
