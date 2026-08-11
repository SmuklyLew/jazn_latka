from __future__ import annotations

from latka_jazn.memory.continuity_readiness import evaluate_memory_continuity_readiness


def _normalization(status: str, *, expected: int = 10, normalized: int = 10, complete: bool = True):
    return {
        "status": status,
        "last_run": {
            "run_id": "run-1",
            "expected_item_count": expected,
            "normalized_item_count": normalized,
            "coverage_complete": complete,
            "coverage_ratio": 0.0 if expected == 0 else normalized / expected,
            "requested_limit": None,
        },
    }


def _wake(status: str, *, active: bool = False):
    return {"status": status, "active_snapshot_present": active}


def _archive(ready: bool):
    return {"status": "ready" if ready else "missing", "ready_for_search": ready}


def test_verified_continuity_requires_complete_normalization_and_ready_wake():
    status = evaluate_memory_continuity_readiness(
        normalization_status=_normalization("ready"),
        wake_state_status=_wake("ready", active=True),
        conversation_archive_status=_archive(True),
    )
    assert status.status == "verified"
    assert status.ok is True
    assert status.retrieval_ready is True
    assert status.wake_context_ready is True
    assert status.continuity_claim_allowed is True
    assert status.memory_recall_allowed is True
    assert status.ordinary_dialogue_allowed is True
    assert status.fallback_policy == "use_verified_wake_and_retrieval"


def test_missing_wake_does_not_disable_searchable_memory_or_ordinary_dialogue():
    status = evaluate_memory_continuity_readiness(
        normalization_status={"status": "sidecar_missing", "last_run": None},
        wake_state_status=_wake("sidecar_missing"),
        conversation_archive_status=_archive(True),
    )
    assert status.status == "retrieval_only"
    assert status.ok is False
    assert status.retrieval_ready is True
    assert status.memory_recall_allowed is True
    assert status.ordinary_dialogue_allowed is True
    assert status.continuity_claim_allowed is False
    assert status.fallback_policy == "use_searchable_archive_without_continuity_claim"


def test_partial_normalization_is_fail_closed_for_continuity_but_not_recall():
    status = evaluate_memory_continuity_readiness(
        normalization_status=_normalization("normalization_partial", expected=100, normalized=20, complete=False),
        wake_state_status=_wake("normalization_partial"),
        conversation_archive_status=_archive(True),
    )
    assert status.status == "partial_unverified"
    assert status.normalization_coverage["coverage_ratio"] == 0.2
    assert status.continuity_claim_allowed is False
    assert status.memory_recall_allowed is True
    assert status.ordinary_dialogue_allowed is True
    assert status.recovery_required is True


def test_integrity_failure_without_archive_restricts_memory_not_dialogue():
    status = evaluate_memory_continuity_readiness(
        normalization_status=_normalization("validation_failed"),
        wake_state_status=_wake("sidecar_invalid"),
        conversation_archive_status=_archive(False),
    )
    assert status.status == "degraded_integrity"
    assert status.memory_recall_allowed is False
    assert status.ordinary_dialogue_allowed is True
    assert status.continuity_claim_allowed is False
    assert status.fallback_policy == "use_current_turn_only_and_report_memory_unavailable"
