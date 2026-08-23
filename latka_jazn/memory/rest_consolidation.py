from __future__ import annotations

from datetime import datetime, timezone
import uuid

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_tier_core_store import MemoryTierCoreStore
from latka_jazn.memory.memory_promotion_gate import MemoryPromotionGate, PromotionDecision
from latka_jazn.memory.memory_tiers import (
    MemoryKind,
    MemoryTier,
    MemoryTruthStatus,
    ShortTermMemoryPolicy,
    SourceEvidence,
)
from latka_jazn.memory.rest_contracts import (
    DreamEvaluation,
    DreamScene,
    RestConsolidationDecision,
    RestConsolidationDisposition,
    RestReplayItem,
)
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("rest_consolidation_gate")


class RestConsolidationGate:
    """Fail-closed bridge from synthetic rest output to, at most, inferred L2."""

    def __init__(self, config: JaznConfig, *, shadow_mode: bool | None = None) -> None:
        self.config = config
        self.shadow_mode = bool(getattr(config, "rest_shadow_mode", True) if shadow_mode is None else shadow_mode)
        self.promotion_gate = MemoryPromotionGate()

    def decide(
        self,
        scene: DreamScene,
        evaluation: DreamEvaluation,
        replay_items: list[RestReplayItem],
        *,
        decided_at_utc: str | None = None,
    ) -> RestConsolidationDecision:
        disposition = evaluation.recommended_disposition
        promotion = self.promotion_gate.assess_rest_candidate(
            replay_items,
            target_tier=MemoryTier.SHORT_TERM.value,
            synthetic_source=True,
        )
        anchors = [item for item in replay_items if self.promotion_gate.is_verified_source_anchor(item)]
        reasons = list(evaluation.reasons)
        reasons.extend(promotion.reasons)
        target_tier: str | None = None
        materialized_memory_id: str | None = None

        if disposition in {RestConsolidationDisposition.REFLECTION_CANDIDATE, RestConsolidationDisposition.PROCEDURE_CANDIDATE}:
            if promotion.decision is PromotionDecision.DENY:
                disposition = RestConsolidationDisposition.REST_TRANSIENT
                reasons.append("candidate_denied_by_memory_promotion_gate")
            elif promotion.decision is PromotionDecision.REQUIRE_USER_REVIEW:
                disposition = RestConsolidationDisposition.USER_REVIEW_REQUIRED
                reasons.append("candidate_requires_user_review")
            elif self.shadow_mode:
                reasons.append("shadow_mode_no_memory_materialization")
            else:
                target_tier = MemoryTier.SHORT_TERM.value
                materialized_memory_id = self._materialize_l2(scene, evaluation, anchors)
                reasons.append("materialized_as_inferred_short_term_candidate")

        return RestConsolidationDecision(
            decision_id=uuid.uuid4().hex,
            scene_id=scene.scene_id,
            disposition=disposition,
            target_tier=target_tier,
            automatic_l3_allowed=False,
            real_source_anchor_count=len(anchors),
            materialized_memory_id=materialized_memory_id,
            reasons=tuple(reasons),
            decided_at_utc=decided_at_utc or datetime.now(timezone.utc).isoformat(),
        )

    def _materialize_l2(
        self,
        scene: DreamScene,
        evaluation: DreamEvaluation,
        anchors: list[RestReplayItem],
    ) -> str:
        evidence = tuple(
            SourceEvidence(
                source_type="rest_replay_anchor",
                source_id=item.source_memory_id,
                source_sha256=item.provenance.get("memory_record_content_sha256") or item.content_sha256,
                metadata={
                    "rest_scene_id": scene.scene_id,
                    "rest_scene_sha256": scene.content_sha256,
                    "simulation_kind": scene.simulation_kind.value,
                    "synthetic_source_is_not_factual_evidence": True,
                },
            )
            for item in anchors
        )
        kind = MemoryKind.PROCEDURAL if evaluation.recommended_disposition is RestConsolidationDisposition.PROCEDURE_CANDIDATE else MemoryKind.REFLECTION
        record = ShortTermMemoryPolicy().create(
            kind=kind,
            content=scene.content,
            domain="rest_reflection",
            mode="rest_internal_simulation",
            truth_status=MemoryTruthStatus.INFERRED,
            confidence=max(0.05, min(0.75, evaluation.groundedness * 0.65)),
            importance=max(0.05, min(0.70, evaluation.utility * 0.70)),
            evidence=evidence,
            tags=("rest", "simulated_internal", scene.simulation_kind.value, "requires_review"),
        )
        with MemoryTierCoreStore(self.config.memory_tier_db_path) as store:
            store.save_record(record)
        return record.memory_id
