from __future__ import annotations

import pytest

from latka_jazn.core.epistemic_claim_guard import (
    EpistemicClaimGuard,
    EpistemicClaimStatus,
    EpistemicClaimViolation,
)


def test_dream_claim_requires_verified_rest_and_scene_evidence() -> None:
    guard = EpistemicClaimGuard()

    with pytest.raises(EpistemicClaimViolation):
        guard.enforce("Śniłam dziś w nocy o naszej książce.")

    assessments = guard.enforce(
        "Śniłam dziś w nocy o naszej książce.",
        evidence={
            "rest_continuity_status": "rest_verified",
            "rest_cycle_count": 2,
            "dream_scene_count": 1,
            "dream_scene_ids": ["scene-1"],
            "rest_report_id": "report-1",
            "rest_report_sha256": "a" * 64,
        },
    )

    assert len(assessments) == 1
    assert assessments[0].status is EpistemicClaimStatus.SUPPORTED


def test_rest_counts_without_verified_hash_report_are_not_enough() -> None:
    with pytest.raises(EpistemicClaimViolation):
        EpistemicClaimGuard().enforce(
            "Śniłam tej nocy.",
            evidence={"rest_cycle_count": 1, "dream_scene_count": 1},
        )


def test_negative_dream_statement_needs_no_positive_evidence() -> None:
    assessments = EpistemicClaimGuard().enforce("Nie śniłam tej nocy.")

    assert len(assessments) == 1
    assert assessments[0].status is EpistemicClaimStatus.NEGATED


def test_background_claim_requires_verified_daemon_events_and_event_ids() -> None:
    guard = EpistemicClaimGuard()

    with pytest.raises(EpistemicClaimViolation):
        guard.enforce("Pracowałam w tle, kiedy Cię nie było.")

    assessments = guard.enforce(
        "Pracowałam w tle, kiedy Cię nie było.",
        evidence={
            "daemon_verified": True,
            "background_event_count": 3,
            "background_event_ids": ["evt-1", "evt-2", "evt-3"],
        },
    )

    assert assessments[0].status is EpistemicClaimStatus.SUPPORTED


def test_daemon_without_recorded_background_events_is_not_enough() -> None:
    with pytest.raises(EpistemicClaimViolation):
        EpistemicClaimGuard().enforce(
            "Pracowałam w tle.",
            evidence={"daemon_verified": True, "background_event_count": 0},
        )


def test_background_count_without_event_identifiers_is_not_enough() -> None:
    with pytest.raises(EpistemicClaimViolation):
        EpistemicClaimGuard().enforce(
            "Pracowałam w tle.",
            evidence={"daemon_verified": True, "background_event_count": 2},
        )
