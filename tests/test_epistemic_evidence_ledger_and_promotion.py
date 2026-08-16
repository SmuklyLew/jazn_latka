from __future__ import annotations

import sqlite3

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.epistemic_claim_guard import (
    EpistemicClaimGuard,
    EpistemicClaimKind,
    EpistemicClaimStatus,
    EpistemicSourceKind,
    StructuredEpistemicClaim,
)
from latka_jazn.core.epistemic_decision_ledger import EpistemicDecisionLedger
from latka_jazn.core.epistemic_evidence import EpistemicEvidenceCollector
from latka_jazn.memory.memory_promotion_gate import MemoryPromotionGate, PromotionDecision
from latka_jazn.memory.rest_contracts import RestReplayItem, sha256_text


def replay_item(memory_id: str, content: str, *, truth: str = "source_recorded", source_row: str = "1") -> RestReplayItem:
    return RestReplayItem(
        source_memory_id=memory_id,
        source_tier="normalized_l1",
        kind="episodic",
        truth_status=truth,
        content=content,
        content_sha256=sha256_text(content),
        domain="test",
        confidence=0.9,
        importance=0.8,
        score=0.8,
        provenance={
            "source_table": "messages",
            "source_row_id": source_row,
            "source_sha256": "a" * 64,
        },
    )


def test_evidence_collector_fails_closed_when_rest_store_missing(tmp_path):
    config = JaznConfig(root=tmp_path)
    snapshot = EpistemicEvidenceCollector(config).collect(
        runtime_evidence={
            "daemon_verified": True,
            "background_event_ids": ["evt-1", "evt-2"],
        },
        memory_evidence={"source_ids": ["mem-1"]},
    )
    assert snapshot.rest_cycle_count == 0
    assert snapshot.dream_scene_count == 0
    assert snapshot.rest_report_sha256 is None
    assert snapshot.daemon_verified is True
    assert snapshot.background_event_count == 2
    assert snapshot.memory_evidence_count == 1


def test_structured_inference_cannot_become_supported_fact_just_from_confidence():
    claim = StructuredEpistemicClaim(
        kind=EpistemicClaimKind.INFERENCE,
        text="To prawdopodobnie wynika z X",
        source_kind=EpistemicSourceKind.MODEL_INFERENCE,
        source_ids=(),
        confidence=0.99,
    )
    assessment = EpistemicClaimGuard().assess_structured([claim])[0]
    assert assessment.status is EpistemicClaimStatus.INFERRED
    assert assessment.blocks_visible_reply is False
    assert assessment.reason == "model_inference_not_promoted_to_fact"


def test_structured_fact_requires_explicit_source_identifier():
    claim = StructuredEpistemicClaim(
        kind=EpistemicClaimKind.EXTERNAL_FACT,
        text="zewnętrzny fakt",
        source_kind=EpistemicSourceKind.TOOL_OR_WEB_SOURCE,
        source_ids=(),
    )
    assessment = EpistemicClaimGuard().assess_structured([claim])[0]
    assert assessment.status is EpistemicClaimStatus.UNSUPPORTED
    assert assessment.blocks_visible_reply is True


def test_epistemic_ledger_is_hash_chained_and_detects_tampering(tmp_path):
    path = tmp_path / "epistemic.sqlite3"
    ledger = EpistemicDecisionLedger(path)
    try:
        ledger.append_assessments(
            turn_id="turn-1",
            trace_id="trace-1",
            assessments=[{
                "kind": "dream_activity",
                "status": "negated",
                "matched_text": "nie śniłam",
                "reason": "negative_or_uncertain_dream_statement",
                "required_evidence": [],
                "evidence_snapshot": {},
            }],
        )
        assert ledger.validate_chain()["ok"] is True
        ledger.con.execute("UPDATE epistemic_decisions SET reason='tampered' WHERE seq=1")
        ledger.con.commit()
        validation = ledger.validate_chain()
        assert validation["ok"] is False
        assert validation["reason"] == "entry_hash_mismatch"
    finally:
        ledger.close()


def test_memory_promotion_gate_forbids_automatic_l3():
    assessment = MemoryPromotionGate().assess_rest_candidate(
        [replay_item("m1", "source text")],
        target_tier="long_term",
        synthetic_source=True,
    )
    assert assessment.decision is PromotionDecision.DENY
    assert "automatic_long_term_promotion_forbidden" in assessment.reasons


def test_memory_promotion_gate_flags_same_source_with_conflicting_content():
    first = replay_item("m1", "version one", source_row="42")
    second = replay_item("m2", "version two", source_row="42")
    assessment = MemoryPromotionGate().assess_rest_candidate(
        [first, second],
        target_tier="short_term",
        synthetic_source=True,
    )
    assert assessment.decision is PromotionDecision.REQUIRE_USER_REVIEW
    assert assessment.source_conflict_detected is True
