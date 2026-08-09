from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from latka_jazn.core.homeostasis import HomeostasisInput, HomeostasisRegulator
from latka_jazn.core.predictive_dialogue_engine import PredictiveDialogueEngine
from latka_jazn.core.reasoning_orchestrator import ReasoningOrchestrator
from latka_jazn.core.system_temporal_semantics import SystemTemporalSemantics, TemporalEvent
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("cognitive_runtime_coordinator")


@dataclass(slots=True)
class CognitiveRuntimeCoordinator:
    temporal: SystemTemporalSemantics = field(default_factory=SystemTemporalSemantics)
    homeostasis: HomeostasisRegulator = field(default_factory=HomeostasisRegulator)
    predictive: PredictiveDialogueEngine = field(default_factory=PredictiveDialogueEngine)
    reasoning: ReasoningOrchestrator = field(default_factory=ReasoningOrchestrator)

    def plan_turn(
        self,
        *,
        user_text: str,
        explicit_intent: str | None = None,
        temporal_events: list[TemporalEvent] | None = None,
        homeostasis_input: HomeostasisInput | None = None,
        dialogue_task_state: dict[str, Any] | None = None,
        classifier_confidence: float | None = None,
        source_available: bool = False,
        tool_available: bool = False,
    ) -> dict[str, Any]:
        predictions = self.predictive.predict(user_text, explicit_intent=explicit_intent)
        regulation = self.homeostasis.decide(homeostasis_input or HomeostasisInput())
        graph = self.temporal.build_graph(temporal_events or [])
        reasoning_plan = self.reasoning.plan(
            user_text=user_text,
            intent=explicit_intent or "unknown",
            task_state=dialogue_task_state,
            classifier_confidence=classifier_confidence,
            source_available=source_available,
            tool_available=tool_available,
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "predictions": [item.to_dict() for item in predictions],
            "regulation": regulation.to_dict(),
            "temporal_graph": graph,
            "explicit_intent": explicit_intent,
            "reasoning_plan": reasoning_plan.to_dict(),
            "prediction_may_override_user_intent": False,
            "truth_boundary": "Cognitive modules are operational models and cannot assert biological experience.",
        }
