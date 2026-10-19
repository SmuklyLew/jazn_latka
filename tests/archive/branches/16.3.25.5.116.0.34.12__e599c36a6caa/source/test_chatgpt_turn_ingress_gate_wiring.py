from __future__ import annotations

import hashlib
import io
import json
from typing import Any

from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_presentation_packet,
    write_chat_bridge_payload,
)
from latka_jazn.core.chatgpt_host_pre_response_gate import (
    build_host_pre_response_gate_telemetry,
)
from latka_jazn.mcp.tools import jazn_generate_visible_reply


def _phase_one_payload(user_text: str, *, turn_id: str) -> dict[str, Any]:
    return {
        "chatgpt_host_bridge": {
            "phase": "host_visible_generation_requested",
            "status": "host_visible_generation_requested",
            "host_must_generate_visible_reply": True,
            "host_reply_finalization_required": True,
            "pending_request_persisted": True,
            "host_request_contract_hash": "a" * 64,
            "turn_id": turn_id,
            "trace_id": f"trace-{turn_id}",
            "user_text_sha256": hashlib.sha256(user_text.encode("utf-8")).hexdigest(),
            "host_generation_policy": {},
        },
        "host_pre_response_gate_context": {
            "runtime_turn_invoked": True,
            "requested_runtime_root": "/runtime",
        },
        "transport_observability": {
            "selected_transport": "persistent_daemon",
            "fallback_reason": "daemon_reused",
            "requested_runtime_root": "/runtime",
            "resolved_active_root": "/runtime",
        },
    }


def test_existing_host_packet_builder_is_now_a_current_turn_gate() -> None:
    packet = build_chatgpt_host_presentation_packet(
        _phase_one_payload("Pierwsza wiadomość.", turn_id="turn-1")
    )

    assert packet["action"] == "generate_then_finalize"
    assert packet["turn_ingress_gate_enforced"] is True
    assert packet["host_route_bound"] is True
    telemetry = packet["host_pre_response_gate"]
    assert telemetry["turn_ingress_gate_enforced"] is True
    assert telemetry["host_route_bound"] is True
    assert telemetry["runtime_turn_id"] == "turn-1"
    assert telemetry["trace_id"] == "trace-turn-1"


def test_each_consecutive_packet_requires_its_own_turn_binding() -> None:
    stdout = io.StringIO()
    first = _phase_one_payload("Pierwsza wiadomość.", turn_id="turn-1")
    second = _phase_one_payload("Druga wiadomość.", turn_id="turn-2")

    write_chat_bridge_payload(stdout, first, output_mode="host_packet")
    write_chat_bridge_payload(stdout, second, output_mode="host_packet")

    packets = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert [item["turn_id"] for item in packets] == ["turn-1", "turn-2"]
    assert all(item["turn_ingress_gate_enforced"] is True for item in packets)
    assert all(item["host_route_bound"] is True for item in packets)
    assert packets[0]["host_pre_response_gate"]["user_text_sha256"] != packets[1]["host_pre_response_gate"]["user_text_sha256"]


def test_runtime_action_without_current_turn_digest_fails_closed_before_render() -> None:
    payload = _phase_one_payload("Wiadomość.", turn_id="turn-unbound")
    payload["chatgpt_host_bridge"].pop("user_text_sha256")

    packet = build_chatgpt_host_presentation_packet(payload)

    assert packet["action"] == "host_diagnostic"
    assert packet["turn_ingress_gate_enforced"] is False
    assert packet["host_route_bound"] is False
    assert packet["final_visible_text"] == ""
    assert packet["host_pre_response_gate"]["host_routing_bypass_detected"] is True
    assert packet["host_pre_response_gate"]["host_routing_bypass_reason"] == "current_turn_runtime_binding_unverified"


def test_mcp_visible_reply_entrypoint_calls_canonical_gate_before_gateway_directly(
    monkeypatch: Any,
) -> None:
    calls: list[str] = []

    def fake_gate(user_text: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append(user_text)
        return {
            "ok": False,
            "action": "host_diagnostic",
            "diagnostic_reason": "test_gate_stop",
            "visible_text": "Host diagnostic: test_gate_stop.",
            "visible_output_source": "host_diagnostic",
            "host_pre_response_gate": {
                "host_pre_response_gate": True,
                "turn_ingress_gate_enforced": True,
                "host_route_bound": False,
                "runtime_turn_invoked": True,
            },
        }

    monkeypatch.setattr(jazn_generate_visible_reply, "run_host_pre_response_gate", fake_gate)

    class Gateway:
        runtime_root = "/runtime"

        def chat(
            self,
            _message: str,
            *,
            session_id: str | None = None,
            request_id: str | None = None,
        ) -> dict[str, Any]:
            raise AssertionError("gateway.chat must be owned by the canonical ingress gate callback")

        def issue_continuation(self, _response: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("diagnostic gate result cannot issue a continuation")

    result = jazn_generate_visible_reply.run(
        Gateway(),
        message="Dokładny tekst użytkownika.",
        session_id="chatgpt-main",
    )

    assert calls == ["Dokładny tekst użytkownika."]
    assert result["isError"] is True
    assert result["structuredContent"]["action"] == "host_diagnostic"
    assert result["structuredContent"]["host_pre_response_gate"]["turn_ingress_gate_enforced"] is True


def test_daemon_liveness_is_not_host_route_binding_without_gate_evidence() -> None:
    presentation = {
        "type": "chatgpt_host_presentation",
        "action": "display_exact",
        "phase": "runtime_final_available",
        "turn_id": "turn-1",
        "trace_id": "trace-1",
        "chatgpt_host_bridge": {"user_text_sha256": "b" * 64},
        "transport_observability": {
            "selected_transport": "persistent_daemon",
            "fallback_reason": "daemon_reused",
            "resolved_active_root": "/runtime",
        },
    }

    telemetry = build_host_pre_response_gate_telemetry(
        presentation=presentation,
        runtime_turn_invoked=True,
        turn_ingress_gate_enforced=False,
    )

    assert telemetry["selected_transport"] == "persistent_daemon"
    assert telemetry["turn_ingress_gate_enforced"] is False
    assert telemetry["host_route_bound"] is False
    assert presentation["action"] == "host_diagnostic"
