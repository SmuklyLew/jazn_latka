from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from latka_jazn.core.daemon_autostart import status_allows_runtime_turn
from latka_jazn.core.epistemic_decision_ledger import EpistemicDecisionLedger
from latka_jazn.db.runtime_sqlite import runtime_sqlite_journal_mode


SAMPLE_ISO = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc).isoformat()
HEADER = "🕒 2026-08-26 12:00:00"


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


class _PersistentHostPendingSession:
    def __init__(self, _config, **kwargs) -> None:
        self.state = SimpleNamespace(session_id=kwargs.get("session_id"))

    def process_user_text(self, user_text: str, **_kwargs) -> dict:
        return deepcopy(_host_pending_result(user_text))

    def close(self) -> None:
        return None


def _server(root: Path) -> runtime_daemon.JaznDaemonServer:
    resolved = root.resolve()
    return runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0),
        runtime_daemon.JaznDaemonHandler,
        config=JaznConfig(root=resolved),
        marker_path=resolved / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        session_factory=_PersistentHostPendingSession,
        execution_timeout_seconds=15.0,
    )


def _submit(server: runtime_daemon.JaznDaemonServer, request_id: str):
    job, created, error = server.submit_chat_job(
        user_text=request_id,
        input_field="message",
        session_id="session-v1636",
        no_carryover=False,
        client="chatgpt_daemon_bridge",
        request_id=request_id,
    )
    assert created is True and error is None and job is not None
    assert job.done_event.wait(20.0)
    assert job.status == "awaiting_host_finalization", repr(job.result)
    assert job.host_turn_id
    assert job.host_trace_id
    assert job.host_request_contract_hash
    return job


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


def test_degraded_daemon_requires_confirmed_endpoint_identity_and_fresh_heartbeat() -> None:
    assert status_allows_runtime_turn({"active_state": "active_trusted"}) is True
    assert status_allows_runtime_turn(
        {
            "active_state": "active_degraded",
            "active_state_reason": "endpoint_runtime_identity_confirmed",
        }
    ) is True

    for reason in (
        "endpoint_identity_confirmed_heartbeat_stale",
        "fresh_marker_and_live_pid_endpoint_unreachable",
        "unknown_future_degradation",
        "",
    ):
        assert status_allows_runtime_turn(
            {"active_state": "active_degraded", "active_state_reason": reason}
        ) is False


def test_epistemic_ledger_uses_canonical_runtime_journal_policy(tmp_path: Path) -> None:
    path = tmp_path / "workspace_runtime" / "epistemic_decisions.sqlite3"
    with EpistemicDecisionLedger(path) as ledger:
        mode = str(ledger.con.execute("PRAGMA journal_mode").fetchone()[0]).upper()
        assert mode == runtime_sqlite_journal_mode()
        ledger.append_assessments(
            turn_id="turn-v1636",
            trace_id="trace-v1636",
            assessments=[
                {
                    "kind": "runtime_presence",
                    "status": "supported",
                    "matched_text": "runtime działa",
                    "reason": "test",
                    "required_evidence": [],
                    "evidence_snapshot": {"daemon_verified": True},
                }
            ],
        )
        assert ledger.validate_chain()["ok"] is True


def test_host_finalization_does_not_end_liveness_and_pending_turn_recovers_after_restart(
    tmp_path: Path,
) -> None:
    first = _server(tmp_path)
    try:
        first_job = _submit(first, "request-v1636-first")
        _accept(first, first_job)

        # A completed host-finalized turn must not retire the dialogue daemon.
        second_job = _submit(first, "request-v1636-second")
        assert first.chat_job_summary()["awaiting_host_finalization"] == 1
    finally:
        first.close_sessions()
        first.server_close()

    second = _server(tmp_path)
    try:
        recovered = second.get_chat_job(second_job.request_id)
        assert recovered is not None
        assert recovered.status == "awaiting_host_finalization"
        assert recovered.recovery_disposition == "host_finalization_pending_recovered"
        _accept(second, recovered)

        # Recovery/finalization must leave the replacement daemon able to accept
        # another turn in the same logical session.
        third_job = _submit(second, "request-v1636-third")
        assert third_job.status == "awaiting_host_finalization"
        assert second.chat_job_summary()["terminal_failure_total"] == 0
    finally:
        second.close_sessions()
        second.server_close()
