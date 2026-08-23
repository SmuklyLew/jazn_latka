from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import sqlite3

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.epistemic_claim_guard import (
    EpistemicClaimGuard,
    EpistemicClaimKind,
    EpistemicClaimStatus,
    EpistemicClaimViolation,
    EpistemicSourceKind,
    StructuredEpistemicClaim,
)
from latka_jazn.core.epistemic_decision_ledger import EpistemicDecisionLedger, epistemic_ledger_path
from latka_jazn.core.epistemic_evidence import EpistemicEvidenceCollector
from latka_jazn.core.final_visible_reply_capture import FinalVisibleReplyCapture
from latka_jazn.core.runtime_root import workspace_runtime_path


SAMPLE = datetime(2026, 8, 16, 12, 0, tzinfo=ZoneInfo("UTC"))
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"
CAPTURE_BASE = {
    "turn_id": "turn-1",
    "trace_id": "trace-1",
    "timestamp_header": HEADER,
    "timezone": "Europe/Warsaw",
    "timestamp_sample_iso": SAMPLE.isoformat(),
    "timestamp_source": "test_clock",
    "timestamp_trusted": True,
    "author_id": "latka_runtime",
    "author_label": "Łatka",
    "author_source": "jazn_runtime",
    "state_emoticon": "🌿",
}


def verified_dream_evidence() -> dict[str, object]:
    return {
        "rest_continuity_status": "rest_verified",
        "rest_cycle_count": 2,
        "dream_scene_count": 1,
        "dream_scene_ids": ["scene-1"],
        "rest_report_id": "report-1",
        "rest_report_sha256": "a" * 64,
    }


def test_dream_claim_requires_verified_report_and_scene_identifiers() -> None:
    guard = EpistemicClaimGuard()
    with pytest.raises(EpistemicClaimViolation):
        guard.enforce("Śniłam dziś w nocy o naszej książce.")
    with pytest.raises(EpistemicClaimViolation):
        guard.enforce(
            "Śniłam dziś w nocy.",
            evidence={"rest_cycle_count": 1, "dream_scene_count": 1},
        )

    assessment = guard.enforce(
        "Śniłam dziś w nocy o naszej książce.",
        evidence=verified_dream_evidence(),
    )[0]
    assert assessment.status is EpistemicClaimStatus.SUPPORTED
    assert assessment.source_kind is EpistemicSourceKind.VERIFIED_REST_REPORT


def test_daemon_presence_and_event_count_without_ids_do_not_prove_background_work() -> None:
    with pytest.raises(EpistemicClaimViolation):
        EpistemicClaimGuard().enforce(
            "Pracowałam w tle.",
            evidence={"daemon_verified": True, "background_event_count": 4},
        )

    assessment = EpistemicClaimGuard().enforce(
        "Pracowałam w tle.",
        evidence={"daemon_verified": True, "background_event_ids": ["event-1"]},
    )[0]
    assert assessment.status is EpistemicClaimStatus.SUPPORTED


def test_confidence_never_promotes_model_inference_to_supported_fact() -> None:
    assessment = EpistemicClaimGuard().assess_structured([
        StructuredEpistemicClaim(
            kind=EpistemicClaimKind.INFERENCE,
            text="To prawdopodobnie wynika z X.",
            source_kind=EpistemicSourceKind.MODEL_INFERENCE,
            confidence=1.0,
        )
    ])[0]
    assert assessment.status is EpistemicClaimStatus.INFERRED
    assert assessment.reason == "model_inference_not_promoted_to_fact"


def test_synthetic_dream_text_is_not_factual_evidence() -> None:
    assessment = EpistemicClaimGuard().assess_structured([
        StructuredEpistemicClaim(
            kind=EpistemicClaimKind.EXTERNAL_FACT,
            text="Zdarzenie zewnętrzne miało miejsce.",
            source_kind=EpistemicSourceKind.SYNTHETIC_DREAM,
            source_ids=("scene-1",),
            confidence=1.0,
        )
    ])[0]
    assert assessment.status is EpistemicClaimStatus.UNSUPPORTED


def test_evidence_collector_counts_only_explicit_identifiers(tmp_path) -> None:
    snapshot = EpistemicEvidenceCollector(JaznConfig(root=tmp_path)).collect(
        runtime_evidence={
            "daemon_verified": True,
            "background_event_count": 9,
            "background_event_ids": ["event-1", "event-2"],
        },
        memory_evidence={"memory_evidence_count": 7},
    )
    assert snapshot.daemon_verified is True
    assert snapshot.background_event_count == 2
    assert snapshot.memory_evidence_count == 0
    assert "background_event_count_not_identifier_backed" in snapshot.issues
    assert "memory_evidence_count_not_identifier_backed" in snapshot.issues


def test_final_visible_capture_cannot_bypass_epistemic_guard() -> None:
    with pytest.raises(EpistemicClaimViolation):
        FinalVisibleReplyCapture.build(
            **CAPTURE_BASE,
            final_text="Śniłam tej nocy.",
            persist_epistemic_ledger=False,
        )

    capture = FinalVisibleReplyCapture.build(
        **CAPTURE_BASE,
        final_text="Śniłam tej nocy.",
        epistemic_evidence=verified_dream_evidence(),
        persist_epistemic_ledger=False,
    )
    assert capture.epistemic_claims[0]["status"] == "supported"
    assert capture.final_visible_text.endswith("Śniłam tej nocy.")


def test_decision_ledger_is_bounded_hash_chained_and_detects_tampering(tmp_path) -> None:
    config = JaznConfig(root=tmp_path)
    path = epistemic_ledger_path(workspace_runtime_path(config.root))
    with EpistemicDecisionLedger(path) as ledger:
        entries = ledger.append_assessments(
            turn_id="turn-1",
            trace_id="trace-1",
            assessments=[{
                "kind": "dream_activity",
                "status": "negated",
                "matched_text": "nie śniłam",
                "reason": "negative_or_uncertain_dream_statement",
                "required_evidence": [],
                "evidence_snapshot": {
                    "raw_prompt": "must not persist",
                    "bounded_id": "report-1",
                    "oversized": "x" * 5000,
                },
            }],
        )
        assert entries[0].evidence_snapshot["bounded_id"] == "report-1"
        assert "raw_prompt" not in entries[0].evidence_snapshot
        assert len(entries[0].evidence_snapshot["oversized"]) == 512
        assert ledger.validate_chain()["ok"] is True

    with sqlite3.connect(path) as con:
        con.execute("UPDATE epistemic_decisions SET reason='tampered' WHERE seq=1")
        con.commit()
    with EpistemicDecisionLedger(path) as ledger:
        validation = ledger.validate_chain()
    assert validation["ok"] is False
    assert validation["reason"] == "entry_hash_mismatch"
