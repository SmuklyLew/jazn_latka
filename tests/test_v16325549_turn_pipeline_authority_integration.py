from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_bridge_turn_contract,
    build_chatgpt_host_presentation_packet,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.core.turn_pipeline_contract import validate_turn_pipeline_contract

SAMPLE = datetime(2026, 9, 8, 10, 30, 0, tzinfo=timezone.utc)
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"
FINAL = f"{HEADER}\n🌿 Łatka\n\nJestem tutaj.\n"


def _runtime_final() -> dict:
    integrity = {"valid": True, "text_sha256": sha256_host_visible_text(FINAL)}
    return {
        "runtime_version": "16.3.25.5.49-turn-authority-cognition-identity-convergence",
        "final_visible_text": FINAL,
        "trace": {"turn_id": "turn-49", "trace_id": "trace-49", "timestamp_header": HEADER, "timezone": "Europe/Warsaw"},
        "conversation_decision": {"handler_name": "OrdinaryDialogueHandler", "route": "ordinary_dialogue"},
        "runtime_turn_contract": {
            "turn_id": "turn-49", "trace_id": "trace-49", "handler_name": "OrdinaryDialogueHandler",
            "requires_host_model": False, "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": "turn-49", "trace_id": "trace-49", "requires_host_model": False,
            "timestamp_header": HEADER, "timezone": "Europe/Warsaw",
            "author_id": "latka_runtime", "author_label": "Łatka", "author_source": "jazn_runtime",
            "state_emoticon": "🌿", "final_visible_text": FINAL, "final_visible_integrity": integrity,
        },
        "final_visible_integrity": integrity,
        "final_visible_integrity_consensus": {"valid": True, "mismatch": False},
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": True},
    }


def test_exact_runtime_final_carries_verified_turn_authority_and_pipeline() -> None:
    user_text = "Obudź się Łateczko."
    runtime = _runtime_final()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text=user_text, chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge

    assert bridge["turn_authority_required"] is True
    assert bridge["turn_authority_validation"]["ok"] is True
    assert bridge["turn_authority_receipt"]["visible_output_source"] == "runtime_exact"
    assert validate_turn_pipeline_contract(bridge["turn_pipeline_contract"])["ok"] is True

    presentation = build_chatgpt_host_presentation_packet(runtime)
    assert presentation["action"] == "display_exact"
    assert presentation["authorship_verified"] is True
    assert presentation["final_visible_text"] == FINAL


def test_tampered_authority_receipt_for_required_turn_fails_to_host_diagnostic() -> None:
    runtime = _runtime_final()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="test", chat_bridge_meta={})
    bridge["turn_authority_receipt"]["final_visible_text_sha256"] = "0" * 64
    runtime["chatgpt_host_bridge"] = bridge
    presentation = build_chatgpt_host_presentation_packet(runtime)
    assert presentation["action"] == "host_diagnostic"
    assert presentation["authorship_verified"] is False
    assert "turn_authority_receipt_invalid" in str(presentation["diagnostic_reason"])
