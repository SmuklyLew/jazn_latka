from __future__ import annotations

"""MCP binding for the typed Jaźń conversation-turn runtime."""

import hashlib
from typing import Any, Mapping

from latka_jazn.runtime.turn_runtime import (
    ProfessionalTurnRuntime,
    TurnIdentity,
    TurnProtocolViolation,
)


_TURN_TOOLS = frozenset(
    {
        "jazn_generate_visible_reply",
        "jazn_resume_visible_reply",
        "jazn_finalize_reply",
    }
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _identity_request_id(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    metadata: Mapping[str, Any],
    result: Mapping[str, Any],
    jsonrpc_request_id: Any,
) -> str:
    structured = _mapping(result.get("structuredContent"))
    explicit = str(
        structured.get("daemon_request_id")
        or structured.get("request_id")
        or arguments.get("request_id")
        or metadata.get("request_id")
        or ""
    ).strip()
    if explicit:
        return explicit
    if tool_name == "jazn_finalize_reply":
        token = str(arguments.get("continuation_token") or "")
        if token:
            return "finalize-" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:48]
    transport = str(jsonrpc_request_id if jsonrpc_request_id is not None else "").strip()
    if transport:
        return "mcp-transport-" + hashlib.sha256(transport.encode("utf-8")).hexdigest()[:40]
    raise TurnProtocolViolation("request_identity_unavailable")


class McpTurnRuntimeAdapter:
    def __init__(self, runtime: ProfessionalTurnRuntime | None = None) -> None:
        self.runtime = runtime or ProfessionalTurnRuntime()

    def capability_descriptor(self) -> dict[str, Any]:
        return self.runtime.capability_descriptor()

    def decorate_call_response(
        self,
        request_value: Mapping[str, Any],
        response: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if response is None:
            return None
        if request_value.get("method") != "tools/call":
            return response

        params = _mapping(request_value.get("params"))
        tool_name = str(params.get("name") or "").strip()
        if tool_name not in _TURN_TOOLS:
            return response
        result = response.get("result")
        if not isinstance(result, Mapping):
            return response

        arguments = _mapping(params.get("arguments"))
        metadata = _mapping(params.get("_meta"))
        message = str(
            arguments.get("message")
            or arguments.get("final_text")
            or ""
        )
        session_id = str(arguments.get("session_id") or "").strip() or None
        identity: TurnIdentity | None = None
        try:
            request_id = _identity_request_id(
                tool_name=tool_name,
                arguments=arguments,
                metadata=metadata,
                result=result,
                jsonrpc_request_id=request_value.get("id"),
            )
            identity = TurnIdentity.build(
                request_id=request_id,
                message=message,
                session_id=session_id,
            )
            decorated = self.runtime.decorate_tool_result(
                tool_name=tool_name,
                result=result,
                identity=identity,
            )
        except TurnProtocolViolation as exc:
            decorated = self.runtime.fail_closed_tool_result(str(exc), identity=identity)

        value = dict(response)
        value["result"] = decorated
        return value


__all__ = ["McpTurnRuntimeAdapter"]
