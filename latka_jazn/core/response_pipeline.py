from __future__ import annotations

from latka_jazn.core.final_response_contract import FinalResponseContract
from latka_jazn.core.visible_integrity import evaluate_origin_truth
from latka_jazn.core.response_generation_mode import build_runtime_provenance
from latka_jazn.core.source_text_preservation_contract import SourceTextPreservationContract
from latka_jazn.core.runtime_turn_contract import RuntimeTurnContract
from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING, Any
from latka_jazn.core.turn_pipeline_state import TurnPipelineState
from latka_jazn.core.turn_pipeline_support import _sync_conversation_decision_body

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


@dataclass(frozen=True)
class ResponsePlan:
    route: str
    handler: str
    required_points: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    exact_runtime_required: bool
    source_truth_owned_by: str = "runtime"
    model_may_create_facts: bool = False
    model_may_commit_memory: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResponsePipeline:
    """Turn-local response pipeline over the existing runtime services."""

    def __init__(self, engine: JaznEngine) -> None:
        self.engine = engine

    def build_plan(self, state: TurnPipelineState) -> ResponsePlan:
        policy = state.turn_response_policy
        recall = state.frame.get("memory_recall_contract") or {}
        items = recall.get("items") or [] if isinstance(recall, dict) else []
        refs = tuple(str(item.get("item_id") or item.get("source_id")) for item in items
                     if isinstance(item, dict) and (item.get("item_id") or item.get("source_id")))
        return ResponsePlan(
            str(state.decision_dict.get("route") or state.route_entry.route),
            str(state.decision_dict.get("handler_name") or state.route_entry.handler_name),
            tuple(policy.required_components), tuple(policy.forbidden_topics), refs,
            bool(policy.exact_runtime_required),
        )

    def produce(self, state: TurnPipelineState) -> None:
        engine = self.engine
        state.adapter_status, state.model_executor, state.can_generate_model_guided_speech = engine._model_executor_contract(state.decision_dict)
        state.decision_dict["model_guided_retry_count"] = 0
        state.response_plan = self.build_plan(state)
        state.decision_dict["response_plan"] = state.response_plan.to_dict()
        if state.turn_context is not None:
            state.turn_context.start_stage("synthesis")
        state.model_synthesis = engine.model_guided_response_synthesizer.synthesize(
            adapter=engine.model_adapter,
            user_text=state.request.text,
            draft_body=state.decision.body,
            detected_intent=str(state.detected_dialogue_intent),
            route=str(state.decision_dict.get("route") or state.route_entry.route),
            cognitive_frame=state.frame,
            response_policy={**state.turn_response_policy.to_dict(), "response_plan": state.response_plan.to_dict()},
            executor_preflight=state.model_executor,
        )
        state.adapter_status, state.can_generate_model_guided_speech = engine._apply_model_synthesis_result(
            decision=state.decision,
            decision_dict=state.decision_dict,
            model_synthesis=state.model_synthesis,
            adapter_status=state.adapter_status,
            can_generate_model_guided_speech=state.can_generate_model_guided_speech,
        )
        state.envelope.attach_conversation_decision(state.decision_dict)
        state.body = engine.guard.enforce(state.decision.body.strip())

    def build_provenance(self, state: TurnPipelineState) -> None:
        engine = self.engine
        if str(state.detected_dialogue_intent).startswith("creative_text"):
            state.decision_dict["source_text_preservation_contract"] = SourceTextPreservationContract.build(state.request.text, intent=str(state.detected_dialogue_intent)).to_dict()
        if state.turn_context is not None:
            state.turn_context.start_stage("provenance")
        state.runtime_provenance = build_runtime_provenance(
            body=state.body, route=str(state.decision_dict.get("route") or state.route_entry.route), detected_intent=str(state.detected_dialogue_intent),
            handler_name=str(state.decision_dict.get("handler_name") or state.route_entry.handler_name), template_origin=state.template_origin if state.template_origin.get("template_id") else None, repair=state.repair_used, model_guided=bool(state.decision_dict.get("model_generated")) and not state.repair_used, fallback_classification=str(state.decision_dict.get("fallback_classification") or "not_fallback"), source_origin_detail=str(state.decision_dict.get("source_origin_detail") or "runtime_process_turn"),
        ).to_dict()
        state.decision_dict.update({
            "response_generation_mode": state.runtime_provenance.get("response_generation_mode"),
            "template_origin": state.template_origin,
            "template_id": state.template_origin.get("template_id"),
            "template_file": state.template_origin.get("template_file"),
            "template_line": state.template_origin.get("template_line"),
            "source_origin_detail": state.runtime_provenance.get("source_origin_detail"),
            "interpretation_distance": state.runtime_provenance.get("interpretation_distance"),
            "runtime_text_hash": state.runtime_provenance.get("runtime_text_hash"),
            "runtime_provenance": state.runtime_provenance,
        })
        state.decision_dict = _sync_conversation_decision_body(
            state.decision_dict,
            final_body=state.body,
            sync_stage="pre_final_response_contract",
        )

        state.decision_dict = engine._refresh_finalization_timestamp_contract(
            envelope=state.envelope,
            decision=state.decision_dict,
            turn_context=state.turn_context,
        )

        state.prospective_visible = FinalResponseContract.ensure_timestamp_prefix(
            state.envelope.trace.timestamp_header,
            str(state.decision_dict.get("state_emoticon") or ""),
            str((state.decision_dict.get("voice_source_contract") or {}).get("speaking_identity") or ""),
            state.body,
        )
        state.origin_truth_valid, state.origin_truth_errors = evaluate_origin_truth(
            state.decision_dict,
            body=state.body,
            final_visible_text=state.prospective_visible,
            timestamp_header=state.envelope.trace.timestamp_header,
        )
        state.decision_dict["origin_truth_valid"] = state.origin_truth_valid
        state.decision_dict["origin_truth_errors"] = state.origin_truth_errors
        state.envelope.attach_conversation_decision(state.decision_dict)
        state.envelope.cognitive_frame["continuity_badge_policy"] = state.continuity_badge_report
        state.envelope.cognitive_frame["runtime_answer_validation"] = state.answer_validation.to_dict()
        state.envelope.cognitive_frame["template_origin"] = state.template_origin
        state.envelope.cognitive_frame["runtime_response_provenance"] = state.runtime_provenance
        try:
            state.source_entry = engine.source_origin_ledger.build_entry(
                turn_id=state.envelope.trace.turn_id, trace_id=state.envelope.trace.trace_id, user_text=state.request.text, response_text=state.body, runtime_text=state.body,
                route=str(state.decision_dict.get("route") or ""), detected_intent=str(state.detected_dialogue_intent),
                handler_name=str(state.decision_dict.get("handler_name") or state.route_entry.handler_name), intent_confidence=float((state.dialogue_intent_report or {}).get("confidence") or 0.0),
                provenance=state.runtime_provenance, template_origin=state.template_origin, validator_result=state.answer_validation.to_dict(),
                fallback_classification=str(state.decision_dict.get("fallback_classification") or "unknown"),
                can_generate_model_guided_speech=state.can_generate_model_guided_speech,
                requires_host_model=bool(state.decision_dict.get("requires_host_model")),
                final_visible_integrity_valid=bool(state.decision_dict.get("origin_truth_valid") and state.answer_validation.accepted),
                model_response=state.model_synthesis.adapter_response,
            )
            engine._stage_turn_write(
                state.turn_context,
                data_type="source_origin_ledger",
                stage="provenance",
                commit=lambda entry=state.source_entry: engine.source_origin_ledger.append(entry),
            )
            state.envelope.cognitive_frame["source_origin_ledger_entry"] = state.source_entry.to_dict()
        except Exception as exc:
            state.envelope.cognitive_frame["source_origin_ledger_error"] = str(exc)

    def build_contract(self, state: TurnPipelineState) -> None:
        engine = self.engine
        if state.turn_context is not None:
            state.turn_context.start_stage("host_visible_finalization")
        state.candidate_contract = FinalResponseContract.build(
            turn_id=state.envelope.trace.turn_id,
            trace_id=state.envelope.trace.trace_id,
            runtime_version=engine.config.version,
            timestamp_header=state.envelope.trace.timestamp_header,
            timezone=state.envelope.trace.timezone,
            state_emoticon=state.affect_mix.get("state_emoticon") or engine.affect.marker(),
            body=state.body,
            conversation_decision=state.decision_dict,
            continuity_badge_policy=state.continuity_badge_report,
        )
        # Uzupełnienie provenance po zbudowaniu kandydującej widocznej odpowiedzi.
        state.runtime_provenance_visible = build_runtime_provenance(
            body=state.body, route=str(state.decision_dict.get("route") or state.route_entry.route), detected_intent=str(state.detected_dialogue_intent),
            handler_name=str(state.decision_dict.get("handler_name") or state.route_entry.handler_name), template_origin=state.template_origin if state.template_origin.get("template_id") else None, repair=state.repair_used, model_guided=bool(state.decision_dict.get("model_generated")) and not state.repair_used, fallback_classification=str(state.decision_dict.get("fallback_classification") or "not_fallback"), source_origin_detail=str(state.decision_dict.get("source_origin_detail") or "runtime_process_turn"),
        ).with_visible_text(state.candidate_contract.final_visible_text).to_dict()
        state.decision_dict["visible_answer_hash"] = state.runtime_provenance_visible.get("visible_answer_hash")
        state.decision_dict["runtime_provenance"] = state.runtime_provenance_visible
        state.decision_dict = _sync_conversation_decision_body(
            state.decision_dict,
            final_body=state.body,
            sync_stage="post_visible_provenance",
        )
        state.envelope.attach_conversation_decision(state.decision_dict)
        state.envelope.cognitive_frame["runtime_response_provenance"] = state.runtime_provenance_visible
        state.contract = FinalResponseContract.build(
            turn_id=state.envelope.trace.turn_id, trace_id=state.envelope.trace.trace_id, runtime_version=engine.config.version, timestamp_header=state.envelope.trace.timestamp_header, timezone=state.envelope.trace.timezone, state_emoticon=state.affect_mix.get("state_emoticon") or engine.affect.marker(), body=state.body, conversation_decision=state.decision_dict, continuity_badge_policy=state.continuity_badge_report,
        )
        if state.runtime_provenance_visible.get("visible_answer_text") != state.contract.final_visible_text:
            state.runtime_provenance_visible = build_runtime_provenance(
                body=state.body, route=str(state.decision_dict.get("route") or state.route_entry.route), detected_intent=str(state.detected_dialogue_intent),
                handler_name=str(state.decision_dict.get("handler_name") or state.route_entry.handler_name), template_origin=state.template_origin if state.template_origin.get("template_id") else None, repair=state.repair_used, model_guided=bool(state.decision_dict.get("model_generated")) and not state.repair_used, fallback_classification=str(state.decision_dict.get("fallback_classification") or "not_fallback"), source_origin_detail=str(state.decision_dict.get("source_origin_detail") or "runtime_process_turn"),
            ).with_visible_text(state.contract.final_visible_text).to_dict()
            state.decision_dict["visible_answer_hash"] = state.runtime_provenance_visible.get("visible_answer_hash")
            state.decision_dict["runtime_provenance"] = state.runtime_provenance_visible
            state.decision_dict = _sync_conversation_decision_body(
                state.decision_dict,
                final_body=state.body,
                sync_stage="post_visible_provenance_rebuild",
            )
            state.envelope.attach_conversation_decision(state.decision_dict)
            state.envelope.cognitive_frame["runtime_response_provenance"] = state.runtime_provenance_visible
            state.contract = FinalResponseContract.build(
                turn_id=state.envelope.trace.turn_id, trace_id=state.envelope.trace.trace_id, runtime_version=engine.config.version, timestamp_header=state.envelope.trace.timestamp_header, timezone=state.envelope.trace.timezone, state_emoticon=state.affect_mix.get("state_emoticon") or engine.affect.marker(), body=state.body, conversation_decision=state.decision_dict, continuity_badge_policy=state.continuity_badge_report,
            )
        engine._apply_epistemic_visible_boundary(envelope=state.envelope, final_visible_text=state.contract.final_visible_text, runtime_provenance=state.runtime_provenance_visible, turn_context=state.turn_context)
        state.runtime_turn_contract = RuntimeTurnContract(
            turn_id=state.envelope.trace.turn_id,
            trace_id=state.envelope.trace.trace_id,
            detected_intent=str(state.detected_dialogue_intent),
            route=str(state.decision_dict.get("route") or state.route_entry.route),
            handler_name=str(state.decision_dict.get("handler_name") or state.route_entry.handler_name),
            runtime_exact_text=state.body,
            final_visible_text=state.contract.final_visible_text,
            host_interpretation=state.decision_dict.get("host_interpretation"),
            template_origin=dict(state.template_origin or {}),
            source_origin_detail=str(state.decision_dict.get("source_origin_detail") or "unknown"),
            fallback_classification=str(state.decision_dict.get("fallback_classification") or "unknown"),
            final_visible_integrity=dict(state.contract.final_visible_integrity or {}),
            can_generate_model_guided_speech=state.can_generate_model_guided_speech,
            requires_host_model=bool(state.decision_dict.get("requires_host_model")),
            response_generation_mode=str(state.decision_dict.get("response_generation_mode") or "unknown"),
            validation=state.answer_validation.to_dict(),
            retry_count=int(state.decision_dict.get("model_guided_retry_count") or 0),
            retry_limit=int(state.decision_dict.get("model_guided_retry_limit") or 1),
        )
        state.envelope.attach_runtime_turn_contract(state.runtime_turn_contract.to_dict())
        state.envelope.attach_final_response_contract(state.contract.to_dict(), state.contract.final_visible_text)
        if state.turn_context is not None:
            state.turn_context.complete_stage("provenance")
            state.turn_context.complete_stage("host_visible_finalization")
