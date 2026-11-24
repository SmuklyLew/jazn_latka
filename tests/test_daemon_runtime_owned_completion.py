from __future__ import annotations

from typing import Any

import pytest

import main as main_module
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text


def _runtime_owned_result(command: str = "--chat-ollama") -> dict[str, Any]:
    text = "Synthetic verified runtime reply"
    return {
        "ok": True,
        "answer_ok": True,
        "execution_state": "final_visible_answer",
        "host_finalization_pending": False,
        "host_visible_finalization": None,
        "canonical_persistence_ok": True,
        "final_visible_text": text,
        "final_visible_integrity": {
            "valid": True,
            "consensus": True,
            "message_envelope_valid": True,
            "text_sha256": sha256_host_visible_text(text),
        },
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": True},
        "final_response_contract": {
            "author_source": "jazn_runtime",
            "requires_host_model": False,
            "fallback_classification": "not_fallback",
        },
        "conversation_state_persistence": {
            "ok": True, "record_sha256": "a" * 64,
            "session_id": "synthetic-session", "turn_id": "turn", "trace_id": "trace",
        },
        "trace": {"turn_id": "turn", "trace_id": "trace"},
        "daemon": {"request_id": "request"},
        "daemon_job": {
            "job_status": "completed", "done": True, "command": command,
            "client": "runtime_owned_test",
            "request_id": "request", "session_id": "synthetic-session",
            "awaiting_host_finalization": False, "phase_result_ready": False,
            "host_finalization_gate_state": "not_required",
            "host_finalization_attempt_count": 0,
            "host_request_contract_hash": None,
            "host_turn_id": None, "host_trace_id": None,
            "host_finalization_error_code": None,
        },
    }


@pytest.mark.parametrize("command", ["--chat-ollama", "--chat-open-ai"])
@pytest.mark.parametrize("classification", ["not_fallback", "rule_handler_response"])
def test_runtime_owned_finalization_uses_runtime_evidence(
    command: str, classification: str,
) -> None:
    payload = _runtime_owned_result(command)
    payload["final_response_contract"]["fallback_classification"] = classification
    observed = main_module._daemon_cli_completion(payload)
    assert observed["finalized_successfully"] is True
    assert observed["finalization"] == "accepted"


@pytest.mark.parametrize(("section", "field", "value"), [
    (None, "canonical_persistence_ok", False),
    (None, "answer_ok", False),
    (None, "final_visible_text", "tampered"),
    (None, "host_visible_finalization", {"status": "rejected"}),
    (None, "chatgpt_host_bridge", {"phase": "host_visible_generation_requested"}),
    ("final_visible_integrity", "valid", False),
    ("final_visible_integrity", "consensus", False),
    ("final_visible_integrity", "message_envelope_valid", False),
    ("final_visible_integrity", "text_sha256", "bad"),
    ("runtime_truth_gate", "normal_response_allowed", False),
    ("final_response_contract", "author_source", "chatgpt_host"),
    ("final_response_contract", "requires_host_model", True),
    ("conversation_state_persistence", "ok", False),
    ("conversation_state_persistence", "record_sha256", "g" * 64),
    ("conversation_state_persistence", "trace_id", "wrong-trace"),
    ("conversation_state_persistence", "turn_id", "wrong-turn"),
    ("conversation_state_persistence", "session_id", "wrong-session"),
    ("daemon", "request_id", "wrong-request"),
    ("daemon_job", "phase_result_ready", True),
    ("daemon_job", "awaiting_host_finalization", True),
    ("daemon_job", "host_finalization_attempt_count", False),
    ("daemon_job", "host_finalization_attempt_count", 1),
    ("daemon_job", "host_request_contract_hash", "phase-1"),
    ("daemon_job", "host_turn_id", "host-turn"),
    ("daemon_job", "host_finalization_gate_state", "failed"),
    ("daemon_job", "command", "--chat-gpt"),
    ("daemon_job", "command", "--chat"),
    ("daemon_job", "client", "chatgpt_daemon_bridge"),
    ("daemon_job", "client", "secure_mcp_gateway"),
])
def test_runtime_owned_completion_rejects_missing_or_conflicting_evidence(
    section: str | None, field: str, value: Any,
) -> None:
    payload = _runtime_owned_result()
    target = payload if section is None else payload[section]
    target[field] = value
    observed = main_module._daemon_cli_completion(payload)
    assert observed["finalized_successfully"] is False
    assert observed["finalization"] == "completed_job_unverified"


def test_runtime_owned_completion_does_not_replace_host_phase_two() -> None:
    payload = _runtime_owned_result()
    payload["daemon_job"].update(
        command="--chat-gpt", client="chatgpt_daemon_bridge",
        job_status="awaiting_host_finalization", done=False,
        phase_result_ready=True, awaiting_host_finalization=True,
    )
    payload["host_finalization_pending"] = True
    payload["execution_state"] = "host_visible_generation_requested"
    observed = main_module._daemon_cli_completion(payload)
    assert observed["finalization"] == "awaiting_host"
    assert observed["finalized_successfully"] is False
