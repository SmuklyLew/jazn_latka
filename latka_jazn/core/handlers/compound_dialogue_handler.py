from __future__ import annotations

from typing import Any

from latka_jazn.core.route_handler_base import RouteHandlerResult
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("compound_dialogue_handler")


class CompoundDialogueHandler:
    """Preserve a multi-intent plan for the normal synthesis/finalization path.

    The handler deliberately does not invent a body.  Each component keeps its
    own object, source requirements and memory decision in the classifier
    report; the response synthesizer receives that sealed plan in the cognitive
    frame and must cover all requested components under the turn truth policy.
    """

    name = "CompoundDialogueHandler"
    route = "compound_dialogue"
    handled_intents = ("compound_dialogue_question",)

    def handle(self, text: str, context: dict[str, Any] | None = None) -> RouteHandlerResult:
        ctx = dict(context or {})
        report_value = ctx.get("dialogue_intent_report")
        report = dict(report_value) if isinstance(report_value, dict) else {}
        components = [
            dict(item) for item in report.get("component_analysis") or [] if isinstance(item, dict)
        ]
        response_plan_value = report.get("response_plan")
        response_plan = dict(response_plan_value) if isinstance(response_plan_value, dict) else {}
        memory_value = ctx.get("memory_context")
        memory_context = dict(memory_value) if isinstance(memory_value, dict) else {}
        gate_value = memory_context.get("memory_gate")
        memory_gate = dict(gate_value) if isinstance(gate_value, dict) else {}
        required = list(ctx.get("required_components") or [])
        satisfied = [
            "question_components",
            "component_intents",
            "component_source_plan",
            "memory_gate",
            "truth_boundary",
        ]
        missing: list[str] = []
        if not components:
            missing.append("question_components")
        if not response_plan.get("semantic_intents"):
            missing.append("component_intents")
        if not response_plan.get("required_source_types"):
            # Source-less components are allowed only when no component asks for
            # provenance/memory.  Otherwise fail closed and expose the gap.
            if response_plan.get("memory_required"):
                missing.append("component_source_plan")
        return RouteHandlerResult(
            handler_name=self.name,
            route=self.route,
            body="",
            intent=str(ctx.get("intent") or "compound_dialogue_question"),
            data={
                "component_analysis": components,
                "response_plan": response_plan,
                "memory_gate": memory_gate,
                "coverage_required": [str(item.get("component_id") or "") for item in components],
                "status": "compound_plan_ready" if not missing else "compound_plan_incomplete",
            },
            generation_mode="pass_through_empty",
            response_generation_mode_hint="runtime_dynamic",
            required_components=required,
            satisfied_components=[item for item in satisfied if item not in missing],
            missing_components=missing,
            confidence=0.9 if not missing else 0.55,
            source_origin_detail=SCHEMA_VERSION,
            truth_boundary=(
                "Komponenty złożonej tury zachowują osobne intencje i typy źródeł. "
                "Brak dowodu dla jednego komponentu nie może zostać wypełniony treścią z innego typu źródła."
            ),
        )


__all__ = ["SCHEMA_VERSION", "CompoundDialogueHandler"]
