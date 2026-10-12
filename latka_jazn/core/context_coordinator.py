from __future__ import annotations

import time
from latka_jazn.core.turn_execution import TurnExecutionContext
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from latka_jazn.core.turn_pipeline_state import TurnPipelineState

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


@dataclass(frozen=True)
class TurnContextSnapshot:
    session_id: str
    client_context: dict[str, Any]
    carryover_allowed: bool
    previous_task_state: dict[str, Any]
    read_only_preview: bool


class ContextCoordinator:
    """Turn-local context coordinator over the existing runtime services."""

    def __init__(self, engine: JaznEngine) -> None:
        self.engine = engine

    def build(self, state: TurnPipelineState) -> TurnContextSnapshot:
        engine = self.engine
        state.ctx = dict(state.request.client_context or {})
        state.turn_context = state.ctx.pop("_turn_context", None)
        if not isinstance(state.turn_context, TurnExecutionContext):
            state.turn_context = None
        state.ctx.setdefault("client", "process_turn")
        state.ctx.setdefault("lifecycle", "one_shot")
        state.read_only_preview = engine._configure_preview_turn_context(state.ctx)
        state.no_carryover = bool(state.ctx.get("no_carryover"))
        state.initial_task_state = engine._initial_task_state_for_process_turn(state.ctx, no_carryover=state.no_carryover)
        engine._audit_process_turn_started(state.request.text, state.ctx)
        state.prior_turn_at = engine.last_turn_at
        state.prior_user_text = None if state.no_carryover else (state.ctx.get("previous_user_text") or engine.last_user_text)
        state.prior_visible_text = None if state.no_carryover else state.ctx.get("previous_visible_text")
        state.prior_detected_intent = state.ctx.get("previous_detected_intent") or engine.last_detected_intent
        state.prior_runtime_route = state.ctx.get("previous_runtime_route") or engine.last_runtime_route
        state.now_for_context = time.time()
        state.prior_context_age_seconds = int(state.now_for_context - state.prior_turn_at) if isinstance(state.prior_turn_at, (int, float)) else None
        state.turn_context_resolution = engine.turn_context_resolver.resolve(
            current_user_text=state.request.text,
            previous_user_text=state.prior_user_text,
            previous_intent=state.prior_detected_intent,
            previous_route=state.prior_runtime_route,
            session_id=str(state.ctx.get("session_id") or ""),
            no_carryover=state.no_carryover,
            time_gap_seconds=state.prior_context_age_seconds,
            explicit_previous_user_text=bool(state.ctx.get("previous_user_text")),
            previous_task_state=state.initial_task_state,
        )
        state.carryover_allowed = bool(state.turn_context_resolution.carryover_allowed)
        if state.carryover_allowed:
            state.ctx.setdefault("previous_user_text", state.prior_user_text)
            if state.prior_visible_text:
                state.ctx.setdefault("previous_visible_text", state.prior_visible_text)
            if state.prior_detected_intent:
                state.ctx.setdefault("previous_detected_intent", state.prior_detected_intent)
            if state.prior_runtime_route:
                state.ctx.setdefault("previous_runtime_route", state.prior_runtime_route)
            state.ctx.setdefault("previous_context_age_seconds", state.prior_context_age_seconds)
        if state.turn_context is not None:
            state.turn_context.start_stage("route_classification")
        state.previous_task_state = {} if state.no_carryover else engine._previous_task_state_for_turn(state.ctx, carryover_allowed=state.carryover_allowed)
        return TurnContextSnapshot(
            str(state.ctx.get("session_id") or ""), state.ctx,
            state.carryover_allowed, state.previous_task_state, state.read_only_preview,
        )
