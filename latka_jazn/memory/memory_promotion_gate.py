from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable
import re

from latka_jazn.memory.rest_contracts import RestReplayItem
from latka_jazn.memory.rest_replay import RestReplayEngine
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("memory_promotion_gate")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class PromotionDecision(StrEnum):
    ALLOW_INFERRED_L2 = "allow_inferred_l2"
    REQUIRE_USER_REVIEW = "require_user_review"
    DENY = "deny"


@dataclass(slots=True, frozen=True)
class MemoryPromotionAssessment:
    decision: PromotionDecision
    truth_eligible_source_count: int
    real_source_anchor_count: int
    distinct_source_count: int
    source_conflict_detected: bool
    synthetic_source: bool
    target_tier: str
    reasons: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Synthetic or inferred content cannot become factual long-term memory automatically. "
        "A real anchor needs both an eligible truth status and bounded source provenance with integrity."
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        return data


class MemoryPromotionGate:
    """Deterministic fail-closed gate between generated content and memory tiers."""

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _source_identity(cls, item: RestReplayItem) -> str | None:
        provenance = dict(item.provenance or {})
        source_table = cls._clean(provenance.get("source_table"))
        source_row = cls._clean(provenance.get("source_row_id"))
        if source_table and source_row:
            return f"table:{source_table}:{source_row}"
        source_file = cls._clean(provenance.get("source_file"))
        if source_file:
            return f"file:{source_file}"
        source_uri = cls._clean(provenance.get("source_uri"))
        if source_uri:
            return f"uri:{source_uri}"
        record_id = cls._clean(provenance.get("source_record_id"))
        if record_id:
            return f"record:{record_id}"
        evidence_keys = provenance.get("source_evidence_keys")
        if isinstance(evidence_keys, (list, tuple)):
            verified_keys = [
                cls._clean(value).lower()
                for value in evidence_keys
                if _SHA256.fullmatch(cls._clean(value).lower())
            ]
            if verified_keys:
                return f"evidence:{verified_keys[0]}"
        return None

    @classmethod
    def _source_integrity(cls, item: RestReplayItem) -> str | None:
        provenance = dict(item.provenance or {})
        for key in ("source_sha256", "memory_record_content_sha256", "normalized_content_hash"):
            value = cls._clean(provenance.get(key)).lower()
            if _SHA256.fullmatch(value):
                return value
        return None

    @classmethod
    def is_verified_source_anchor(cls, item: RestReplayItem) -> bool:
        return bool(
            RestReplayEngine.is_real_source_anchor(item)
            and cls._source_identity(item)
            and cls._source_integrity(item)
        )

    def assess_rest_candidate(
        self,
        replay_items: Iterable[RestReplayItem],
        *,
        target_tier: str,
        synthetic_source: bool = True,
    ) -> MemoryPromotionAssessment:
        items = list(replay_items)
        eligible = [item for item in items if RestReplayEngine.is_real_source_anchor(item)]
        anchors = [item for item in eligible if self.is_verified_source_anchor(item)]
        identities = [self._source_identity(item) for item in anchors]
        source_ids = {identity for identity in identities if identity}
        source_to_hashes: dict[str, set[str]] = {}
        for item in anchors:
            identity = self._source_identity(item)
            if identity:
                source_to_hashes.setdefault(identity, set()).add(item.content_sha256)
        conflict = any(len(hashes) > 1 for hashes in source_to_hashes.values())
        reasons: list[str] = []

        if target_tier == "long_term":
            decision = PromotionDecision.DENY
            reasons.append("automatic_long_term_promotion_forbidden")
        elif not anchors:
            decision = PromotionDecision.DENY
            reasons.append("no_verified_real_source_anchor")
            if eligible:
                reasons.append("truth_status_without_provenance_is_not_an_anchor")
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
            truth_eligible_source_count=len(eligible),
            real_source_anchor_count=len(anchors),
            distinct_source_count=len(source_ids),
            source_conflict_detected=conflict,
            synthetic_source=synthetic_source,
            target_tier=target_tier,
            reasons=tuple(reasons),
        )
