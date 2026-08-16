from __future__ import annotations

import pytest

from latka_jazn.core.epistemic_claim_guard import EpistemicClaimViolation
from latka_jazn.core.final_visible_reply_capture import FinalVisibleReplyCapture


BASE = {
    "turn_id": "turn-1",
    "trace_id": "trace-1",
    "timestamp_header": "🕒 2026-08-16 12:00:00",
    "timezone": "UTC",
    "timestamp_sample_iso": "2026-08-16T12:00:00+00:00",
    "timestamp_source": "test_clock",
    "timestamp_trusted": True,
    "author_id": "latka_runtime",
    "author_label": "Łatka",
    "author_source": "jazn_runtime",
    "state_emoticon": "🌿",
}


def test_final_capture_rejects_unsupported_dream_claim() -> None:
    with pytest.raises(EpistemicClaimViolation):
        FinalVisibleReplyCapture.build(
            **BASE,
            final_text="Śniłam tej nocy.",
            persist_epistemic_ledger=False,
        )


def test_final_capture_rejects_counts_without_verified_report() -> None:
    with pytest.raises(EpistemicClaimViolation):
        FinalVisibleReplyCapture.build(
            **BASE,
            final_text="Śniłam tej nocy.",
            epistemic_evidence={"rest_cycle_count": 1, "dream_scene_count": 1},
            persist_epistemic_ledger=False,
        )


def test_final_capture_records_supported_dream_claim_evidence() -> None:
    capture = FinalVisibleReplyCapture.build(
        **BASE,
        final_text="Śniłam tej nocy.",
        epistemic_evidence={
            "rest_continuity_status": "rest_verified",
            "rest_cycle_count": 1,
            "dream_scene_count": 1,
            "dream_scene_ids": ["scene-1"],
            "rest_report_id": "report-1",
            "rest_report_sha256": "a" * 64,
        },
        persist_epistemic_ledger=False,
    )

    assert capture.epistemic_claims
    assert capture.epistemic_claims[0]["status"] == "supported"
    assert capture.epistemic_claims[0]["source_kind"] == "verified_rest_report"
    assert capture.final_visible_text.endswith("Śniłam tej nocy.")


def test_final_capture_allows_truthful_negative_statement() -> None:
    capture = FinalVisibleReplyCapture.build(
        **BASE,
        final_text="Nie śniłam tej nocy.",
        persist_epistemic_ledger=False,
    )

    assert capture.epistemic_claims[0]["status"] == "negated"
