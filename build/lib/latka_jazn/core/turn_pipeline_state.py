from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.cognitive_turn_envelope import CognitiveTurnEnvelope


@dataclass(frozen=True)
class TurnRequest:
    text: str
    client_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnResult:
    envelope: CognitiveTurnEnvelope


@dataclass(frozen=True)
class CognitiveFrame:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.payload


@dataclass
class TurnPipelineState:
    request: TurnRequest
    response_plan: Any = None
    speech_adapter: Any = None
    adapter_status: Any = None
    affect_mix: Any = None
    answer_validation: Any = None
    body: Any = None
    can_generate_model_guided_speech: Any = None
    candidate_contract: Any = None
    candidate_valid: Any = None
    carryover_allowed: Any = None
    checkpoint: Any = None
    continuity_badge_report: Any = None
    contract: Any = None
    ctx: Any = None
    current_dialogue_task_state: Any = None
    decision: Any = None
    decision_dict: Any = None
    detected_dialogue_intent: Any = None
    dialogue_intent_report: Any = None
    dialogue_intent_result: Any = None
    dialogue_state: Any = None
    dispatch_report: Any = None
    emotional_profile: Any = None
    envelope: Any = None
    envelope_dict: Any = None
    first_validation: Any = None
    frame: Any = None
    granular: Any = None
    handler_context: Any = None
    handler_fallback_payload: Any = None
    handler_missing: Any = None
    handler_required: Any = None
    handler_result: Any = None
    handler_satisfied: Any = None
    health_check_fast_path: Any = None
    host_bridge_accepts_handler: Any = None
    initial_task_state: Any = None
    logic_audit: Any = None
    model_executor: Any = None
    model_replied: Any = None
    model_synthesis: Any = None
    no_carryover: Any = None
    now_for_context: Any = None
    origin_truth_errors: Any = None
    origin_truth_valid: Any = None
    preserve_handler_body: Any = None
    previous_task_state: Any = None
    prior_context_age_seconds: Any = None
    prior_detected_intent: Any = None
    prior_runtime_route: Any = None
    prior_turn_at: Any = None
    prior_user_text: Any = None
    prior_visible_text: Any = None
    prospective_visible: Any = None
    read_only_preview: Any = None
    reasoning_decision: Any = None
    repair_used: Any = None
    retry_body: Any = None
    retry_synthesis: Any = None
    retry_template: Any = None
    retry_validation: Any = None
    route_entry: Any = None
    runtime_answer_quality: Any = None
    runtime_provenance: Any = None
    runtime_provenance_visible: Any = None
    runtime_turn_contract: Any = None
    source_entry: Any = None
    source_origin_detail: Any = None
    speech_truth_gate_required: Any = None
    synthesis: Any = None
    template_origin: Any = None
    turn_context: Any = None
    turn_context_resolution: Any = None
    turn_response_policy: Any = None
    turn_route_trace: Any = None


@dataclass
class FrameBuildState:
    request: TurnRequest
    intent_report: Any = None
    turn_context: TurnExecutionContext | None = None
    accepted: Any = None
    adapter_status: Any = None
    awareness_report: Any = None
    candidate_fingerprint: Any = None
    cognitive_integration: Any = None
    cognitive_packets: Any = None
    cognitive_runtime_plan: Any = None
    cognitive_topics: Any = None
    consolidation_plan: Any = None
    declared_tools: Any = None
    dialogue_context: Any = None
    emotional_profile: Any = None
    fallback_diagnostics: Any = None
    gap: Any = None
    granular_affect: Any = None
    identity_vector: Any = None
    importance: Any = None
    intent_tags: Any = None
    lexical_report: Any = None
    logical_report: Any = None
    memory_context: Any = None
    memory_gate_intent_report: Any = None
    memory_recall_contract: Any = None
    memory_recall_observability: Any = None
    neuro_cycle: Any = None
    neurological_signal_route: Any = None
    nlp_report: Any = None
    now: Any = None
    operational_work_plan: Any = None
    packet: Any = None
    persistence: Any = None
    persistence_reason: Any = None
    polish_reasoning_frame: Any = None
    polish_report: Any = None
    quiet_context: Any = None
    raw_chat_status: Any = None
    read_only_preview: Any = None
    runtime_candidate: Any = None
    runtime_operating_context: Any = None
    runtime_rendering_mode: Any = None
    sample: Any = None
    self_knowledge_summary: Any = None
    self_state_packet: Any = None
    session_continuity: Any = None
    source_origin: Any = None
    startup_summary: Any = None
    temporal_state: Any = None
    tool_execution_plan: Any = None
    tool_use_decision: Any = None
    topic_guard_report: Any = None
    trace_id: Any = None
    truth_boundary_check: Any = None
    truth_risk: Any = None
    turn_id: Any = None
    untrusted_source_assessment: Any = None
    user_truth_audit: Any = None
    voice_source_contract: Any = None
    write_id: Any = None


