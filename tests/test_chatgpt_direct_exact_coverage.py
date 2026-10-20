"""Contract examples for the two legal MCP visible-reply paths."""

from __future__ import annotations

import hashlib
from copy import deepcopy

from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.mcp.turn_coverage import audit_turn_coverage


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _direct_receipt(message: str = "Cześć", message_id: str = "host-1") -> dict:
    gate = {
        "host_pre_response_gate": True,
        "runtime_turn_invoked": True,
        "turn_ingress_gate_enforced": True,
        "host_route_bound": True,
        "host_routing_bypass_detected": False,
        "presentation_action": "display_exact",
        "visible_output_source": "runtime_exact",
        "user_text_sha256": _sha(message),
        "runtime_turn_id": "runtime-turn-1",
        "trace_id": "runtime-trace-1",
    }
    final = {
        "ok": True,
        "action": "display_exact",
        "final_visible_text": "🕒 2026-10-20 12:00:00\n🌿 Łatka\n\nDzień dobry.",
        "turn_id": "runtime-turn-1",
        "trace_id": "runtime-trace-1",
        "must_display_exactly": True,
        "visible_output_source": "runtime_exact",
        "host_pre_response_gate": deepcopy(gate),
        "host_route_bound": True,
    }
    final["final_text_sha256"] = sha256_host_visible_text(final["final_visible_text"])
    return {"message_id": message_id, "gate": gate, "final": {"structuredContent": final, "isError": False}}


def _audit(row: dict, text: str = "Cześć") -> dict:
    return audit_turn_coverage(
        [{"message_id": "host-1", "user_text_sha256": _sha(text)}],
        [row],
    )


def test_mcp_direct_display_exact_does_not_require_host_phase_two() -> None:
    r = _audit(_direct_receipt())
    assert r["ok"] is True
    assert r["accepted_count"] == 1
    assert r["chatgpt_platform_auto_routing_verified"] is False


def test_direct_final_without_echoed_ingress_gate_is_not_accepted() -> None:
    r = _direct_receipt()
    del r["final"]["structuredContent"]["host_pre_response_gate"]
    assert _audit(r)["unaccepted_message_ids"] == ["host-1"]


def test_direct_final_without_matching_trace_is_not_accepted() -> None:
    r = _direct_receipt()
    r["final"]["structuredContent"]["trace_id"] = "forged-trace"
    assert not _audit(r)["ok"]


def test_direct_final_from_other_message_digest_is_not_accepted() -> None:
    r = _direct_receipt("different")
    assert not _audit(r)["ok"]


def test_direct_final_with_altered_text_is_not_accepted() -> None:
    r = _direct_receipt()
    r["final"]["structuredContent"]["final_visible_text"] += " changed"
    assert not _audit(r)["ok"]


def test_direct_final_with_false_readiness_is_not_accepted() -> None:
    r = _direct_receipt()
    r["final"]["structuredContent"]["host_route_bound"] = False
    assert not _audit(r)["ok"]


def test_direct_final_with_error_wrapper_is_not_accepted() -> None:
    r = _direct_receipt()
    r["final"]["isError"] = True
    assert not _audit(r)["ok"]


def test_direct_mcp_receipt_may_redact_reply_body_after_hash_capture() -> None:
    r = _direct_receipt()
    del r["final"]["structuredContent"]["final_visible_text"]
    assert _audit(r)["ok"] is True
