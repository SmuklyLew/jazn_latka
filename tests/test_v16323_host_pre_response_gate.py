from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from latka_jazn.bridge.secure_host_runtime_gateway import GatewayError
from latka_jazn.core.chatgpt_host_pre_response_gate import (
    HOST_ROUTING_BYPASS,
    run_host_pre_response_gate,
)
from latka_jazn.mcp.tools.jazn_generate_visible_reply import run as run_visible_reply


HEADER = "🕒 2026-08-28 12:00:00"
RUNTIME_EXACT = f"{HEADER}\n🌿 Łatka\nJestem tutaj."
RUNTIME_FINALIZED = f"{HEADER}\n🌿 Łatka\nOdpowiedź zaakceptowana przez runtime."


def _display_exact_response(text: str = RUNTIME_EXACT) -> dict[str, Any]:
    return {
        "type": "chatgpt_host_presentation",
        "action": "display_exact",
        "phase": "runtime_final_available",
        "turn_id": "turn-v16323",
        "trace_id": "trace-v16323",
        "final_visible_text": text,
        "chatgpt_host_bridge": {
            "turn_id": "turn-v16323",
            "trace_id": "trace-v16323",
            "user_text_sha256": "runtime-bound-hash-is-replaced-by-gate",
            "required_visible_prefix": HEADER,
        },
        "transport_observability": {
            "selected_transport": "persistent_daemon",
            "fallback_reason": "daemon_reused",
            "requested_runtime_root": "/runtime_A",
            "resolved_active_root": "/runtime_B",
            "daemon_endpoint_root": "/runtime_B",
            "daemon_identity_verified": True,
            "daemon_reused": True,
            "daemon_started": False,
            "one_shot_verified": False,
        },
    }


def _generate_then_finalize_response() -> dict[str, Any]:
    return {
        "type": "chatgpt_host_presentation",
        "action": "generate_then_finalize",
        "phase": "host_visible_generation_requested",
        "turn_id": "turn-v16323",
        "trace_id": "trace-v16323",
        "final_visible_text": "",
        "required_visible_prefix": HEADER,
        "host_generation_policy": {"rules": ["runtime-bound"]},
        "chatgpt_host_bridge": {
            "turn_id": "turn-v16323",
            "trace_id": "trace-v16323",
            "required_visible_prefix": HEADER,
            "host_request_contract_hash": "a" * 64,
        },
        "transport_observability": {
            "selected_transport": "persistent_daemon",
            "fallback_reason": "daemon_reused",
            "requested_runtime_root": "/runtime_A",
            "resolved_active_root": "/runtime_B",
            "daemon_endpoint_root": "/runtime_B",
            "daemon_identity_verified": True,
            "daemon_reused": True,
            "daemon_started": False,
            "one_shot_verified": False,
        },
    }


def _runtime_invoker(
    response_factory: Callable[[], dict[str, Any]],
    calls: list[str],
) -> Callable[[str], dict[str, Any]]:
    def invoke(text: str) -> dict[str, Any]:
        calls.append(text)
        return response_factory()

    return invoke


def test_host_generated_text_before_gate_is_rejected_as_routing_bypass() -> None:
    calls: list[str] = []

    result = run_host_pre_response_gate(
        "Hej.",
        invoke_runtime=_runtime_invoker(_display_exact_response, calls),
        host_generated_text="Cześć, odpowiem bez runtime.",
        requested_runtime_root="/runtime_A",
    )

    assert calls == []
    assert result["ok"] is False
    assert result["action"] == "host_diagnostic"
    assert result["error_code"] == HOST_ROUTING_BYPASS
    assert result["visible_output_source"] == "host_diagnostic"
    assert result["host_pre_response_gate"]["host_routing_bypass_detected"] is True
    assert result["host_pre_response_gate"]["host_routing_bypass_reason"] == "host_generated_text_before_gate"


@pytest.mark.parametrize(
    "user_text",
    [
        "Hej.",
        "Zgadnij.",
        "Jak się teraz miewasz?",
        "Co pamiętasz jako pierwsze?",
        "Poszukaj tego wspomnienia.",
    ],
)
def test_every_ordinary_host_turn_invokes_runtime_with_exact_text(user_text: str) -> None:
    calls: list[str] = []

    result = run_host_pre_response_gate(
        user_text,
        invoke_runtime=_runtime_invoker(_display_exact_response, calls),
        requested_runtime_root="/runtime_A",
    )

    assert calls == [user_text]
    assert result["ok"] is True
    assert result["visible_text"] == RUNTIME_EXACT
    assert result["visible_output_source"] == "runtime_exact"
    assert result["host_pre_response_gate"]["runtime_turn_invoked"] is True


