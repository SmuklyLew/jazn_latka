from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
import hashlib
import json

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("rest_experience_contract")
TRUTH_BOUNDARY = (
    "Rest/replay/dream records describe auditable internal computation. A simulated scene is never "
    "an observed event, user-confirmed fact, canonical memory, biological dream, or proof of consciousness."
)


class RestEpisodeStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class RestCycleStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class SimulationTruthStatus(StrEnum):
    SIMULATED_INTERNAL = "simulated_internal"
    COUNTERFACTUAL = "counterfactual"
    REHEARSAL = "rehearsal"
    ASSOCIATIVE = "associative"


class RestConsolidationDisposition(StrEnum):
    DISCARD = "discard"
    REST_TRANSIENT = "rest_transient"
    REFLECTION_CANDIDATE = "reflection_candidate"
    PROCEDURE_CANDIDATE = "procedure_candidate"
    USER_REVIEW_REQUIRED = "user_review_required"


class RestContinuityStatus(StrEnum):
    REST_VERIFIED = "rest_verified"
    REST_PARTIAL = "rest_partial"
    REST_NONE = "rest_none"
    REST_INTEGRITY_FAILED = "rest_integrity_failed"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(slots=True, frozen=True)
class RestReplayItem:
    source_memory_id: str
    source_tier: str
    kind: str
    truth_status: str
    content: str
    content_sha256: str
    domain: str
    confidence: float
    importance: float
    score: float
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = TRUTH_BOUNDARY

    def __post_init__(self) -> None:
        if not self.source_memory_id.strip():
            raise ValueError("source_memory_id is required")
        if self.content_sha256 != sha256_text(self.content):
            raise ValueError("replay content hash mismatch")
        if not 0.0 <= float(self.score) <= 1.0:
            raise ValueError("replay score must be between 0 and 1")

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_content:
            data.pop("content", None)
        return data


@dataclass(slots=True, frozen=True)
class DreamScene:
    scene_id: str
    cycle_id: str
    simulation_kind: SimulationTruthStatus
    content: str
    content_sha256: str
    source_memory_ids: tuple[str, ...]
    generator_provider: str
    generator_model: str
    generator_status: str
    created_at_utc: str
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = TRUTH_BOUNDARY

    def __post_init__(self) -> None:
        if not self.scene_id.strip() or not self.cycle_id.strip():
            raise ValueError("scene_id and cycle_id are required")
        if not self.content.strip():
            raise ValueError("dream scene content is required")
        if self.content_sha256 != sha256_text(self.content):
            raise ValueError("dream scene content hash mismatch")

    @property
    def factual_claim_allowed(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["simulation_kind"] = self.simulation_kind.value
        data["factual_claim_allowed"] = False
        return data


@dataclass(slots=True, frozen=True)
class DreamEvaluation:
    evaluation_id: str
    scene_id: str
    groundedness: float
    source_consistency: float
    novelty: float
    utility: float
    uncertainty: float
    self_reference_risk: float
    real_source_anchor_count: int
    recommended_disposition: RestConsolidationDisposition
    reasons: tuple[str, ...]
    created_at_utc: str
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = TRUTH_BOUNDARY

    def __post_init__(self) -> None:
        for name in ("groundedness", "source_consistency", "novelty", "utility", "uncertainty", "self_reference_risk"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.real_source_anchor_count < 0:
            raise ValueError("real_source_anchor_count cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["recommended_disposition"] = self.recommended_disposition.value
        return data


@dataclass(slots=True, frozen=True)
class RestConsolidationDecision:
    decision_id: str
    scene_id: str
    disposition: RestConsolidationDisposition
    target_tier: str | None
    automatic_l3_allowed: bool
    real_source_anchor_count: int
    materialized_memory_id: str | None
    reasons: tuple[str, ...]
    decided_at_utc: str
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Rest consolidation may create at most an inferred L2 candidate. Automatic L3 promotion is forbidden; "
        "synthetic content cannot serve as its own factual evidence."
    )

    def __post_init__(self) -> None:
        if self.automatic_l3_allowed:
            raise ValueError("automatic L3 promotion from rest cycles is forbidden")
        if self.target_tier == "long_term":
            raise ValueError("rest cycles cannot target long_term")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["disposition"] = self.disposition.value
        return data
