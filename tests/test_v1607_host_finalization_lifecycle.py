from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TypedDict

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from latka_jazn.core.chatgpt_host_pending_store import (
    claim_pending_host_request,
    cleanup_expired_host_requests,
    consume_claimed_host_request,
    issue_continuation_token,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.core.host_response_candidate_guard import (
    build_host_generation_context,
    evaluate_host_response_candidate,
    validate_host_generation_context,
)
from latka_jazn.core.full_canon_model_context import build_full_canon_model_context
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.model_adapters.chatgpt_runtime_adapter import ChatgptRuntimeAdapter
from latka_jazn.mcp.tools import jazn_finalize_reply


SAMPLE_ISO = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc).isoformat()
HEADER = "🕒 2026-08-23 20:00:00"


def _phase_one_result(suffix: str = "v1607") -> dict:
    safe_suffix = suffix.replace(" ", "-")
    return {
        "ok": True,
        "host_finalization_pending": True,
        "execution_state": "awaiting_host_finalization",
        "runtime_version": "test-version",
        "trace": {
            "turn_id": f"turn-{safe_suffix}",
            "trace_id": f"trace-{safe_suffix}",
            "timestamp_header": HEADER,
            "timezone": "Europe/Warsaw",
        },
        "conversation_decision": {
            "handler_name": "RuntimeTurnTruthGate",
            "route": "greeting",
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
            "turn_id": f"turn-{safe_suffix}",
            "trace_id": f"trace-{safe_suffix}",
            "handler_name": "RuntimeTurnTruthGate",
            "requires_host_model": True,
            "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": f"turn-{safe_suffix}",
            "trace_id": f"trace-{safe_suffix}",
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


class _HostPendingSession:
    def __init__(self, _config, **kwargs) -> None:
        self.state = SimpleNamespace(session_id=kwargs.get("session_id"))

    def process_user_text(self, user_text: str, **_kwargs) -> dict:
        return deepcopy(_phase_one_result(user_text))

    def close(self) -> None:
        return None


def _server(root: Path) -> runtime_daemon.JaznDaemonServer:
    return runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0),
        runtime_daemon.JaznDaemonHandler,
        config=JaznConfig(root=root.resolve()),
        marker_path=root.resolve() / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        session_factory=_HostPendingSession,
        execution_timeout_seconds=15.0,
    )


def _phase_one(server: runtime_daemon.JaznDaemonServer, request_id: str = "request-v1607"):
    job, created, error = server.submit_chat_job(
        user_text=request_id,
        input_field="message",
        session_id="session-v1607",
        no_carryover=False,
        client="chatgpt_daemon_bridge",
        request_id=request_id,
    )
    assert created is True and error is None and job is not None
    assert job.done_event.wait(20.0)
    assert job.status == "awaiting_host_finalization", repr(job.result)
    assert job.phase_result_ready() is True
    return job


class _HostJobBinding(TypedDict):
    request_id: str
    turn_id: str
    trace_id: str
    request_contract_hash: str


def _binding(job: runtime_daemon.DaemonChatJob) -> _HostJobBinding:
    return {
        "request_id": job.request_id,
        "turn_id": str(job.host_turn_id),
        "trace_id": str(job.host_trace_id),
        "request_contract_hash": str(job.host_request_contract_hash),
    }


def test_phase_one_waits_without_terminal_failure_and_phase_two_completes(tmp_path: Path) -> None:
    server = _server(tmp_path)
    try:
        job = _phase_one(server)
        before = server.chat_job_summary()
        assert before["awaiting_host_finalization"] == 1
        assert before["completed_total"] == 0
        assert before["terminal_failure_total"] == 0
        assert job.result is not None
        bridge = job.result["chatgpt_host_bridge"]
        assert bridge["daemon_request_id"] == job.request_id
        assert bridge["turn_id"] == job.host_turn_id
        assert bridge["trace_id"] == job.host_trace_id
        assert bridge["host_request_contract_hash"] == job.host_request_contract_hash
        assert bridge["pending_request_persisted"] is True

        completed, error = server.note_host_finalization(
            **_binding(job),
            outcome="accepted",
            reason="host_visible_reply_finalized",
            terminal=True,
        )
        assert error is None and completed is job
        after = server.chat_job_summary()
        assert job.status == "completed"
        assert after["completed_total"] == 1
        assert after["terminal_failure_total"] == 0
    finally:
        server.close_sessions()
        server.server_close()