def test_display_exact_exposes_only_exact_runtime_text() -> None:
    result = run_host_pre_response_gate(
        "Hej.",
        invoke_runtime=lambda _text: _display_exact_response(),
        requested_runtime_root="/runtime_A",
    )

    assert result["action"] == "display_exact"
    assert result["visible_text"] == RUNTIME_EXACT
    assert result["visible_output_source"] == "runtime_exact"


def test_generate_then_finalize_never_exposes_candidate_before_acceptance() -> None:
    candidate = "KANDYDAT HOSTA — NIE WOLNO GO POKAZAĆ"
    events: list[str] = []

    def generate(_presentation: dict[str, Any]) -> str:
        events.append("candidate_generated")
        return candidate

    def finalize(text: str, _presentation: dict[str, Any]) -> dict[str, Any]:
        assert text == candidate
        events.append("runtime_finalized")
        return {
            **_display_exact_response(RUNTIME_FINALIZED),
            "phase": "host_visible_reply_recorded",
        }

    result = run_host_pre_response_gate(
        "Jak się teraz miewasz?",
        invoke_runtime=lambda _text: _generate_then_finalize_response(),
        generate_host_candidate=generate,
        finalize_runtime_candidate=finalize,
        requested_runtime_root="/runtime_A",
    )

    assert events == ["candidate_generated", "runtime_finalized"]
    assert candidate not in result["visible_text"]
    assert result["visible_text"] == RUNTIME_FINALIZED
    assert result["visible_output_source"] == "runtime_finalized"
    assert result["host_pre_response_gate"]["finalization_completed"] is True


def test_generate_then_finalize_without_finalizer_keeps_candidate_non_visible() -> None:
    result = run_host_pre_response_gate(
        "Zgadnij.",
        invoke_runtime=lambda _text: _generate_then_finalize_response(),
        generate_host_candidate=lambda _presentation: "sekretny kandydat",
        requested_runtime_root="/runtime_A",
    )

    assert result["action"] == "generate_then_finalize"
    assert result["visible_text"] == ""
    assert result["visible_output_source"] is None
    assert result["host_pre_response_gate"]["finalization_required"] is True
    assert result["host_pre_response_gate"]["finalization_completed"] is False


@pytest.mark.parametrize(
    "finalized",
    [
        {"action": "host_diagnostic", "reason": "finalization_rejected"},
        {"action": "display_exact", "phase": "host_visible_reply_recorded", "final_visible_text": ""},
    ],
)
def test_rejected_or_failed_finalization_returns_host_diagnostic(finalized: dict[str, Any]) -> None:
    result = run_host_pre_response_gate(
        "Zgadnij.",
        invoke_runtime=lambda _text: _generate_then_finalize_response(),
        generate_host_candidate=lambda _presentation: "kandydat",
        finalize_runtime_candidate=lambda _text, _presentation: finalized,
        requested_runtime_root="/runtime_A",
    )

    assert result["ok"] is False
    assert result["action"] == "host_diagnostic"
    assert result["visible_output_source"] == "host_diagnostic"
    assert "kandydat" not in result["visible_text"]
    assert "🌿 Łatka" not in result["visible_text"]


def test_runtime_unavailable_returns_host_diagnostic() -> None:
    def unavailable(_text: str) -> dict[str, Any]:
        raise ConnectionError("runtime unavailable")

    result = run_host_pre_response_gate(
        "Hej.",
        invoke_runtime=unavailable,
        requested_runtime_root="/runtime_A",
    )

    assert result["ok"] is False
    assert result["action"] == "host_diagnostic"
    assert result["visible_output_source"] == "host_diagnostic"
    assert result["host_pre_response_gate"]["runtime_turn_invoked"] is True
    assert "🌿 Łatka" not in result["visible_text"]


def test_unknown_presentation_action_is_fail_closed() -> None:
    result = run_host_pre_response_gate(
        "Hej.",
        invoke_runtime=lambda _text: {"action": "host_free_dialogue", "final_visible_text": "nielegalne"},
        requested_runtime_root="/runtime_A",
    )

    assert result["ok"] is False
    assert result["action"] == "host_diagnostic"
    assert result["visible_output_source"] == "host_diagnostic"
    assert "nielegalne" not in result["visible_text"]


