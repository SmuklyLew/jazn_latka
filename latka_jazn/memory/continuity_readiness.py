from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from latka_jazn.config import JaznConfig
from latka_jazn.memory.conversation_archive import build_conversation_archive_status
from latka_jazn.memory.normalization_sidecar import (
    build_memory_normalization_status,
    build_wake_state_status,
)
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("memory_continuity_readiness")
TRUTH_BOUNDARY = (
    "Memory continuity readiness distinguishes searchable source memory from a verified wake-state. "
    "A missing or stale wake-state must not erase searchable history or force ordinary dialogue into a generic fallback, "
    "but it blocks claims of restored cross-session continuity until normalization coverage and wake validation are complete."
)


@dataclass(slots=True)
class MemoryContinuityReadinessStatus:
    schema_version: str
    status: str
    retrieval_ready: bool
    wake_context_ready: bool
    continuity_claim_allowed: bool
    ordinary_dialogue_allowed: bool
    memory_recall_allowed: bool
    recovery_required: bool
    fallback_policy: str
    normalization_status: str
    wake_state_status: str
    archive_status: str
    normalization_coverage: dict[str, Any]
    reasons: list[str]
    truth_boundary: str = TRUTH_BOUNDARY

    @property
    def ok(self) -> bool:
        return self.status == "verified"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "ok": self.ok}


def _mapping(value: Mapping[str, Any] | dict[str, Any] | None) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _coverage(normalization: dict[str, Any]) -> dict[str, Any]:
    run = _mapping(normalization.get("last_run"))
    expected = int(run.get("expected_item_count") or 0)
    normalized = int(run.get("normalized_item_count") or 0)
    complete = bool(run.get("coverage_complete"))
    ratio_value = run.get("coverage_ratio")
    try:
        ratio = float(ratio_value) if ratio_value is not None else (1.0 if expected == 0 and complete else 0.0)
    except (TypeError, ValueError):
        ratio = 0.0
    return {
        "expected_item_count": expected,
        "normalized_item_count": normalized,
        "coverage_complete": complete,
        "coverage_ratio": max(0.0, min(1.0, ratio)),
        "source_run_id": run.get("run_id"),
        "requested_limit": run.get("requested_limit"),
    }


def evaluate_memory_continuity_readiness(
    *,
    normalization_status: Mapping[str, Any] | dict[str, Any] | None,
    wake_state_status: Mapping[str, Any] | dict[str, Any] | None,
    conversation_archive_status: Mapping[str, Any] | dict[str, Any] | None,
) -> MemoryContinuityReadinessStatus:
    normalization = _mapping(normalization_status)
    wake = _mapping(wake_state_status)
    archive = _mapping(conversation_archive_status)

    norm_state = str(normalization.get("status") or "status_not_available")
    wake_state = str(wake.get("status") or "status_not_available")
    archive_state = str(archive.get("status") or "status_not_available")
    retrieval_ready = bool(archive.get("ready_for_search"))
    coverage = _coverage(normalization)
    normalization_ready = bool(
        norm_state == "ready"
        and coverage.get("coverage_complete") is True
        and int(coverage.get("normalized_item_count") or 0) >= int(coverage.get("expected_item_count") or 0)
    )
    wake_ready = bool(wake_state == "ready" and wake.get("active_snapshot_present") is True)
    verified = bool(normalization_ready and wake_ready)

    reasons: list[str] = []
    if not retrieval_ready:
        reasons.append(f"conversation_archive:{archive_state}")
    if not normalization_ready:
        reasons.append(f"normalization:{norm_state}")
    if not wake_ready:
        reasons.append(f"wake_state:{wake_state}")

    partial_states = {
        "normalization_partial",
        "normalization_coverage_unverified",
        "source_changed",
        "normalization_stale",
        "snapshot_coverage_unverified",
    }
    invalid_states = {
        "validation_failed",
        "sidecar_invalid",
        "snapshot_hash_mismatch",
        "source_run_invalid",
        "read_error",
    }

    if verified:
        status = "verified"
        fallback_policy = "use_verified_wake_and_retrieval"
        recovery_required = False
    elif norm_state in invalid_states or wake_state in invalid_states:
        status = "degraded_integrity"
        fallback_policy = (
            "use_searchable_archive_without_continuity_claim"
            if retrieval_ready
            else "use_current_turn_only_and_report_memory_unavailable"
        )
        recovery_required = True
    elif norm_state in partial_states or wake_state in partial_states:
        status = "partial_unverified"
        fallback_policy = (
            "use_searchable_archive_without_continuity_claim"
            if retrieval_ready
            else "use_current_turn_only_and_report_memory_unavailable"
        )
        recovery_required = True
    elif retrieval_ready:
        status = "retrieval_only"
        fallback_policy = "use_searchable_archive_without_continuity_claim"
        recovery_required = True
    else:
        status = "current_turn_only"
        fallback_policy = "use_current_turn_only_and_report_memory_unavailable"
        recovery_required = True

    return MemoryContinuityReadinessStatus(
        schema_version=SCHEMA_VERSION,
        status=status,
        retrieval_ready=retrieval_ready,
        wake_context_ready=verified,
        continuity_claim_allowed=verified,
        ordinary_dialogue_allowed=True,
        memory_recall_allowed=retrieval_ready,
        recovery_required=recovery_required,
        fallback_policy=fallback_policy,
        normalization_status=norm_state,
        wake_state_status=wake_state,
        archive_status=archive_state,
        normalization_coverage=coverage,
        reasons=reasons,
    )


def build_memory_continuity_readiness(
    config: JaznConfig,
    *,
    deep_verify: bool = False,
) -> MemoryContinuityReadinessStatus:
    archive = build_conversation_archive_status(
        config.root,
        health_mode="deep" if deep_verify else "metadata",
    ).to_dict()
    normalization = build_memory_normalization_status(config, deep_verify=deep_verify).to_dict()
    wake = build_wake_state_status(config, deep_verify=deep_verify).to_dict()
    return evaluate_memory_continuity_readiness(
        normalization_status=normalization,
        wake_state_status=wake,
        conversation_archive_status=archive,
    )
