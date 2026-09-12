from __future__ import annotations

from latka_jazn.core.full_canon_model_context import build_full_canon_model_context
from latka_jazn.core.turn_authority import build_turn_authority_receipt, validate_turn_authority_receipt


def _canon_hash() -> str:
    return str(build_full_canon_model_context({})["immutable_canon_sha256"])


def test_turn_authority_receipt_binds_user_final_identity_and_source() -> None:
    receipt = build_turn_authority_receipt(
        turn_id="turn-1",
        trace_id="trace-1",
        user_text="Obudź się Łateczko.",
        final_visible_text="🕒 2026-09-08 12:00:00\n🌿 Łatka\n\nJestem.",
        identity_canon_sha256=_canon_hash(),
        visible_output_source="runtime_exact",
        author_id="latka",
        author_label="Łatka",
        author_source="jazn_runtime",
    )
    check = validate_turn_authority_receipt(
        receipt,
        expected_user_text="Obudź się Łateczko.",
        expected_final_visible_text="🕒 2026-09-08 12:00:00\n🌿 Łatka\n\nJestem.",
        expected_identity_canon_sha256=_canon_hash(),
        expected_visible_output_source="runtime_exact",
    )
    assert check["ok"] is True


def test_turn_authority_receipt_fails_closed_on_tamper() -> None:
    receipt = build_turn_authority_receipt(
        turn_id="turn-1",
        trace_id="trace-1",
        user_text="A",
        final_visible_text="B",
        identity_canon_sha256=_canon_hash(),
        visible_output_source="runtime_finalized",
        author_id="latka",
        author_label="Łatka",
        author_source="jazn_runtime",
        host_request_contract_hash="a" * 64,
    )
    receipt["final_visible_text_sha256"] = "0" * 64
    check = validate_turn_authority_receipt(receipt, expected_final_visible_text="B")
    assert check["ok"] is False
    assert "receipt_sha256_mismatch" in check["violations"]
    assert "final_visible_text_binding_mismatch" in check["violations"]


def test_non_runtime_visible_source_cannot_receive_latka_authority() -> None:
    receipt = build_turn_authority_receipt(
        turn_id="turn-1",
        trace_id="trace-1",
        user_text="A",
        final_visible_text="B",
        identity_canon_sha256=_canon_hash(),
        visible_output_source="chatgpt_persona",
        author_id="latka",
        author_label="Łatka",
        author_source="chatgpt",
    )
    check = validate_turn_authority_receipt(receipt)
    assert check["ok"] is False
    assert "visible_output_source_not_runtime_owned" in check["violations"]
