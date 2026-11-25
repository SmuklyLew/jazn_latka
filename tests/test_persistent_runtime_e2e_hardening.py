from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import sys
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


# Run the real daemon job loop in two separate OS processes.  Thread-backed
# session workers are intentional in this fixture; full CLI/public MCP and
# hard-isolated worker lifecycle acceptance remain separate gates.
_DAEMON_CONTINUITY_CHILD = r'''
import json
import os
import sys
from pathlib import Path
from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon import JaznDaemonServer, JaznDaemonHandler
from latka_jazn.core.conversation_state_store import ConversationStateStore

root = Path(sys.argv[1])
phase = sys.argv[2]
output = Path(sys.argv[3])
session = "stage04-process-continuity"
server = JaznDaemonServer(
    ("127.0.0.1", 0), JaznDaemonHandler,
    config=JaznConfig(root=root, memory_mode="off"),
    marker_path=root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
    hard_worker_process_isolation=False,
    execution_timeout_seconds=60,
)
try:
    text = ("Jaka jest godzina?" if phase == "first" else
            "Zacytuj pierwszych trzech słów mojej poprzedniej wiadomości.")
    args = dict(user_text=text, input_field="message", session_id=session,
                no_carryover=False, client="daemon_http", request_id="stage04-" + phase)
    if phase == "resumed":
        # The first process already committed this request. A second process
        # must never execute it again, even though no visible result is kept
        # in the metadata-only daemon recovery ledger.
        previous_args = dict(args)
        previous_args["user_text"] = "Jaka jest godzina?"
        previous_args["request_id"] = "stage04-first"
        recovered, created, error = server.submit_chat_job(**previous_args)
        assert error is None and created is False and recovered is not None
        assert recovered.status == "recovered_after_restart"
        assert recovered.error == "completed_request_result_unavailable"
        assert recovered.result is not None
        assert recovered.result["automatic_replay_performed"] is False
        assert recovered.result["ok"] is False
        assert "final_visible_text" not in recovered.result
        conflict_args = dict(previous_args)
        conflict_args["user_text"] = "Different input for same request ID"
        conflicted, created, error = server.submit_chat_job(**conflict_args)
        assert conflicted is None and created is False
        assert error is not None and error["error_code"] == "request_id_conflict"
        assert ConversationStateStore(root).load_context_projection(session)["total_turn_count"] == 1
    job, created, error = server.submit_chat_job(**args)
    assert created is True and error is None and job is not None
    assert job.done_event.wait(90), "daemon job did not settle"
    assert job.status == "completed", repr(job.result)
    result = job.result
    assert isinstance(result, dict)
    assert result["answer_ok"] is True
    assert result["canonical_persistence_ok"] is True
    assert result["conversation_state_persistence"]["ok"] is True
    assert result["session_persistence_ok"] is True
    # Same request in the same process must not append another accepted turn.
    again, duplicate_created, duplicate_error = server.submit_chat_job(**args)
    assert duplicate_error is None and duplicate_created is False and again is job
    store = ConversationStateStore(root)
    history = store.load_context_projection(session)
    assert history["invalid_record_count"] == 0
    assert store.load_context_projection("stage04-foreign-session")["turns"] == []
    report = {
        "pid": os.getpid(),
        "instance": server.daemon_instance_id,
        "session": result["session"]["session_id"],
        "turn_id": result["trace"]["turn_id"],
        "trace_id": result["trace"]["trace_id"],
        "body": result["conversation_decision"]["body"],
        "provenance": result["session_provenance"],
        "history_count": history["total_turn_count"],
        "first_record": store.lookup_accepted_turn(session, selector="first")["record"],
    }
finally:
    server.close_sessions()
    server.server_close()
output.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
'''


