from __future__ import annotations


from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from latka_jazn.core.turn_pipeline_state import TurnPipelineState, FrameBuildState

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


@dataclass(frozen=True)
class AffectRequest:
    text: str
    intent_tags: list[str]
    granular: dict[str, Any]
    emotional_profile: dict[str, Any]


@dataclass(frozen=True)
class AffectProjection:
    payload: dict[str, Any]
    source: str = "existing_runtime_affect"
    advisory: bool = True
    creates_durable_authority: bool = False


class AffectCoordinator:
    """Turn-local affect coordinator over the existing runtime services."""

    def __init__(self, engine: JaznEngine) -> None:
        self.engine = engine

    def evaluate(self, request: AffectRequest) -> AffectProjection:
        return AffectProjection(self.engine.affect_mixer.mix(
            user_text=request.text, intent_tags=request.intent_tags,
            affective_state=self.engine.affect, granular_affect=request.granular,
            emotional_profile=request.emotional_profile,
        ).to_dict())

    def project(self, state: TurnPipelineState) -> None:
        engine = self.engine
        state.granular = state.frame.get("granular_affect") or state.frame.get("cognitive_packets", {}).get("affect") or {}
        state.emotional_profile = state.frame.get("emotional_profile") or {}
        projection = self.evaluate(AffectRequest(
            state.request.text, state.frame.get("intent_tags") or [],
            state.granular if isinstance(state.granular, dict) else {},
            state.emotional_profile if isinstance(state.emotional_profile, dict) else {},
        ))
        state.affect_mix = projection.payload
        state.dialogue_state = engine.dialogue_state_tracker.classify(
            user_text=state.request.text,
            intent_tags=state.frame.get("intent_tags") or [],
            client_context=state.ctx,
        ).to_dict()
        state.envelope.attach_affect_mix(state.affect_mix)
        state.envelope.attach_dialogue_state(state.dialogue_state)

    def project_frame(self, state: FrameBuildState) -> None:
        engine = self.engine
        engine.affect = engine.affect.observe(state.request.text)
        state.temporal_state = engine.temporal_awareness.classify_gap(state.gap)
        state.emotional_profile = engine.emotional_layers.appraise(state.request.text, state.gap)
        state.importance = engine.importance_assessor.assess(state.request.text)
        if state.turn_context is not None:
            state.turn_context.start_stage("truth_audit_generation")
        state.user_truth_audit = engine.layered_memory.evaluate_truth(state.request.text, source_count=0)
        if state.turn_context is not None:
            state.turn_context.record_technical_event(
                "technical_turn_truth_audit",
                {
                    "text_sha256": __import__("hashlib").sha256(state.request.text.encode("utf-8", errors="surrogatepass")).hexdigest(),
                    "audit": state.user_truth_audit,
                    "memory_allowed": False,
                    "category": "technical_turn_audit",
                },
            )
            state.turn_context.complete_stage("truth_audit_generation")
        state.truth_risk = min(1.0, 0.18 * sum(1 for a in state.user_truth_audit if a.get("risk_flags")))
        if state.turn_context is not None:
            state.turn_context.start_stage("memory_planning")
        state.consolidation_plan = engine.consolidation.plan(
            text=state.request.text,
            emotional_profile=state.emotional_profile,
            source_count=0,
            silence_gap_seconds=state.gap,
            truth_risk=state.truth_risk,
        )
        if state.turn_context is not None:
            state.turn_context.complete_stage("memory_planning")
        state.identity_vector = engine.identity_dynamics.evaluate(
            text=state.request.text,
            truth_audit=state.user_truth_audit,
            temporal_state=state.temporal_state,
            emotional_profile=state.emotional_profile,
            procedural_rules_count=engine.store.stats().get("procedural_rules", 0),
        )
        state.neuro_cycle = engine.neuro_loop.run(
            text=state.request.text,
            emotional_profile=state.emotional_profile,
            consolidation_plan=state.consolidation_plan,
            identity_vector=state.identity_vector,
            temporal_state=state.temporal_state,
            truth_audit=state.user_truth_audit,
        )
