from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from latka_jazn.bridge.secure_host_runtime_gateway import SecureHostRuntimeGateway
from latka_jazn.core.chatgpt_host_pending_store import (
    calculate_host_request_contract_hash,
    claim_pending_host_request,
    consume_claimed_host_request,
    issue_continuation_token,
    persist_pending_host_request,
)
from latka_jazn.mcp.server import READ_ONLY_TOOLS, TOOL_DEFINITIONS
from latka_jazn.mcp.tools import jazn_resume_visible_reply


REQUEST_ID = "request-v1637-recovery"
TURN_ID = "turn-v1637-recovery"
TRACE_ID = "trace-v1637-recovery"
HEADER = "🕒 2026-08-26 17:00:00"
V1637_RECOVERY_RUNTIME_VERSION = "16.3.7-host-finalization-recovery-hardening"


def _bridge() -> dict[str, Any]:
    bridge: dict[str, Any] = {
        "runtime_version": V1637_RECOVERY_RUNTIME_VERSION,
        "phase": "host_visible_generation_requested",
        "turn_id": TURN_ID,
        "trace_id": TRACE_ID,
        "timestamp_header": HEADER,
        "timezone": "Europe/Warsaw",
        "timestamp_sample_iso": "2026-08-26T17:00:00+02:00",
        "timestamp_source": "system_local",
        "timestamp_trusted": True,
        "author_id": "latka_runtime",
        "author_label": "Łatka",
        "author_source": "jazn_runtime",
        "state_emoticon": "🌿",
        "user_text_sha256": hashlib.sha256("dokładna wiadomość".encode("utf-8")).hexdigest(),
        "finalization_contract_hash": "a" * 64,
        "runtime_context_sha256": "b" * 64,
        "daemon_request_id": REQUEST_ID,
        "required_visible_prefix": f"{HEADER}\n🧷 Łatka\n\n",
        "host_generation_policy": {"mode": "runtime_bound"},
        "host_generation_rules": ["Preserve the runtime contract."],
        "host_generation_context": {"bounded_context": True},
        "runtime_summary": {"route": "ordinary_dialogue"},
    }
    bridge["host_request_contract_hash"] = calculate_host_request_contract_hash(bridge)
    return bridge


def _phase_one_envelope(bridge: dict[str, Any]) -> dict[str, Any]:
    presentation = {
        "type": "chatgpt_host_presentation",
        "action": "generate_then_finalize",
        "phase": "host_visible_generation_requested",
        "turn_id": TURN_ID,
        "trace_id": TRACE_ID,
        "daemon_request_id": REQUEST_ID,
        "chatgpt_host_bridge": dict(bridge),
    }
    return {
        "request_id": REQUEST_ID,
        "status": "awaiting_host_finalization",
        "result": {
            "ok": True,
            "chatgpt_host_presentation": presentation,
            "chatgpt_host_bridge": dict(bridge),
        },
    }


