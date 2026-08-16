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
        evidence={"rest_cycle_count": 2, "dream_scene_count": 1},
    )

    assert len(assessments) == 1
    assert assessments[0].status is EpistemicClaimStatus.SUPPORTED


def test_negative_dream_statement_needs_no_positive_evidence() -> None:
    assessments = EpistemicClaimGuard().enforce("Nie śniłam tej nocy.")

    assert len(assessments) == 1
    assert assessments[0].status is EpistemicClaimStatus.NEGATED


def test_background_claim_requires_verified_daemon_and_events() -> None:
    guard = EpistemicClaimGuard()

    with pytest.raises(EpistemicClaimViolation):
        guard.enforce("Pracowałam w tle, kiedy Cię nie było.")

    assessments = guard.enforce(
        "Pracowałam w tle, kiedy Cię nie było.",
        evidence={"daemon_verified": True, "background_event_count": 3},
    )

    assert assessments[0].status is EpistemicClaimStatus.SUPPORTED


def test_daemon_without_recorded_background_events_is_not_enough() -> None:
    with pytest.raises(EpistemicClaimViolation):
        EpistemicClaimGuard().enforce(
            "Pracowałam w tle.",
            evidence={"daemon_verified": True, "background_event_count": 0},
        )
