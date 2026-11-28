"""Executor selection survives rejection and truth-gate projection."""
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.core.chat_command_contract import chatgpt_result_requires_host_visible_reply
from latka_jazn.core.conversation_runner import _host_finalization_pending
from latka_jazn.core.model_transport_failure import terminal_model_failure


@pytest.mark.parametrize("executor", ["local_model", "unavailable", "external_model", "host_bridge"])
def test_complete_phase_one_fields_respect_selected_executor(executor: str) -> None:
    result: dict[str, Any] = {
        "conversation_decision": {
            "model_executor_preflight": {"executor": executor, "available": True},
            "requires_host_model": True,
        },
        "final_response_contract": {
            "requires_host_model": True, "fallback_classification": "cannot_answer_directly",
            "turn_id": "turn", "trace_id": "trace", "timestamp_header": "header",
            "timezone": "UTC", "timestamp_sample_iso": "2026-11-28T12:00:00Z",
            "timestamp_source": "test", "timestamp_trusted": True,
            "author_id": "a", "author_label": "a", "author_source": "canon", "state_emoticon": "ok",
        },
    }
    assert _host_finalization_pending(result, can_continue=True) == (executor == "host_bridge", [])
    assert chatgpt_result_requires_host_visible_reply(result) is (executor == "host_bridge")


def test_semantic_failure_keeps_last_rejection_without_exposing_candidate() -> None:
    decision: dict[str, Any] = {
        "model_executor_preflight": {"executor": "local_model"},
        "model_generated": False,
        "fallback_classification": "cannot_answer_directly",
        "model_guided_retry_synthesis": {
            "used": False,
            "adapter_response": {
                "adapter_id": "local_llm_adapter", "generated": True, "provider": "ollama",
                "status": "completed", "text": "PRIVATE CANARY",
            },
            "candidate_evaluations": [{"source": "model_adapter", "accepted": False,
                                       "violations": ["memory_claim_without_allowed_memory_payload"]}],
        },
    }
    failure = terminal_model_failure(decision)
    assert failure is not None
    assert failure["error_code"] == "model_candidate_rejected"
    assert "memory_claim_without_allowed_memory_payload" in failure["violations"]
    assert "CANARY" not in repr(failure)
    decision["model_generated"] = True
    assert terminal_model_failure(decision) is None

@pytest.mark.parametrize(("command", "client", "state", "code"), [
    ("--chat-ollama", "ollama_terminal_one_shot", "failed", "host_executor_not_authorized"),
    ("--chat-ollama", "secure_mcp_gateway", "failed", "host_executor_not_authorized"),
    ("--chat-gpt", "chatgpt_daemon_bridge", "host_finalization_rejected", "host_finalization_contract_not_persisted"),
])
def test_daemon_settles_contradictory_worker_result_on_admitted_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, client: str, state: str, code: str,
) -> None:
    import json
    from latka_jazn.config import JaznConfig
    from latka_jazn.core import runtime_daemon as daemon
    from latka_jazn.core import chat_command_contract as bridge

    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), daemon.JaznDaemonHandler,
        config=JaznConfig(root=tmp_path, memory_mode="off"),
        marker_path=tmp_path / "workspace_runtime/JAZN_ACTIVE_RUNTIME.json",
        hard_worker_process_isolation=False,
    )
    monkeypatch.setattr(server, "start_chat_worker", lambda: None)
    monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
    calls = []
    def attach(*args: Any, **kwargs: Any) -> None:
        calls.append("bridge")
    monkeypatch.setattr(bridge, "attach_chatgpt_host_contract", attach)
    worker = SimpleNamespace(state=SimpleNamespace(session_id="session"),
                             process_user_text=lambda *a, **k: {"ok": True, "host_finalization_pending": True})
    monkeypatch.setattr(server, "get_session", lambda *a, **k: (worker, "test"))
    monkeypatch.setattr(server, "write_marker", lambda: {})
    try:
        job, created, error = server.submit_chat_job(request_id="synthetic-bound", user_text="test",
                client=client, command=command, session_id="session", no_carryover=False, input_field="message")
        assert job and created and not error
        server._process_chat_job(job)
        assert job.status == state and job.error == code
        row, = json.loads(server._chat_state_path.read_text(encoding="utf-8"))["jobs"]
        assert (row["status"], row["error"], row["host_request_contract_hash"]) == (state, code, None)
        assert calls == (["bridge"] if command == "--chat-gpt" else [])
    finally:
        server.close_sessions()
        server.server_close()
