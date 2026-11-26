"""F03: verify the actual /chat-result snapshot shape without finalizing again."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

import main as main_module
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.core.runtime_daemon import DaemonChatJob


def _snapshot(command: str = "--chat-ollama") -> dict[str, Any]:
    text = "Synthetic accepted runtime-owned answer"
    result = {
        "ok": True, "answer_ok": True, "execution_state": "final_visible_answer",
        "host_finalization_pending": False, "host_visible_finalization": None,
        "canonical_persistence_ok": True, "final_visible_text": text,
        "final_visible_integrity": {
            "valid": True, "consensus": True, "message_envelope_valid": True,
            "text_sha256": sha256_host_visible_text(text),
        },
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": True},
        "final_response_contract": {
            "author_source": "jazn_runtime", "requires_host_model": False,
            "fallback_classification": "not_fallback",
        },
        "conversation_state_persistence": {
            "ok": True, "record_sha256": "a" * 64, "session_id": "synthetic-session",
            "turn_id": "synthetic-turn", "trace_id": "synthetic-trace",
        },
        "trace": {"turn_id": "synthetic-turn", "trace_id": "synthetic-trace"},
        "daemon": {"request_id": "synthetic-request", "daemon_instance_id": "synthetic-instance"},
    }
    job = DaemonChatJob(
        request_id="synthetic-request", user_text="synthetic", input_field="message",
        session_id="synthetic-session", no_carryover=False, client="runtime_owned_test",
        command=command, status="completed", result=result,
    )
    job.done_event.set()
    return {**job.snapshot(include_result=True), "daemon_instance_id": "synthetic-instance"}


@pytest.mark.parametrize("command", ["--chat-ollama", "--chat-open-ai"])
def test_completed_poll_projects_runtime_owned_evidence_without_mutation(command: str) -> None:
    payload = _snapshot(command)
    before = deepcopy(payload)
    completion = main_module._daemon_cli_completion(payload)
    assert completion["finalization"] == "accepted"
    assert completion["finalized_successfully"] is True
    assert completion["phase_result_ready"] is False
    assert completion["finalization_evidence_source"] == "runtime_owned_poll"
    assert payload == before
    flat = {**payload["result"], "daemon_job": payload}
    projected = main_module._daemon_cli_completion(flat)
    assert projected["finalized_successfully"] is True
    assert projected["finalization_evidence_source"] == "runtime_owned_result"


@pytest.mark.parametrize(("path", "value"), [
    (("ok",), False), (("accepted",), False), (("done",), False),
    (("request_id",), "different-request"), (("session_id",), "different-session"),
    (("command",), "--chat-gpt"), (("client",), "secure_mcp_gateway"),
    (("awaiting_host_finalization",), True), (("phase_result_ready",), True),
    (("host_finalization_attempt_count",), 1),
    (("host_request_contract_hash",), "a" * 64),
    (("final_visible_text",), "contradictory outer text"),
    (("host_finalization_pending",), True),
    (("result", "ok"), False), (("result", "answer_ok"), False),
    (("result", "canonical_persistence_ok"), False),
    (("result", "final_visible_text"), "tampered"),
    (("result", "host_finalization_pending"), True),
    (("result", "host_visible_finalization"), {"status": "completed"}),
    (("result", "final_visible_integrity", "message_envelope_valid"), False),
    (("result", "runtime_truth_gate", "normal_response_allowed"), False),
    (("result", "conversation_state_persistence", "trace_id"), "different-trace"),
])
def test_nested_completion_never_promotes_conflicting_or_missing_proof(
    path: tuple[str, ...], value: Any,
) -> None:
    payload = _snapshot()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    completion = main_module._daemon_cli_completion(payload)
    assert completion["finalized_successfully"] is False
    assert completion["finalization_evidence_source"] is None
