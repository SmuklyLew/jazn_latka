from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from latka_jazn.core.memory_intent_contract import (
    MEMORY_CONTENT_INTENTS,
    analyze_memory_intent,
)
from latka_jazn.core.self_question_memory_gate import SelfQuestionMemoryGate
from latka_jazn.nlp.utterance_components import analyse_utterance

SCHEMA_VERSION = "memory_use_gate/v2"

NON_MEMORY_INTENTS = {
    "runtime_health_check",
    "runtime_health_check_after_update",
    "runtime_activation_status_question",
    "presence_check",
    "identity_presence_check",
    "identity_continuity_check",
    "capability_status_question",
    "internet_access_question",
}

MEMORY_REQUIRED_INTENTS = MEMORY_CONTENT_INTENTS | {
    "self_memory_recall_request",
    "identity_memory_question",
    "continuity_question",
    "self_architecture_audit_request",
    "jazn_development_plan_request",
}

@dataclass(slots=True)
class MemoryUseDecision:
    allow_memory_content: bool
    reason: str
    memory_role: str
    stale_route_risk: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = SCHEMA_VERSION
        return data

class MemoryUseGate:
    """Decyduje, czy wolno wprowadzić treści pamięci do widocznej odpowiedzi.

    Sama obecność słowa „ostatnio” nie wystarcza. W pytaniu „na co miałaś
    ostatnio ochotę?” pamięć mogłaby przypadkowo wstrzyknąć dawny fragment
    obcego tematu. Dlatego poprzednia linia runtime rozdziela pytanie o własny stan Łatki od
    prawdziwej prośby o wspomnienie albo poprzedni wątek.
    """

    def decide(self, user_text: str, *, detected_intent: str | None = None) -> MemoryUseDecision:
        intent = detected_intent or "unknown"
        semantics = analyze_memory_intent(user_text)
        component_report = analyse_utterance(user_text)
        self_gate = SelfQuestionMemoryGate().decide(user_text, detected_intent=intent)
        if intent == "compound_dialogue_question":
            memory_components = [
                component
                for component in component_report.question_components
                if component.memory_required
            ]
            if memory_components:
                return MemoryUseDecision(
                    True,
                    "compound_component_requires_memory:"
                    + ",".join(component.component_id for component in memory_components),
                    "per_component_content_source",
                    "low_after_component_gate",
                )
            return MemoryUseDecision(
                False,
                "compound_components_do_not_require_memory",
                "disabled_for_turn",
                "low_after_component_gate",
            )
        if self_gate.force_memory_content:
            return MemoryUseDecision(True, "self_question_memory_gate:" + self_gate.reason, "self_architecture_or_self_memory_content", "low")
        if intent in NON_MEMORY_INTENTS:
            return MemoryUseDecision(False, "non_memory_specialized_intent_blocks_retrieval", "disabled_for_turn", "low_after_gate")
        if semantics.capability_only:
            return MemoryUseDecision(False, "canonical_memory_contract:capability_only", "disabled_for_turn", "low_after_gate")
        if semantics.operation in {"store_directive", "forget_directive"} or semantics.negated_recall:
            return MemoryUseDecision(False, "canonical_memory_contract:non_retrieval_operation", "disabled_for_turn", "low_after_gate")
        if intent == "self_preference_question" and "self_preference" in component_report.semantic_intents:
            return MemoryUseDecision(
                True,
                "preference_question_uses_evidence_aware_memory_and_canon_sources",
                "preference_provenance_source",
                "low_after_typed_source_gate",
            )
        if intent in {"self_state_question", "reciprocal_self_state_question", "self_plan_question", "sleep_closure_statement"}:
            return MemoryUseDecision(False, "self_state_or_closure_uses_current_turn_not_memory_excerpt", "affective_context_only", "high_if_memory_excerpt_injected")
        if intent in MEMORY_REQUIRED_INTENTS:
            return MemoryUseDecision(True, "memory_required_intent", "content_source", "low")
        if semantics.content_requested:
            return MemoryUseDecision(True, "canonical_memory_contract:content_requested", "content_source", "low")
        return MemoryUseDecision(False, "no_explicit_memory_request", "continuity_guard_only", "medium")
