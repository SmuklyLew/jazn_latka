from __future__ import annotations

from typing import Any

from latka_jazn.core.route_handler_base import RouteHandlerResult
from latka_jazn.version import generation_mode, schema_version


class ExternalToolAssistanceHandler:
    name = "ExternalToolAssistanceHandler"
    route = "external_tool_assistance"
    handled_intents = ("external_tool_assistance_request",)

    def handle(self, text: str, context: dict[str, Any] | None = None) -> RouteHandlerResult:
        ctx = context or {}
        report_value = ctx.get("dialogue_intent_report")
        report: dict[str, Any] = report_value if isinstance(report_value, dict) else {}
        tool_context_value = report.get("external_tool_context")
        tool_context: dict[str, Any] = tool_context_value if isinstance(tool_context_value, dict) else {}
        tools = [str(item) for item in tool_context.get("requested_tools", [])]
        body = (
            "Zewnętrzne narzędzie jest kontekstem wykonawczym, nie nowym autorem odpowiedzi. "
            f"Żądane narzędzia: {', '.join(tools) or 'nieustalone'}. "
            "Warstwa hosta powinna wykonać właściwy connector i zachować główną intencję oraz kontrakt głosu runtime."
        )
        return RouteHandlerResult(
            self.name,
            self.route,
            body,
            intent=str(ctx.get("intent") or "external_tool_assistance_request"),
            data={
                "external_tool_context": tool_context,
                "status": "requires_host_connector_execution",
                "external_tools_do_not_transfer_voice": True,
            },
            required_components=list(ctx.get("required_components") or []),
            satisfied_components=["tool_context", "primary_intent_preservation", "voice_continuity", "truth_boundary"],
            confidence=0.90,
            generation_mode=generation_mode("external_tool_assistance"),
            source_origin_detail=schema_version("external_tool_assistance_handler"),
            truth_boundary="Runtime opisuje potrzebę connectora; nie twierdzi, że lokalnie wykonał zewnętrzne narzędzie.",
        )
