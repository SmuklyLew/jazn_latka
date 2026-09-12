from __future__ import annotations

import pytest

from latka_jazn.memory.rest_contracts import (
    DreamScene,
    RestConsolidationDecision,
    RestConsolidationDisposition,
    SimulationTruthStatus,
    sha256_text,
)


def test_dream_scene_is_never_a_factual_claim() -> None:
    content = "Wewnętrzna symulacja alternatywnego rozwiązania."
    scene = DreamScene(
        scene_id="scene-1",
        cycle_id="cycle-1",
        simulation_kind=SimulationTruthStatus.COUNTERFACTUAL,
        content=content,
        content_sha256=sha256_text(content),
        source_memory_ids=("m1",),
        generator_provider="injected_test_generator",
        generator_model="test",
        generator_status="completed",
        created_at_utc="2026-08-11T20:00:00+00:00",
    )
    assert scene.factual_claim_allowed is False
    assert scene.to_dict()["factual_claim_allowed"] is False


def test_rest_consolidation_forbids_automatic_l3() -> None:
    with pytest.raises(ValueError, match="automatic L3"):
        RestConsolidationDecision(
            decision_id="d1",
            scene_id="s1",
            disposition=RestConsolidationDisposition.REFLECTION_CANDIDATE,
            target_tier="short_term",
            automatic_l3_allowed=True,
            real_source_anchor_count=1,
            materialized_memory_id=None,
            reasons=(),
            decided_at_utc="2026-08-11T20:00:00+00:00",
        )
    with pytest.raises(ValueError, match="long_term"):
        RestConsolidationDecision(
            decision_id="d2",
            scene_id="s1",
            disposition=RestConsolidationDisposition.REFLECTION_CANDIDATE,
            target_tier="long_term",
            automatic_l3_allowed=False,
            real_source_anchor_count=1,
            materialized_memory_id=None,
            reasons=(),
            decided_at_utc="2026-08-11T20:00:00+00:00",
        )
