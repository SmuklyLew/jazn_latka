from __future__ import annotations

from contextlib import nullcontext
import os
from typing import TYPE_CHECKING
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.turn_pipeline_state import TurnRequest, TurnResult, TurnPipelineState
from latka_jazn.core.context_coordinator import ContextCoordinator
from latka_jazn.core.cognitive_frame_builder import CognitiveFrameBuilder
from latka_jazn.core.affect_coordinator import AffectCoordinator
from latka_jazn.core.dialogue_router import DialogueRouter
from latka_jazn.core.response_pipeline import ResponsePipeline
from latka_jazn.core.validation_pipeline import ValidationPipeline
from latka_jazn.core.recovery_policy import RecoveryPolicy
from latka_jazn.core.persistence_coordinator import PersistenceCoordinator

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


class TurnOrchestrator:
    """Order one pipeline over existing services without owning another session."""

    def __init__(self, engine: JaznEngine) -> None:
        self.context = ContextCoordinator(engine)
        self.frame = CognitiveFrameBuilder(engine)
        self.affect = AffectCoordinator(engine)
        self.dialogue = DialogueRouter(engine)
        self.response = ResponsePipeline(engine)
        self.validation = ValidationPipeline(engine)
        self.recovery = RecoveryPolicy(engine)
        self.persistence = PersistenceCoordinator(engine)

    def process(self, request: TurnRequest, context: TurnExecutionContext | None = None) -> TurnResult:
        if context is not None:
            request = TurnRequest(request.text, {**request.client_context, "_turn_context": context})
        state = TurnPipelineState(request=request)
        # Opt-in, numeric-only diagnostics for the unaccounted Windows health
        # latency. No messages, source paths, model calls or private data are
        # recorded. Ordinary turns keep their original execution path.
        observed = context or request.client_context.get("_turn_context")
        measured = (
            os.environ.get("JAZN_TURN_LATENCY_DIAGNOSTICS") == "1"
            and isinstance(observed, TurnExecutionContext)
        )

        def span(name: str):
            return observed.stage(name) if measured else nullcontext()

        with span("pipeline_prepare"):
            self.context.build(state)
            self.dialogue.classify(state)
            self.frame.prepare_turn(state)
            self.affect.project(state)
        with span("pipeline_route"):
            self.dialogue.resolve_and_execute(state)
        with span("pipeline_response"):
            self.response.produce(state)
        with span("pipeline_validation"):
            self.validation.validate_candidate(state)
            self.recovery.resolve(state)
            self.validation.assess_reasoning(state)
            self.recovery.resolve_reasoning(state)
            self.validation.record_final_validation(state)
            self.recovery.classify_result(state)
            self.validation.complete_validation(state)
        with span("pipeline_settlement"):
            self.response.build_provenance(state)
            self.response.build_contract(state)
            self.persistence.checkpoint(state)
            self.persistence.prepare_result(state)
        return TurnResult(state.envelope)