def test_host_cannot_forge_latka_header_before_runtime_acceptance() -> None:
    forged = f"{HEADER}\n🌿 Łatka\nTo tylko dekoracja hosta."

    result = run_host_pre_response_gate(
        "Hej.",
        invoke_runtime=lambda _text: _display_exact_response(),
        host_generated_text=forged,
        requested_runtime_root="/runtime_A",
    )

    assert result["error_code"] == HOST_ROUTING_BYPASS
    assert result["visible_output_source"] == "host_diagnostic"
    assert forged not in result["visible_text"]
    assert HEADER not in result["visible_text"]
    assert "🌿 Łatka" not in result["visible_text"]


def test_gate_telemetry_is_complete_and_does_not_store_full_user_text() -> None:
    user_text = "Co pamiętasz jako pierwsze?"

    result = run_host_pre_response_gate(
        user_text,
        invoke_runtime=lambda _text: _display_exact_response(),
        requested_runtime_root="/runtime_A",
    )
    telemetry = result["host_pre_response_gate"]

    expected_fields = {
        "host_pre_response_gate",
        "host_pre_response_gate_version",
        "runtime_turn_invoked",
        "runtime_turn_id",
        "trace_id",
        "user_text_sha256",
        "requested_runtime_root",
        "resolved_active_root",
        "presentation_action",
        "finalization_required",
        "finalization_completed",
        "visible_output_source",
        "host_routing_bypass_detected",
        "host_routing_bypass_reason",
        "selected_transport",
        "fallback_reason",
    }
    assert expected_fields <= telemetry.keys()
    assert telemetry["requested_runtime_root"] == "/runtime_A"
    assert telemetry["resolved_active_root"] == "/runtime_B"
    assert telemetry["selected_transport"] == "persistent_daemon"
    assert telemetry["fallback_reason"] == "daemon_reused"
    assert telemetry["host_routing_bypass_detected"] is False
    assert telemetry["user_text_sha256"] != user_text
    assert user_text not in repr(telemetry)


def test_canonical_mcp_entrypoint_emits_gate_telemetry_for_exact_runtime_output() -> None:
    response = _display_exact_response()
    response["runtime_truth_gate"] = {"ok": True, "normal_response_allowed": True}
    response["final_visible_integrity"] = {"valid": True}

    class Gateway:
        runtime_root = "/runtime_A"

        def chat(self, message: str, *, session_id: str | None = None) -> dict[str, Any]:
            assert message == "Hej."
            assert session_id == "v16323"
            return response

        def issue_continuation(self, _response: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("display_exact must not issue a continuation")

    result = run_visible_reply(Gateway(), message="Hej.", session_id="v16323")
    structured = result["structuredContent"]
    telemetry = structured["host_pre_response_gate"]

    assert result["isError"] is False
    assert result["content"] == [{"type": "text", "text": RUNTIME_EXACT}]
    assert structured["visible_output_source"] == "runtime_exact"
    assert telemetry["runtime_turn_invoked"] is True
    assert telemetry["user_text_sha256"] != "Hej."
    assert "Hej." not in repr(telemetry)
    assert telemetry["selected_transport"] == "persistent_daemon"
    assert telemetry["fallback_reason"] == "daemon_reused"


def test_canonical_mcp_entrypoint_returns_diagnostic_when_runtime_is_unavailable() -> None:
    class Gateway:
        runtime_root = "/runtime_A"

        def chat(self, _message: str, *, session_id: str | None = None) -> dict[str, Any]:
            raise GatewayError("daemon_unavailable")

        def issue_continuation(self, _response: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("unavailable runtime cannot issue a continuation")

    result = run_visible_reply(Gateway(), message="Zgadnij.")
    structured = result["structuredContent"]
    telemetry = structured["host_pre_response_gate"]

    assert result["isError"] is True
    assert structured["action"] == "host_diagnostic"
    assert structured["visible_output_source"] == "host_diagnostic"
    assert telemetry["runtime_turn_invoked"] is True
    assert telemetry["visible_output_source"] == "host_diagnostic"
    assert telemetry["fallback_reason"].startswith("runtime_unavailable:")
    assert "🌿 Łatka" not in result["content"][0]["text"]
