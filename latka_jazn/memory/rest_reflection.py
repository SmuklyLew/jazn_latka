from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from latka_jazn.memory.rest_contracts import (
    DreamEvaluation,
    DreamScene,
    RestConsolidationDisposition,
    RestReplayItem,
)
from latka_jazn.memory.rest_replay import RestReplayEngine
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("rest_reflection_evaluation")
_TOKEN_RE = re.compile(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ-]{3,}", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}


class RestReflectionEvaluator:
    """Deterministic first-pass evaluator for synthetic rest scenes.

    It intentionally does not ask the same model that generated a scene to certify
    the scene as factual. The output is a bounded recommendation for the existing
    memory gate, never factual evidence.
    """

    def evaluate(
        self,
        scene: DreamScene,
        replay_items: list[RestReplayItem],
        *,
        created_at_utc: str | None = None,
    ) -> DreamEvaluation:
        source_tokens = set().union(*(_tokens(item.content) for item in replay_items)) if replay_items else set()
        scene_tokens = _tokens(scene.content)
        overlap = len(scene_tokens & source_tokens) / max(1, len(scene_tokens))
        anchor_count = sum(1 for item in replay_items if RestReplayEngine.is_real_source_anchor(item))
        source_consistency = min(1.0, overlap * 1.35 + min(anchor_count, 3) * 0.08)
        groundedness = min(1.0, overlap + min(anchor_count, 3) * 0.12)
        novelty = max(0.0, min(1.0, 1.0 - overlap))
        length_score = min(1.0, len(scene.content.strip()) / 700.0)
        utility = max(0.0, min(1.0, 0.40 * groundedness + 0.25 * novelty + 0.35 * length_score))
        self_reference_terms = ("na pewno wydarzyło", "pamiętam że", "użytkownik powiedział", "to jest fakt", "naprawdę śniłam")
        lowered = scene.content.lower()
        self_reference_risk = min(1.0, 0.28 * sum(term in lowered for term in self_reference_terms))
        uncertainty = max(0.0, min(1.0, 1.0 - 0.55 * groundedness - 0.25 * source_consistency + 0.20 * self_reference_risk))

        reasons: list[str] = [
            f"source_overlap={overlap:.3f}",
            f"real_source_anchor_count={anchor_count}",
            f"simulation_kind={scene.simulation_kind.value}",
            "synthetic_scene_is_not_factual_evidence",
        ]
        if anchor_count == 0:
            disposition = RestConsolidationDisposition.REST_TRANSIENT
            reasons.append("no_real_source_anchor")
        elif self_reference_risk >= 0.45 or source_consistency < 0.18:
            disposition = RestConsolidationDisposition.DISCARD
            reasons.append("high_self_reference_or_low_source_consistency")
        elif groundedness >= 0.34 and utility >= 0.38:
            disposition = RestConsolidationDisposition.REFLECTION_CANDIDATE
            reasons.append("bounded_reflection_candidate")
        else:
            disposition = RestConsolidationDisposition.REST_TRANSIENT
            reasons.append("insufficient_value_for_memory_candidate")

        return DreamEvaluation(
            evaluation_id=uuid.uuid4().hex,
            scene_id=scene.scene_id,
            groundedness=groundedness,
            source_consistency=source_consistency,
            novelty=novelty,
            utility=utility,
            uncertainty=uncertainty,
            self_reference_risk=self_reference_risk,
            real_source_anchor_count=anchor_count,
            recommended_disposition=disposition,
            reasons=tuple(reasons),
            created_at_utc=created_at_utc or datetime.now(timezone.utc).isoformat(),
        )
