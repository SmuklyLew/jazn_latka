from __future__ import annotations

from datetime import datetime, timezone

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import MemoryTier, MemoryTruthStatus
from latka_jazn.memory.rest_consolidation import RestConsolidationGate
from latka_jazn.memory.rest_contracts import (
    DreamEvaluation,
    DreamScene,
    RestConsolidationDisposition,
    RestReplayItem,
    SimulationTruthStatus,
    sha256_text,
)
from latka_jazn.memory.rest_reflection import RestReflectionEvaluator


def _item() -> RestReplayItem:
    text = "Audytowalny proces odpoczynku ma zachowywać źródła i nie udawać faktów."
    return RestReplayItem(
        source_memory_id="source-1", source_tier="short_term", kind="reflection",
        truth_status="user_confirmed", content=text, content_sha256=sha256_text(text),
        domain="project", confidence=0.95, importance=0.9, score=0.91,
        provenance={"memory_record_content_sha256": sha256_text(text)},
    )


def _scene() -> DreamScene:
    text = "Audytowalny proces odpoczynku może zachowywać źródła i oznaczać wewnętrzną symulację."
    return DreamScene(
        scene_id="scene-1", cycle_id="cycle-1", simulation_kind=SimulationTruthStatus.ASSOCIATIVE,
        content=text, content_sha256=sha256_text(text), source_memory_ids=("source-1",),
        generator_provider="test", generator_model="test", generator_status="completed",
        created_at_utc="2026-08-11T20:00:00+00:00",
    )


def test_reflection_evaluator_requires_real_anchor_for_candidate() -> None:
    evaluation = RestReflectionEvaluator().evaluate(_scene(), [_item()])
    assert evaluation.real_source_anchor_count == 1
    assert evaluation.recommended_disposition is RestConsolidationDisposition.REFLECTION_CANDIDATE
    inferred_item = _item().__class__(**{**_item().to_dict(), "truth_status": "inferred"})
    no_anchor = RestReflectionEvaluator().evaluate(_scene(), [inferred_item])
    assert no_anchor.recommended_disposition is RestConsolidationDisposition.REST_TRANSIENT


def test_shadow_mode_never_materializes_memory(tmp_path) -> None:
    config = JaznConfig(root=tmp_path, rest_shadow_mode=True)
    evaluation = RestReflectionEvaluator().evaluate(_scene(), [_item()])
    decision = RestConsolidationGate(config).decide(_scene(), evaluation, [_item()])
    assert decision.materialized_memory_id is None
    assert decision.target_tier is None
    assert decision.automatic_l3_allowed is False


def test_non_shadow_mode_materializes_only_inferred_l2(tmp_path) -> None:
    config = JaznConfig(root=tmp_path, rest_shadow_mode=False)
    evaluation = DreamEvaluation(
        evaluation_id="eval-1", scene_id="scene-1", groundedness=0.8, source_consistency=0.8,
        novelty=0.4, utility=0.8, uncertainty=0.2, self_reference_risk=0.0,
        real_source_anchor_count=1, recommended_disposition=RestConsolidationDisposition.REFLECTION_CANDIDATE,
        reasons=("test",), created_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    decision = RestConsolidationGate(config).decide(_scene(), evaluation, [_item()])
    assert decision.target_tier == "short_term"
    assert decision.materialized_memory_id
    assert decision.automatic_l3_allowed is False
    with MemoryTierStore(config.memory_tier_db_path) as store:
        record = store.get_record(decision.materialized_memory_id)
        assert record is not None
        assert record.tier is MemoryTier.SHORT_TERM
        assert record.truth_status is MemoryTruthStatus.INFERRED
        assert "requires_review" in record.tags