class _FakeRecoveryGateway:
    def __init__(self, envelope: dict[str, Any]) -> None:
        self.envelope = envelope
        self.result_calls: list[str] = []

    def result(self, request_id: str) -> dict[str, Any]:
        self.result_calls.append(request_id)
        return self.envelope

    def chat(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("resume must never resubmit user text through chat()")


def test_v1637_recovery_fixture_keeps_historical_runtime_contract() -> None:
    bridge = _bridge()
    assert bridge["runtime_version"] == V1637_RECOVERY_RUNTIME_VERSION
    assert bridge["phase"] == "host_visible_generation_requested"
    assert bridge["author_source"] == "jazn_runtime"


def test_resume_tool_is_private_read_only_and_has_no_message_input() -> None:
    definition = next(
        item for item in TOOL_DEFINITIONS if item["name"] == "jazn_resume_visible_reply"
    )
    schema = definition["inputSchema"]
    assert schema["required"] == ["daemon_request_id"]
    assert "message" not in schema["properties"]
    assert definition["annotations"]["readOnlyHint"] is True
    assert definition["annotations"]["idempotentHint"] is True
    assert definition["_meta"]["openai/visibility"] == "private"
    assert "jazn_resume_visible_reply" in READ_ONLY_TOOLS


def test_resume_reuses_same_pending_contract_and_same_hmac_token(tmp_path: Path) -> None:
    bridge = _bridge()
    record = persist_pending_host_request(tmp_path, bridge)
    initial = issue_continuation_token(
        tmp_path,
        turn_id=TURN_ID,
        request_contract_hash=str(record["request_contract_hash"]),
    )
    gateway = _FakeRecoveryGateway(_phase_one_envelope(bridge))

    resumed = jazn_resume_visible_reply.run(
        root=tmp_path,
        gateway=gateway,
        daemon_request_id=REQUEST_ID,
        turn_id=TURN_ID,
        host_request_contract_hash=str(record["request_contract_hash"]),
    )

    structured = resumed["structuredContent"]
    assert resumed["isError"] is False
    assert structured["action"] == "generate_then_finalize"
    assert structured["continuation_token"] == initial["continuation_token"]
    assert structured["host_request_contract_hash"] == record["request_contract_hash"]
    assert structured["daemon_request_id"] == REQUEST_ID
    assert structured["host_generation_context"] == {"bounded_context": True}
    assert structured["must_not_resubmit_user_message"] is True
    assert structured["continuation_token_reissued_idempotently"] is True
    assert gateway.result_calls == [REQUEST_ID]


def test_resume_fails_closed_after_pending_record_is_claimed(tmp_path: Path) -> None:
    bridge = _bridge()
    record = persist_pending_host_request(tmp_path, bridge)
    issue_continuation_token(
        tmp_path,
        turn_id=TURN_ID,
        request_contract_hash=str(record["request_contract_hash"]),
    )
    claim_pending_host_request(
        tmp_path,
        turn_id=TURN_ID,
        request_contract_hash=str(record["request_contract_hash"]),
    )
    gateway = _FakeRecoveryGateway(_phase_one_envelope(bridge))

    resumed = jazn_resume_visible_reply.run(
        root=tmp_path,
        gateway=gateway,
        daemon_request_id=REQUEST_ID,
    )

    assert resumed["isError"] is True
    assert resumed["structuredContent"]["action"] == "host_diagnostic"
    assert resumed["structuredContent"]["reason"] == "host_request_in_progress"
    assert resumed["structuredContent"]["must_not_resubmit_user_message"] is True


def test_lost_finalization_response_recovers_display_exact_without_replay(tmp_path: Path) -> None:
    bridge = _bridge()
    record = persist_pending_host_request(tmp_path, bridge)
    issue_continuation_token(
        tmp_path,
        turn_id=TURN_ID,
        request_contract_hash=str(record["request_contract_hash"]),
    )
    claim_pending_host_request(
        tmp_path,
        turn_id=TURN_ID,
        request_contract_hash=str(record["request_contract_hash"]),
    )
    consume_claimed_host_request(
        tmp_path,
        turn_id=TURN_ID,
        request_contract_hash=str(record["request_contract_hash"]),
    )

    final_text = f"{HEADER}\n🧷 Łatka\n\nZaakceptowana odpowiedź runtime."
    envelope = {
        "request_id": REQUEST_ID,
        "status": "completed",
        "result": {
            "ok": True,
            "final_visible_text": final_text,
            "final_visible_integrity": {"valid": True},
            "runtime_truth_gate": {"ok": True, "normal_response_allowed": True},
            "chatgpt_host_presentation": {
                "type": "chatgpt_host_presentation",
                "action": "display_exact",
                "turn_id": TURN_ID,
                "trace_id": TRACE_ID,
                "final_visible_text": final_text,
                "final_text_sha256": hashlib.sha256(final_text.encode("utf-8")).hexdigest(),
                "runtime_checks": {
                    "final_visible_integrity_valid": True,
                    "runtime_truth_gate_ok": True,
                },
            },
        },
    }
    gateway = _FakeRecoveryGateway(envelope)

    resumed = jazn_resume_visible_reply.run(
        root=tmp_path,
        gateway=gateway,
        daemon_request_id=REQUEST_ID,
    )

    assert resumed["isError"] is False
    assert resumed["structuredContent"]["action"] == "display_exact"
    assert resumed["structuredContent"]["final_visible_text"] == final_text
    assert resumed["structuredContent"]["must_display_exactly"] is True
    assert resumed["structuredContent"]["must_not_resubmit_user_message"] is True
    assert gateway.result_calls == [REQUEST_ID]


def test_gateway_result_polls_chat_result_only(monkeypatch, tmp_path: Path) -> None:
    gateway = object.__new__(SecureHostRuntimeGateway)
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_http_json(
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append((method, path, payload))
        return {"request_id": REQUEST_ID, "status": "running"}

    monkeypatch.setattr(gateway, "_http_json", fake_http_json)
    result = gateway.result(REQUEST_ID)

    assert result["request_id"] == REQUEST_ID
    assert calls == [("GET", f"/chat-result?request_id={REQUEST_ID}", None)]
