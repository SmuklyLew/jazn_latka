from __future__ import annotations

from latka_jazn.memory.memory_promotion_gate import MemoryPromotionGate, PromotionDecision
from latka_jazn.memory.offline_rest_consolidation import OfflineRestConsolidator
from latka_jazn.memory.rest_contracts import RestReplayItem, sha256_text


def replay_item(
    memory_id: str,
    content: str,
    *,
    truth: str = "source_recorded",
    source_row: str | None = "1",
    source_sha: str | None = None,
) -> RestReplayItem:
    provenance: dict[str, str] = {}
    if source_row is not None:
        provenance.update({
            "source_table": "messages",
            "source_row_id": source_row,
            "source_sha256": source_sha or "a" * 64,
        })
    return RestReplayItem(
        source_memory_id=memory_id,
        source_tier="normalized_l1",
        kind="episodic",
        truth_status=truth,
        content=content,
        content_sha256=sha256_text(content),
        domain="test",
        confidence=1.0,
        importance=0.8,
        score=0.8,
        provenance=provenance,
    )


def test_promotion_gate_forbids_automatic_l3() -> None:
    assessment = MemoryPromotionGate().assess_rest_candidate(
        [replay_item("m1", "source text")],
        target_tier="long_term",
        synthetic_source=True,
    )
    assert assessment.decision is PromotionDecision.DENY
    assert "automatic_long_term_promotion_forbidden" in assessment.reasons


def test_truth_status_or_confidence_without_provenance_is_not_real_anchor() -> None:
    assessment = MemoryPromotionGate().assess_rest_candidate(
        [replay_item("m1", "unanchored", source_row=None)],
        target_tier="short_term",
        synthetic_source=True,
    )
    assert assessment.truth_eligible_source_count == 1
    assert assessment.real_source_anchor_count == 0
    assert assessment.decision is PromotionDecision.DENY
    assert "truth_status_without_provenance_is_not_an_anchor" in assessment.reasons


def test_same_source_with_conflicting_content_requires_review() -> None:
    assessment = MemoryPromotionGate().assess_rest_candidate(
        [
            replay_item("m1", "version one", source_row="42"),
            replay_item("m2", "version two", source_row="42"),
        ],
        target_tier="short_term",
        synthetic_source=True,
    )
    assert assessment.decision is PromotionDecision.REQUIRE_USER_REVIEW
    assert assessment.source_conflict_detected is True


def test_source_anchored_synthetic_candidate_is_only_inferred_l2() -> None:
    assessment = MemoryPromotionGate().assess_rest_candidate(
        [replay_item("m1", "source text")],
        target_tier="short_term",
        synthetic_source=True,
    )
    assert assessment.decision is PromotionDecision.ALLOW_INFERRED_L2


def test_offline_rest_is_model_free_and_reports_duplicates_and_missing_anchors() -> None:
    content = "same source text"
    report = OfflineRestConsolidator().run([
        replay_item("m1", content, source_row="1"),
        replay_item("m2", content, source_row="2"),
        replay_item("m3", "inference", truth="inferred", source_row=None),
    ])
    assert report.dream_generation_required is False
    assert report.automatic_memory_promotion_allowed is False
    assert report.source_anchor_count == 2
    assert report.inferred_or_symbolic_count == 1
    assert report.duplicate_groups == (("m1", "m2"),)
    assert report.status == "completed_with_incomplete_provenance"


def test_empty_offline_rest_is_successful_housekeeping() -> None:
    report = OfflineRestConsolidator().run([])
    assert report.status == "completed_empty"
    assert report.replay_count == 0
