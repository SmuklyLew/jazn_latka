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
        )


def test_final_capture_records_supported_dream_claim_evidence() -> None:
    capture = FinalVisibleReplyCapture.build(
        **BASE,
        final_text="Śniłam tej nocy.",
        epistemic_evidence={"rest_cycle_count": 1, "dream_scene_count": 1},
    )

    assert capture.epistemic_claims
    assert capture.epistemic_claims[0]["status"] == "supported"
    assert capture.final_visible_text.endswith("Śniłam tej nocy.")


def test_final_capture_allows_truthful_negative_statement() -> None:
    capture = FinalVisibleReplyCapture.build(
        **BASE,
        final_text="Nie śniłam tej nocy.",
    )

    assert capture.epistemic_claims[0]["status"] == "negated"
