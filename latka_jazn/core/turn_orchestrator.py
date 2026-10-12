from __future__ import annotations

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
        self.context.build(state)
        self.dialogue.classify(state)
        self.frame.prepare_turn(state)
        self.affect.project(state)
        self.dialogue.resolve_and_execute(state)
        self.response.produce(state)
        self.validation.validate_candidate(state)
        self.recovery.resolve(state)
        self.validation.assess_reasoning(state)
        self.recovery.resolve_reasoning(state)
        self.validation.record_final_validation(state)
        self.recovery.classify_result(state)
        self.validation.complete_validation(state)
        self.response.build_provenance(state)
        self.response.build_contract(state)
        self.persistence.checkpoint(state)
        self.persistence.prepare_result(state)
        return TurnResult(state.envelope)
