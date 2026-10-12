from __future__ import annotations

from latka_jazn.version import PACKAGE_VERSION
from typing import TYPE_CHECKING
from latka_jazn.core.turn_pipeline_state import TurnPipelineState, FrameBuildState

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


class PersistenceCoordinator:
    """Turn-local persistence coordinator over the existing runtime services."""

    def __init__(self, engine: JaznEngine) -> None:
        self.engine = engine

    def checkpoint(self, state: TurnPipelineState) -> None:
        engine = self.engine
        try:
            state.checkpoint = engine._stage_turn_write(
                state.turn_context,
                data_type="turn_checkpoint",
                stage="host_visible_finalization",
                commit=lambda: engine.turn_checkpoint_writer.build_and_append(
                    turn_id=state.envelope.trace.turn_id, trace_id=state.envelope.trace.trace_id, timestamp_header=state.envelope.trace.timestamp_header, user_text=state.request.text, runtime_text=state.body, visible_text=state.contract.final_visible_text, detected_intent=str(state.detected_dialogue_intent), route=str(state.decision_dict.get("route") or ""), response_generation_mode=str(state.decision_dict.get("response_generation_mode") or "unknown"), template_origin=state.template_origin, validator=state.answer_validation.to_dict(), source_origin=state.envelope.cognitive_frame.get("source_origin_ledger_entry") or {},
                ),
            )
            state.envelope.cognitive_frame["turn_checkpoint"] = state.checkpoint
        except Exception as exc:
            state.envelope.cognitive_frame["turn_checkpoint_error"] = str(exc)

    def prepare_result(self, state: TurnPipelineState) -> None:
        engine = self.engine
        state.envelope_dict = state.envelope.to_dict()
        engine._stage_turn_write(
            state.turn_context,
            data_type="cognitive_turn_envelope",
            stage="host_visible_finalization",
            commit=lambda: engine.store.add_event(
                "cognitive_turn_envelope",
                state.envelope_dict,
                source=state.ctx.get("client", "process_turn"),
                actor="latka_runtime",
                tags=["cognitive_turn_envelope", "final_response_contract", "timestamp_contract", "dialogue_intent_classifier", "runtime_answer_validator", "source_origin_ledger", "project_startup_index", engine.config.version],
                importance=0.86,
                emotional_weight=0.55,
                canonical_impact=1,
                created_at_local=state.envelope.trace.timestamp_header,
            ),
        )
        engine._stage_turn_write(
            state.turn_context,
            data_type="runtime_event_ledger",
            stage="host_visible_finalization",
            commit=lambda: engine.event_ledger.append_event(
                "cognitive_turn_envelope",
                actor="latka_runtime",
                source=state.ctx.get("client", "process_turn"),
                payload=state.envelope_dict,
                tags=["cognitive_turn_envelope", "final_response_contract", "exact", "dialogue_intent_classifier", "runtime_answer_validator", "source_origin_ledger", engine.config.version],
                importance=0.86,
                emotional_weight=0.55,
                canonical_impact=1,
                exact_text=state.request.text,
                local_time_label=state.envelope.trace.timestamp_header,
            ),
        )
        engine._stage_turn_write(
            state.turn_context,
            data_type="final_visible_reply",
            stage="host_visible_finalization",
            commit=lambda: engine.event_ledger.append_final_visible_reply(
                state.envelope_dict,
                final_text=state.contract.final_visible_text,
                source=state.ctx.get("client", "process_turn"),
                local_time_label=state.envelope.trace.timestamp_header,
            ),
        )
        engine._stage_turn_write(
            state.turn_context,
            data_type="session_continuity",
            stage="host_visible_finalization",
            commit=lambda: engine.session_continuity.update_index(
                reason="final_visible_reply_persisted",
                source="JaznEngine.process_turn",
                extra={
                    "turn_id": state.envelope.trace.turn_id,
                    "trace_id": state.envelope.trace.trace_id,
                    "timestamp_header": state.envelope.trace.timestamp_header,
                    "client_context": state.ctx,
                    "final_visible_reply_sha256": state.envelope.cognitive_frame.get("final_visible_reply_sha256"),
                },
            ),
        )
        engine._stage_turn_write(
            state.turn_context,
            data_type="process_turn_completed_audit",
            stage="audit_persistence",
            commit=lambda: engine.audit_store.append_event("process_turn_completed", {"turn_id": state.envelope.trace.turn_id, "trace_id": state.envelope.trace.trace_id, "detected_intent": str(state.detected_dialogue_intent), "route": str(state.decision_dict.get("route") or state.route_entry.route or ""), "runtime_answer_quality": (state.answer_validation.to_dict() or {}).get("runtime_answer_quality")}, source=state.ctx.get("client", "process_turn"), actor="latka_runtime", tags=["turn", "completed", "audit", engine.config.version], trace_id=state.envelope.trace.trace_id, turn_id=state.envelope.trace.turn_id),
        )

        def _commit_engine_turn_state() -> None:
            engine.last_user_text = state.request.text
            engine.last_detected_intent = str(state.detected_dialogue_intent)
            engine.last_runtime_route = str(state.decision_dict.get("route") or state.route_entry.route or "")
            engine.last_dialogue_task_state = dict(state.current_dialogue_task_state or {})
            engine._save_runtime_state()

        engine._stage_turn_write(
            state.turn_context,
            data_type="engine_turn_state",
            stage="host_visible_finalization",
            commit=_commit_engine_turn_state,
        )
        # Keep shutdown read-only for preview too; shutdown clears the flag only
        # after closing stores. Normal process_turn clears immediately.
        if not state.read_only_preview:
            engine._preview_read_only_active = False

    def prepare_frame_result(self, state: FrameBuildState) -> None:
        engine = self.engine
        engine._stage_turn_write(
            state.turn_context,
            data_type="cognitive_frame_event",
            stage="cognitive_frame_complete",
            commit=lambda: engine.store.add_event(
                "chatgpt_cognitive_frame",
                state.packet,
                source=(state.request.client_context or {}).get("client", "chatgpt_cognitive_bridge"),
                actor="latka_runtime",
                tags=["chatgpt_bridge", "cognitive_frame", "one_voice", "logical_reasoning", "operational_awareness", "polish_understanding", "lexical_semantic_understanding", "polish_nlp", "topic_mismatch_guard", "project_startup_index", "cognitive_packets", "runtime_operating_model", "github_repository_plan", "source_origin", "self_state_runtime", "free_dialogue_memory_nlp_bridge", PACKAGE_VERSION],
                importance=max(state.importance.importance, state.consolidation_plan.weights.total, 0.72),
                emotional_weight=max(engine.affect.tension, state.importance.emotional_weight, state.emotional_profile.arousal),
                canonical_impact=max(state.importance.canonical_impact, 1 if "architecture" in state.packet["intent_tags"] or "correction" in state.packet["intent_tags"] or "identity_continuity" in state.packet["intent_tags"] else 0),
                created_at_local=engine.clock.header(state.sample),
            ),
        )
        engine._stage_turn_write(
            state.turn_context,
            data_type="runtime_event_ledger",
            stage="cognitive_frame_complete",
            commit=lambda: engine.event_ledger.append_event(
                "chatgpt_cognitive_frame",
                actor="latka_runtime",
                source=(state.request.client_context or {}).get("client", "chatgpt_cognitive_bridge"),
                payload=state.packet,
                tags=["chatgpt_bridge", "cognitive_frame", "exact", "logical_reasoning", "operational_awareness", "polish_understanding", "lexical_semantic_understanding", "polish_nlp", "runtime_operating_model", "github_repository_plan", "source_origin", "self_state_runtime", "free_dialogue_memory_nlp_bridge", PACKAGE_VERSION],
                importance=max(state.importance.importance, state.consolidation_plan.weights.total, 0.72),
                emotional_weight=max(engine.affect.tension, state.importance.emotional_weight, state.emotional_profile.arousal),
                canonical_impact=max(state.importance.canonical_impact, 1 if "architecture" in state.packet["intent_tags"] or "correction" in state.packet["intent_tags"] or "identity_continuity" in state.packet["intent_tags"] else 0),
                exact_text=state.request.text,
                local_time_label=engine.clock.header(state.sample),
            ),
        )
