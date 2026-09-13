from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract
from latka_jazn.core.chatgpt_host_pre_response_gate import (
    build_host_pre_response_gate_telemetry,
)
from latka_jazn.mcp.tools import jazn_generate_visible_reply


def _diagnostic_gate_result(user_text: str) -> dict[str, Any]:
    telemetry = {
        "host_pre_response_gate": True,
        "runtime_turn_invoked": True,
        "turn_ingress_gate_enforced": True,
        "host_route_bound": False,
        "presentation_action": "host_diagnostic",
        "runtime_turn_id": None,
        "trace_id": None,
        "user_text_sha256": f"digest:{user_text}",
        "visible_output_source": "host_diagnostic",
    }
    return {
        "ok": False,
        "action": "host_diagnostic",
        "error_code": "TEST_GATE_STOP",
        "diagnostic_reason": "test_gate_stop",
        "visible_text": "Host diagnostic: test_gate_stop.",
        "visible_output_source": "host_diagnostic",
        "host_pre_response_gate": telemetry,
        "turn_ingress_gate_enforced": True,
        "host_route_bound": False,
    }


def test_jsonl_chatgpt_ingress_routes_every_ordinary_line_through_gate(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def fake_gate(user_text: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append(user_text)
        return _diagnostic_gate_result(user_text)

    monkeypatch.setattr(chat_command_contract, "run_host_pre_response_gate", fake_gate)

    stdin = io.StringIO("Pierwsza wiadomość.\nDruga wiadomość.\n")
    stdout = io.StringIO()
    exit_code = chat_command_contract.run_jsonl_chat_bridge(
        config=JaznConfig(root=tmp_path),
        session_id="chatgpt-main",
        no_carryover=False,
        command="--chat-gpt",
        stdin=stdin,
        stdout=stdout,
    )

    assert exit_code == 0
    assert calls == ["Pierwsza wiadomość.", "Druga wiadomość."]
    packets = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert len(packets) == 2
    assert all(packet["chatgpt_host_presentation"]["action"] == "host_diagnostic" for packet in packets)
    assert all(packet["turn_ingress_gate_enforced"] is True for packet in packets)
    assert all(packet["host_route_bound"] is False for packet in packets)
    assert all(
        packet["chatgpt_host_presentation"]["host_pre_response_gate"]["turn_ingress_gate_enforced"] is True
        for packet in packets
    )


def test_mcp_visible_reply_entrypoint_calls_gate_before_gateway_directly(
    monkeypatch: Any,
) -> None:
    calls: list[str] = []

    def fake_gate(user_text: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append(user_text)
        return _diagnostic_gate_result(user_text)

    monkeypatch.setattr(jazn_generate_visible_reply, "run_host_pre_response_gate", fake_gate)

    class Gateway:
        runtime_root = "/runtime"

        def chat(self, _message: str, *, session_id: str | None = None) -> dict[str, Any]:
            raise AssertionError("gateway.chat must not run before the canonical ingress gate")

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



def test_daemon_fast_path_routes_exact_user_text_through_gate_before_submit(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text("{}\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(main_module, "_chatgpt_daemon_marker_path", lambda _cfg: marker)
    monkeypatch.setattr(
        main_module,
        "status_daemon",
        lambda *_args, **_kwargs: {"active_state": "active_trusted", "endpoint_reachable": True},
    )
    monkeypatch.setattr(
        main_module,
        "chat_daemon",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("daemon submit must be owned by the canonical gate callback")
        ),
    )

    def fake_gate(user_text: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append(user_text)
        return _diagnostic_gate_result(user_text)

    monkeypatch.setattr(main_module, "run_host_pre_response_gate", fake_gate)
    stdout = io.StringIO()
    monkeypatch.setattr(main_module.sys, "stdout", stdout)

    exit_code = main_module._try_chat_gpt_one_shot_via_daemon(
        cfg=JaznConfig(root=tmp_path),
        text="Wiadomość na daemon fast path.",
        session_id="chatgpt-main",
        no_carryover=False,
        host="127.0.0.1",
        port=8787,
        timeout=1.0,
        output_mode="host_packet",
        request_id="request-gate-wiring",
        transport_observability={
            "selected_transport": "persistent_daemon",
            "fallback_reason": "daemon_reused",
            "requested_runtime_root": str(tmp_path),
            "resolved_active_root": str(tmp_path),
            "daemon_identity_verified": True,
        },
    )

    assert exit_code == 0
    assert calls == ["Wiadomość na daemon fast path."]
    packet = json.loads(stdout.getvalue().strip())
    assert packet["action"] == "host_diagnostic"
    assert packet["turn_ingress_gate_enforced"] is True
    assert packet["host_route_bound"] is False


def test_gate_telemetry_distinguishes_daemon_transport_from_bound_host_route() -> None:
    presentation = {
        "type": "chatgpt_host_presentation",
        "action": "display_exact",
        "phase": "runtime_final_available",
        "turn_id": "turn-1",
        "trace_id": "trace-1",
        "transport_observability": {
            "selected_transport": "persistent_daemon",
            "fallback_reason": "daemon_reused",
            "resolved_active_root": "/runtime",
        },
    }

    before_gate = build_host_pre_response_gate_telemetry(
        presentation=dict(presentation),
        runtime_turn_invoked=True,
        turn_ingress_gate_enforced=False,
    )
    after_gate = build_host_pre_response_gate_telemetry(
        presentation=dict(presentation),
        runtime_turn_invoked=True,
        turn_ingress_gate_enforced=True,
    )

    assert before_gate["selected_transport"] == "persistent_daemon"
    assert before_gate["turn_ingress_gate_enforced"] is False
    assert before_gate["host_route_bound"] is False
    assert after_gate["turn_ingress_gate_enforced"] is True
    assert after_gate["host_route_bound"] is True
