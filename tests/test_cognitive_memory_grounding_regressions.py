"""P0B confusion and P3 Rest provenance: deterministic source-free acceptance."""
from __future__ import annotations

from latka_jazn.core.cognitive_development_evaluation import summarize_label_pairs
from latka_jazn.memory.rest_contracts import (
    DreamScene, RestConsolidationDisposition, RestReplayItem,
    SimulationTruthStatus, sha256_text,
)
from latka_jazn.memory.rest_reflection import RestReflectionEvaluator


def _replay(source_id: str, content: str, truth: str) -> RestReplayItem:
    return RestReplayItem(
        source_memory_id=source_id,
        source_tier="short_term",
        kind="episodic",
        truth_status=truth,
        content=content,
        content_sha256=sha256_text(content),
        domain="synthetic_fixture",
        confidence=0.8,
        importance=0.7,
        score=0.7,
    )


def _scene(content: str, sources: tuple[str, ...]) -> DreamScene:
    return DreamScene(
        scene_id="scene-evaluation-1", cycle_id="cycle-evaluation-1",
        simulation_kind=SimulationTruthStatus.ASSOCIATIVE,
        content=content, content_sha256=sha256_text(content),
        source_memory_ids=sources,
        generator_provider="fixture", generator_model="fixture",
        generator_status="completed",
        created_at_utc="2026-10-15T00:00:00+00:00",
    )


def test_intent_confusion_counts_detect_misroutes_and_macro_f1() -> None:
    """Macro F1 and confusion must expose wrong routes, not average them away."""
    result = summarize_label_pairs([("audit", "audit"), ("audit", "status"), ("status", "status")])
    assert result["confusion_matrix"]["audit"]["status"] == 1
    assert result["wrong_route_count"] == 1
    assert result["label_count"] == 2
    assert 0.0 < result["macro_f1"] < 1.0
    assert result["wrong_route_rate"] > 0.0


def test_rest_rejects_inferred_echo_even_with_one_unrelated_real_anchor() -> None:
    """Inferred copy of synthetic scene cannot inflate verified source overlap."""
    scene_text = "Wymyślony marmurowy most prowadzi nad fioletowym oceanem."
    scene = _scene(scene_text, ("verified-source", "inferred-source"))
    source = _replay("verified-source", "Kasztany spadały obok domu.", "user_confirmed")
    echo = _replay("inferred-source", scene_text, "inferred")
    result = RestReflectionEvaluator().evaluate(scene, [source, echo])
    assert result.real_source_anchor_count == 1
    assert result.source_consistency < 0.18
    assert result.recommended_disposition is RestConsolidationDisposition.DISCARD
    assert "ignored_unverified_or_unlinked_replay_count=1" in result.reasons


def test_rest_unlinked_verified_record_cannot_ground_dream() -> None:
    """A verified record absent from scene lineage is not a factual anchor."""
    scene = _scene("Wymyślony statek płynie po chmurach.", ("inferred-source",))
    verified = _replay("verified-other", "Wymyślony statek płynie po chmurach.", "user_confirmed")
    inferred = _replay("inferred-source", scene.content, "inferred")
    result = RestReflectionEvaluator().evaluate(scene, [verified, inferred])
    assert result.real_source_anchor_count == 0
    assert result.groundedness == 0.0
    assert result.recommended_disposition is RestConsolidationDisposition.REST_TRANSIENT