def test_expired_hash_replay_and_terminal_rejection_have_distinct_telemetry(tmp_path: Path) -> None:
    server = _server(tmp_path)
    try:
        hash_job = _phase_one(server, "request-hash")
        server.note_host_finalization(
            **_binding(hash_job), outcome="hash_rejected", reason="final_text_sha256_mismatch"
        )
        assert hash_job.status == "awaiting_host_finalization"
        assert server.state.chat_job_host_finalization_hash_rejected_count == 1

        rejected, error = server.note_host_finalization(
            **_binding(hash_job), outcome="rejected", reason="candidate_rejected", terminal=True
        )
        assert error is None and rejected is hash_job
        assert hash_job.status == "host_finalization_rejected"

        replay_job = _phase_one(server, "request-replay")
        server.note_host_finalization(
            **_binding(replay_job), outcome="accepted", reason="accepted", terminal=True
        )
        server.note_host_finalization(
            **_binding(replay_job), outcome="replay_rejected", reason="host_request_replay_detected"
        )
        assert replay_job.status == "completed"
        assert server.state.chat_job_host_finalization_replay_rejected_count == 1

        expired_job = _phase_one(server, "request-expired")
        cleanup_expired_host_requests(
            tmp_path,
            now=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        assert server.get_chat_job(expired_job.request_id) is expired_job
        assert expired_job.status == "host_finalization_expired"

        summary = server.chat_job_summary()
        assert summary["host_finalization_rejected_total"] == 1
        assert summary["host_finalization_expired_total"] == 1
        assert summary["terminal_failure_total"] == 2
    finally:
        server.close_sessions()
        server.server_close()


def test_pending_host_job_recovers_after_daemon_restart_and_reconciles_consumption(tmp_path: Path) -> None:
    first = _server(tmp_path)
    job = _phase_one(first, "request-restart")
    binding = _binding(job)
    first.close_sessions()
    first.server_close()

    second = _server(tmp_path)
    try:
        recovered = second.get_chat_job(job.request_id)
        assert recovered is not None
        assert recovered.status == "awaiting_host_finalization"
        assert recovered.recovery_disposition == "host_finalization_pending_recovered"
        claimed = claim_pending_host_request(
            tmp_path,
            turn_id=binding["turn_id"],
            request_contract_hash=binding["request_contract_hash"],
        )
        assert claimed["state"] == "claimed"
        consume_claimed_host_request(
            tmp_path,
            turn_id=binding["turn_id"],
            request_contract_hash=binding["request_contract_hash"],
        )
        reconciled = second.get_chat_job(job.request_id)
        assert reconciled is not None and reconciled.status == "completed"
        assert second.chat_job_summary()["terminal_failure_total"] == 0
    finally:
        second.close_sessions()
        second.server_close()


def test_host_candidate_guard_rejects_undeclared_memory_source() -> None:
    context = build_host_generation_context(
        {
            "user_text": "Co pamiętasz?",
            "nlg_plan": {"memory_policy": "required_grounded_payload"},
            "allowed_memory_items": [
                {
                    "item_id": "allowed-1",
                    "excerpt": "Zweryfikowany fragment.",
                    "source": "verified_memory",
                }
            ],
        },
        detected_intent="self_memory_recall",
        route="self_memory_recall",
    )
    evaluation = evaluate_host_response_candidate(
        final_text="Pamiętam ten fragment.",
        host_generation_context=context,
        used_memory_item_ids=["unauthorized-2"],
    )
    assert evaluation["accepted"] is False
    assert "used_memory_id_not_in_host_context" in evaluation["violations"]


def test_host_generation_context_is_bounded_sanitized_and_hash_bound() -> None:
    context = build_host_generation_context(
        {
            "user_text": "Jak się dzisiaj czujesz?",
            "nlg_plan": {"answer_kind": "natural_dialogue"},
            "allowed_memory_items": [
                {
                    "item_id": "memory-1",
                    "excerpt": "Rozmowa o spacerze po deszczu.",
                    "source": "episodic_memory",
                    "raw_sqlite_row": "MUST_NOT_CROSS_THE_BRIDGE",
                    "secret": "MUST_NOT_CROSS_THE_BRIDGE",
                }
            ],
        },
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
    )
    assert validate_host_generation_context(context) is True
    assert context["allowed_memory_item_ids"] == ["memory-1"]
    assert "MUST_NOT_CROSS_THE_BRIDGE" not in str(context)

    tampered = deepcopy(context)
    tampered["current_turn"]["route"] = "tampered"
    assert validate_host_generation_context(tampered) is False


def test_host_candidate_rejects_undeclared_memory_claim_and_runtime_template() -> None:
    context = build_host_generation_context(
        {
            "user_text": "Co pamiętasz?",
            "nlg_plan": {
                "answer_kind": "natural_dialogue",
                "memory_policy": "required_grounded_payload",
            },
            "full_canon_model_context": build_full_canon_model_context(),
            "allowed_memory_items": [
                {
                    "item_id": "memory-1",
                    "excerpt": "Rozmowa o spacerze po deszczu.",
                    "source": "episodic_memory",
                }
            ],
        },
        detected_intent="memory_experience_question",
        route="ordinary_dialogue",
    )
    unbound = evaluate_host_response_candidate(
        final_text="Pamiętam naszą rozmowę o spacerze po deszczu.",
        host_generation_context=context,
        used_memory_item_ids=[],
    )
    assert unbound["accepted"] is False
    assert "model_memory_claim_without_declared_used_memory_ids" in unbound["violations"]

    template = evaluate_host_response_candidate(
        final_text="Jestem przy Tobie. Możemy spokojnie iść dalej.",
        host_generation_context=context,
        used_memory_item_ids=[],
    )
    assert template["accepted"] is False
    assert "known_runtime_template" in template["violations"]


def test_chatgpt_synthesizer_produces_host_context_without_runtime_draft() -> None:
    synthesis = ModelGuidedResponseSynthesizer().synthesize(
        adapter=ChatgptRuntimeAdapter(),
        user_text="Jak się dzisiaj czujesz?",
        draft_body="Stała formułka handlera.",
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
        cognitive_frame={},
        response_policy={"exact_runtime_required": False},
    )
    assert synthesis.status == "host_visible_generation_requested"
    assert synthesis.host_generation_context is not None
    assert synthesis.host_generation_context["model_context"]["user_text"] == "Jak się dzisiaj czujesz?"
    assert "Stała formułka handlera." not in str(synthesis.host_generation_context)


def test_mcp_phase_two_completes_the_same_daemon_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server(tmp_path)
    try:
        job = _phase_one(server, "request-mcp-finalize")
        issued = issue_continuation_token(
            tmp_path,
            turn_id=str(job.host_turn_id),
            request_contract_hash=str(job.host_request_contract_hash),
        )

        class _FakeEngine:
            def __init__(self, _config) -> None:
                return None

            def shutdown(self) -> None:
                return None

            def persist_final_visible_reply(self, **kwargs):
                return {
                    "final_visible_text": kwargs["final_text"],
                    "turn_id": kwargs["turn_id"],
                    "trace_id": kwargs["trace_id"],
                }

        class _LifecycleGateway:
            def note_host_finalization(self, pending, *, outcome, reason, terminal=False):
                binding = pending["binding"]
                target, error = server.note_host_finalization(
                    request_id=binding["daemon_request_id"],
                    turn_id=binding["turn_id"],
                    trace_id=binding["trace_id"],
                    request_contract_hash=pending["request_contract_hash"],
                    outcome=outcome,
                    reason=reason,
                    terminal=terminal,
                )
                assert error is None and target is job
                assert target is not None
                return target.snapshot(include_result=False)

        import latka_jazn.core.engine as engine_module

        monkeypatch.setattr(engine_module, "JaznEngine", _FakeEngine)
        body = "Jestem tutaj przy tej turze."
        finalized = jazn_finalize_reply.run(
            root=tmp_path,
            continuation_token=issued["continuation_token"],
            final_text=body,
            final_text_sha256=sha256_host_visible_text(body),
            lifecycle_gateway=_LifecycleGateway(),
        )
        assert finalized["structuredContent"]["accepted"] is True
        assert finalized["structuredContent"]["daemon_job_lifecycle"]["job_status"] == "completed"
        assert job.status == "completed"
        assert server.chat_job_summary()["terminal_failure_total"] == 0
    finally:
        server.close_sessions()
        server.server_close()