def test_real_daemon_job_loop_continues_session_across_os_processes(tmp_path: Path) -> None:
    root = tmp_path / "system"
    root.mkdir()
    (root / "main.py").write_text("# isolated daemon fixture\n", encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith("JAZN_")}
    env.update({
        "JAZN_RUNTIME_WORKSPACE_DIR": str(root / "workspace_runtime"),
        "JAZN_MEMORY_ROOT": str(root / "memory"),
        "JAZN_MEMORY_MODE": "off",
        "JAZN_MODEL_ADAPTER": "null",
        "JAZN_LLM_ROUTE": "off",
        "JAZN_NETWORK_TIME_FIRST": "0",
        "JAZN_NETWORK_TIME_IN_TURN": "0",
        "JAZN_ALLOW_NETWORK": "0",
        "JAZN_DICTIONARY_ALLOW_NETWORK": "0",
        "JAZN_MEMORY_SYNC_MODE": "off",
    })
    project = Path(__file__).resolve().parents[1]

    def run(phase: str) -> dict:
        output = tmp_path / (phase + ".json")
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", _DAEMON_CONTINUITY_CHILD,
             str(root), phase, str(output)],
            cwd=project, env=env, capture_output=True, text=True,
            encoding="utf-8", timeout=120, check=False,
        )
        assert completed.returncode == 0, completed.stderr[-4000:] + completed.stdout[-4000:]
        assert output.is_file()
        return json.loads(output.read_text(encoding="utf-8"))

    first = run("first")
    assert first["provenance"]["session_loaded_from"] == "new"
    assert first["provenance"]["session_reused"] is False
    assert first["history_count"] == 1
    # Use the actual durable checkpoint AFTER the first child has exited.
    checkpoint_files = list((root / "workspace_runtime" / "runtime_sessions").glob("*.json"))
    assert len(checkpoint_files) == 1
    checkpoint = json.loads(checkpoint_files[0].read_text(encoding="utf-8"))
    assert checkpoint["session_id"] == first["session"]
    assert checkpoint["last_user_text"] == "Jaka jest godzina?"
    expected_sha = checkpoint["_continuity"]["checkpoint_sha256"]

    second = run("resumed")
    # Independently constructed daemon instance and actual subprocess exit.
    assert first["instance"] != second["instance"]
    assert first["pid"] > 0 and second["pid"] > 0
    assert first["session"] == second["session"]
    assert first["turn_id"] != second["turn_id"]
    assert first["trace_id"] != second["trace_id"]
    assert second["history_count"] == 2
    assert second["first_record"] == first["first_record"]
    assert second["body"] == "Jaka jest godzina?"
    resumed = second["provenance"]
    assert resumed["session_loaded_from"] == "session_checkpoint"
    assert resumed["session_reused"] is True
    assert resumed["session_resurrected_from_disk"] is True
    assert resumed["session_reuse_evidence"] == "checkpoint_matches_accepted_history"
    assert resumed["session_input_checkpoint_sha256"] == expected_sha
    assert resumed["session_prior_accepted_turn_id"] == first["turn_id"]
    assert resumed["session_prior_accepted_trace_id"] == first["trace_id"]
    assert resumed["continuity_checkpoint_sha256"] != expected_sha


def test_interrupted_host_finalization_restarts_without_replay_or_false_acceptance(
    tmp_path: Path,
) -> None:
    """A lost phase-2 acknowledgement is not permission to submit again."""
    from latka_jazn.core.conversation_state_store import ConversationStateStore

    request_id = "stage04-interrupted-finalization"
    first = _server(tmp_path)
    try:
        pending = _submit(first, request_id)
        original_binding = (
            pending.host_turn_id,
            pending.host_trace_id,
            pending.host_request_contract_hash,
        )
        mismatched, error = first.note_host_finalization(
            request_id=request_id,
            turn_id=str(pending.host_turn_id),
            trace_id=str(pending.host_trace_id),
            request_contract_hash="f" * 64,
            outcome="accepted",
            reason="simulated_lost_client_binding",
            terminal=True,
        )
        assert mismatched is pending
        assert error is not None
        assert error["error_code"] == "host_finalization_job_binding_mismatch"
        assert pending.status == "awaiting_host_finalization"
        assert ConversationStateStore(tmp_path).load_context_projection("session-v1636")[
            "total_turn_count"
        ] == 0
    finally:
        first.close_sessions()
        first.server_close()

    restarted = _server(tmp_path)
    try:
        recovered = restarted.get_chat_job(request_id)
        assert recovered is not None
        assert recovered.status == "awaiting_host_finalization"
        assert (
            recovered.host_turn_id,
            recovered.host_trace_id,
            recovered.host_request_contract_hash,
        ) == original_binding
        duplicate, created, error = restarted.submit_chat_job(
            user_text=request_id, input_field="message", session_id="session-v1636",
            no_carryover=False, client="chatgpt_daemon_bridge",
            request_id=request_id,
        )
        assert duplicate is recovered and created is False and error is None
        assert recovered.result is not None
        assert recovered.result["automatic_replay_performed"] is False
        assert ConversationStateStore(tmp_path).load_context_projection("session-v1636")[
            "total_turn_count"
        ] == 0
        _accept(restarted, recovered)
        assert recovered.status == "completed"
        # The daemon ACK does not by itself create accepted visible content.
        assert ConversationStateStore(tmp_path).load_context_projection("session-v1636")[
            "total_turn_count"
        ] == 0
        again, created, error = restarted.submit_chat_job(
            user_text=request_id, input_field="message", session_id="session-v1636",
            no_carryover=False, client="chatgpt_daemon_bridge",
            request_id=request_id,
        )
        assert again is recovered and created is False and error is None
    finally:
        restarted.close_sessions()
        restarted.server_close()
