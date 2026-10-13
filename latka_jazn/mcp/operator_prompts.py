from __future__ import annotations

"""Read-only MCP operator prompts; never an activation or memory source."""

from typing import Any, Mapping

PROMPT_NAME = "jazn_runtime_review"
FOCUS_VALUES = ("readiness", "finalization", "memory")
PROMPT_DESCRIPTION = "Review verified Jaźń runtime evidence without impersonating an active runtime."
_GUIDANCE = {
    "readiness": "Inspect a fresh jazn_status result: exact runtime instance, heartbeat, conversation_ready, package and provenance. Installed plugins alone do not prove readiness.",
    "finalization": "Check request_id, turn_id, trace_id, final text SHA-256 and a genuinely accepted display_exact MessageEnvelope. Do not replay the original user message.",
    "memory": "Assess redacted persistent-memory readiness and source provenance. Never infer access to private memory or reveal content. MEMORY is not SYSTEM active_root.",
}


def runtime_review_text(focus: str = "readiness") -> str:
    if focus not in _GUIDANCE:
        raise ValueError("mcp_prompt_focus_invalid")
    return "Technical review only; this prompt does not activate Jaźń. " + _GUIDANCE[focus]


def list_runtime_prompts() -> dict[str, Any]:
    return {"prompts": [{
        "name": PROMPT_NAME,
        "description": PROMPT_DESCRIPTION,
        "arguments": [{"name": "focus", "description": "readiness, finalization or memory", "required": False}],
    }]}


def get_runtime_prompt(params: Mapping[str, Any]) -> dict[str, Any]:
    if params.get("name") != PROMPT_NAME:
        raise ValueError("mcp_prompt_unknown")
    args = params.get("arguments") or {}
    if not isinstance(args, Mapping) or any(key != "focus" for key in args):
        raise ValueError("mcp_prompt_arguments_invalid")
    focus = args.get("focus", "readiness")
    if not isinstance(focus, str):
        raise ValueError("mcp_prompt_focus_invalid")
    return {
        "description": PROMPT_DESCRIPTION,
        "messages": [{"role": "user", "content": {"type": "text", "text": runtime_review_text(focus)}}],
    }


def complete_runtime_prompt(ref: Mapping[str, Any], argument: Mapping[str, Any]) -> dict[str, Any]:
    if ref.get("type") != "ref/prompt" or ref.get("name") != PROMPT_NAME:
        raise ValueError("mcp_completion_reference_unknown")
    if argument.get("name") != "focus":
        raise ValueError("mcp_completion_argument_unknown")
    prefix = argument.get("value")
    if not isinstance(prefix, str) or len(prefix) > 128:
        raise ValueError("mcp_completion_prefix_invalid")
    values = [focus for focus in FOCUS_VALUES if focus.startswith(prefix)]
    return {"completion": {"values": values, "total": len(values), "hasMore": False}}


__all__ = ["PROMPT_NAME", "PROMPT_DESCRIPTION", "FOCUS_VALUES", "runtime_review_text",
           "list_runtime_prompts", "get_runtime_prompt", "complete_runtime_prompt"]
