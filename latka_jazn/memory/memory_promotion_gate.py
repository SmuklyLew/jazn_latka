from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import StrEnum
from typing import Any, Iterable

from latka_jazn.memory.rest_contracts import RestReplayItem
from latka_jazn.memory.rest_replay import RestReplayEngine
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("memory_promotion_gate")


class PromotionDecision(StrEnum):
    ALLOW_INFERRED_L2 = "allow_inferred_l2"
    REQUIRE_USER_REVIEW = "require_user_review"
    DENY = "deny"


@dataclass(slots=True, frozen=True)
class MemoryPromotionAssessment:
    decision: PromotionDecision
    real_source_anchor_count: int
    distinct_source_count: int
    source_conflict_detected: bool
    synthetic_source: bool
    target_tier: str
    reasons: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Synthetic or inferred content cannot become factual long-term memory automatically. "
        "At most, source-anchored synthetic output may become an inferred short-term candidate."
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        return data


class MemoryPromotionGate:
    """Deterministic gate between generated/reflected content and memory tiers."""

    @staticmethod
    def _source_identity(item: RestReplayItem) -> str:
        provenance = dict(item.provenance or {})
        for key in ("source_sha256", "source_file", "source_row_id", "memory_record_content_sha256"):
            value = str(provenance.get(key) or "").strip()
            if value:
                return f"{key}:{value}"
        return f"memory:{item.source_memory_id}"

    def assess_rest_candidate(
        self,
        replay_items: Iterable[RestReplayItem],
        *,
        target_tier: str,
        synthetic_source: bool = True,
    ) -> MemoryPromotionAssessment:
        items = list(replay_items)
        anchors = [item for item in items if RestReplayEngine.is_real_source_anchor(item)]
        source_ids = {self._source_identity(item) for item in anchors}
        source_to_hashes: dict[str, set[str]] = {}
        for item in anchors:
            source_to_hashes.setdefault(self._source_identity(item), set()).add(item.content_sha256)
        conflict = any(len(hashes) > 1 for hashes in source_to_hashes.values())
        reasons: list[str] = []

        if target_tier == "long_term":
            decision = PromotionDecision.DENY
            reasons.append("automatic_long_term_promotion_forbidden")
        elif not anchors:
            decision = PromotionDecision.DENY
            reasons.append("no_real_source_anchor")
        elif conflict:
            decision = PromotionDecision.REQUIRE_USER_REVIEW
            reasons.append("source_identity_has_conflicting_content_hashes")
        elif synthetic_source:
            decision = PromotionDecision.ALLOW_INFERRED_L2
            reasons.append("synthetic_output_may_only_be_inferred_short_term")
        else:
            decision = PromotionDecision.REQUIRE_USER_REVIEW
            reasons.append("non_synthetic_promotion_requires_explicit_review_path")

        return MemoryPromotionAssessment(
            decision=decision,
            real_source_anchor_count=len(anchors),
            distinct_source_count=len(source_ids),
            source_conflict_detected=conflict,
            synthetic_source=synthetic_source,
            target_tier=target_tier,
            reasons=tuple(reasons),
        )
