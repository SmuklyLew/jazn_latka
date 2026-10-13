from __future__ import annotations

"""Isolated MCP 2026-07-28 conformance fixture using Jaźń's real SDK gateway.

Never import this from production runtime, the plugin package, or normal
`run.py mcp-http`. The synthetic test:// resources and test_* tools only
exist in this separately launched, loopback-bound test process. No MEMORY,
daemon or Ollama is connected. Real Jaźń tool contracts are tested separately.
"""

import argparse
import base64
import json
import secrets
from io import BytesIO
from pathlib import Path
import wave
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import RequestStateSecurity
from mcp.types import (
    CreateMessageRequest, CreateMessageRequestParams, CreateMessageResult,
    ElicitRequest, ElicitRequestFormParams, ElicitResult, InputRequest,
    InputRequiredResult, ListRootsRequest, ListRootsResult,
    SamplingMessage, TextContent, MISSING_REQUIRED_CLIENT_CAPABILITY,
)
from mcp.shared.exceptions import MCPError
from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult

from latka_jazn.mcp.http_gateway import build_public_mcp_gateway

# Valid 1x1 PNG, non-sensitive conformance fixture bytes.
_TEST_IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg=="
)


def _audio_base64() -> str:
    output = BytesIO()
    with wave.open(output, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(1)
        sound.setframerate(8000)
        sound.writeframes(b"\x80" * 8)
    return base64.b64encode(output.getvalue()).decode("ascii")


def _result(*content: dict[str, Any]) -> CallToolResult:
    return CallToolResult.model_validate({"content": list(content), "isError": False})


class _NoPrivateRuntime:
    def call_tool(
        self, name: str, arguments: dict[str, Any],
        *, meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Non-sensitive synthetic status: NO daemon, memory, or user session.
        # This allows protocol resource-read/caching checks to exercise
        # Jaźń's real gateway serializer without claiming runtime readiness.
        if name == "jazn_status":
            return {
                "content": [{"type": "text", "text": "Conformance fixture only; Jaźń is not running."}],
                "structuredContent": {
                    "gateway_ok": True, "daemon_reachable": False,
                    "capability_matrix": {
                        "conversation_ready": False,
                        "ordinary_dialogue_allowed": False,
                        "components": {
                            "persistent_memory": {"status": "unavailable", "available": False},
                            "recall": {"status": "unavailable", "available": False},
                        },
                    },
                },
                "isError": False,
            }
        # Conformance must never execute Jaźń, modify MEMORY or start a turn.
        raise RuntimeError("conformance_fixture_has_no_private_runtime")


def register_fixture(mcp: MCPServer) -> None:
    """Test-only capabilities expected by the upstream reference scenarios."""

    @mcp.tool(name="test_simple_text", description="Tests simple text content response")
    def simple_text() -> CallToolResult:
        return _result({"type": "text", "text": "This is a simple text response for testing."})

    @mcp.tool(name="test_image_content", description="Tests image content response")
    def image_content() -> CallToolResult:
        return _result({"type": "image", "data": _TEST_IMAGE, "mimeType": "image/png"})

    @mcp.tool(name="test_audio_content", description="Tests audio content response")
    def audio_content() -> CallToolResult:
        return _result({"type": "audio", "data": _audio_base64(), "mimeType": "audio/wav"})

    @mcp.tool(name="test_embedded_resource", description="Tests embedded resource content response")
    def embedded_resource() -> CallToolResult:
        return _result({
            "type": "resource",
            "resource": {"uri": "test://embedded-resource", "mimeType": "text/plain",
                         "text": "This is an embedded resource content."},
        })

    @mcp.tool(name="test_multiple_content_types", description="Tests multiple content types")
    def mixed_content() -> CallToolResult:
        return _result(
            {"type": "text", "text": "Multiple content types test:"},
            {"type": "image", "data": _TEST_IMAGE, "mimeType": "image/png"},
            {"type": "resource", "resource": {
                "uri": "test://mixed-content-resource", "mimeType": "application/json",
                "text": '{"test":"data","value":123}',
            }},
        )

    @mcp.tool(name="test_error_handling", description="Tests error response handling")
    def tool_error() -> str:
        raise ValueError("This tool intentionally returns an error for testing")

    @mcp.tool(name="test_tool_with_progress", description="Tests progress notifications")
    async def with_progress(ctx: Context) -> str:
        for value in (0, 50, 100):
            await ctx.report_progress(value, 100, f"Completed step {value} of 100")
        return "Completed progress test"

    @mcp.tool(name="test_tool_with_logging", description="Tests tool logging notifications")
    async def with_logging(ctx: Context) -> str:
        await ctx.info("Tool execution started")
        await ctx.info("Tool processing data")
        await ctx.info("Tool execution completed")
        return "Tool with logging executed successfully"


    # MCP 2026-07-28: required multi-round-trip input requests are
    # exercised here, using the same SDK's actual stateless request context.
    def ask_name(label: str = "What is your name?") -> ElicitRequest:
        return ElicitRequest(params=ElicitRequestFormParams(
            message=label,
            requested_schema={"type": "object", "properties": {
                "name": {"type": "string"}}, "required": ["name"]},
        ))

    def sample_text(label: str) -> CreateMessageRequest:
        return CreateMessageRequest(params=CreateMessageRequestParams(
            messages=[SamplingMessage(
                role="user", content=TextContent(type="text", text=label))],
            max_tokens=50,
        ))

    @mcp.tool(name="test_input_required_result_elicitation", description="Request one form elicitation and resume with the response")
    async def mrtr_elicitation(ctx: Context) -> str | InputRequiredResult:
        responses = ctx.input_responses or {}
        if "user_name" in responses:
            ans = responses["user_name"]
            value = ans.content.get("name", "stranger") if isinstance(ans, ElicitResult) and ans.content else "?"
            return f"Hello, {value}!"
        return InputRequiredResult(input_requests={"user_name": ask_name()})

    @mcp.tool(name="test_input_required_result_sampling", description="Request one client sampling response")
    async def mrtr_sampling(ctx: Context) -> str | InputRequiredResult:
        responses = ctx.input_responses or {}
        if "capital_question" in responses:
            ans = responses["capital_question"]
            value = ans.content.text if isinstance(ans, CreateMessageResult) and ans.content.type == "text" else "?"
            return f"Model said: {value}"
        return InputRequiredResult(input_requests={
            "capital_question": sample_text("What is the capital of France?"),
        })

    @mcp.tool(name="test_input_required_result_list_roots", description="Request client roots from the client")
    async def mrtr_roots(ctx: Context) -> str | InputRequiredResult:
        responses = ctx.input_responses or {}
        if "client_roots" in responses:
            ans = responses["client_roots"]
            total = len(ans.roots) if isinstance(ans, ListRootsResult) else 0
            return f"Client exposed {total} root(s)."
        return InputRequiredResult(input_requests={"client_roots": ListRootsRequest()})

    @mcp.tool(name="test_input_required_result_request_state", description="Exercise secure request-state round-trip")
    async def mrtr_state(ctx: Context) -> str | InputRequiredResult:
        responses = ctx.input_responses or {}
        if "confirm" in responses and ctx.request_state == "request-state-nonce":
            return "state-ok: confirmation received"
        req = ElicitRequest(params=ElicitRequestFormParams(
            message="Please confirm",
            requested_schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                              "required": ["ok"]},
        ))
        return InputRequiredResult(input_requests={"confirm": req}, request_state="request-state-nonce")

    @mcp.tool(name="test_input_required_result_multiple_inputs", description="Request multiple client inputs together")
    async def mrtr_multiple(ctx: Context) -> str | InputRequiredResult:
        responses = ctx.input_responses or {}
        if {"user_name", "greeting", "client_roots"} <= responses.keys():
            return "All inputs received."
        return InputRequiredResult(input_requests={
            "user_name": ask_name(),
            "greeting": sample_text("Generate a greeting"),
            "client_roots": ListRootsRequest(),
        }, request_state="multiple-inputs")

    @mcp.tool(name="test_input_required_result_multi_round", description="Exercise multiple rounds of client input")
    async def mrtr_multiround(ctx: Context) -> str | InputRequiredResult:
        try:
            state = json.loads(ctx.request_state) if ctx.request_state else {"round": 0}
        except (TypeError, ValueError):
            state = {"round": 0}
        responses = ctx.input_responses or {}
        if state.get("round") == 1 and "step1" in responses:
            answer = responses["step1"]
            name = answer.content.get("name", "") if isinstance(answer, ElicitResult) and answer.content else ""
            req = ElicitRequest(params=ElicitRequestFormParams(
                message="Step 2: What is your favorite color?",
                requested_schema={"type": "object", "properties": {"color": {"type": "string"}},
                                  "required": ["color"]},
            ))
            return InputRequiredResult(input_requests={"step2": req},
                                       request_state=json.dumps({"round": 2, "name": name}))
        if state.get("round") == 2 and "step2" in responses:
            answer = responses["step2"]
            color = answer.content.get("color", "") if isinstance(answer, ElicitResult) and answer.content else ""
            return f"{state.get('name')} likes {color}."
        return InputRequiredResult(input_requests={
            "step1": ask_name("Step 1: What is your name?")},
            request_state=json.dumps({"round": 1}))

    @mcp.tool(name="test_input_required_result_tampered_state", description="Reject tampered sealed request state")
    async def mrtr_tamper(ctx: Context) -> str | InputRequiredResult:
        if ctx.request_state is not None:
            return f"state-ok: {ctx.request_state}"
        return InputRequiredResult(input_requests={"confirm": ask_name()},
                                   request_state="round-1")

    @mcp.tool(name="test_input_required_result_capabilities", description="Limit input requests by client capabilities")
    async def mrtr_capabilities(ctx: Context) -> InputRequiredResult:
        caps = ctx.client_capabilities
        requests: dict[str, InputRequest] = {}
        if caps is None or caps.sampling is not None:
            requests["sample"] = sample_text("Say hello")
        if caps is None or caps.elicitation is not None:
            requests["ask"] = ask_name()
        return InputRequiredResult(input_requests=requests, request_state="capability-gated")

    @mcp.tool(name="test_missing_capability", description="Reject a call without required sampling capability")
    async def missing_capability(ctx: Context) -> str:
        caps = ctx.client_capabilities
        if caps is None or caps.sampling is None:
            raise MCPError(
                code=MISSING_REQUIRED_CLIENT_CAPABILITY,
                message="Client sampling capability required",
                data={"requiredCapabilities": {"sampling": {}}},
            )
        return "Sampling was declared"

    @mcp.resource(
        "test://static-text", name="Static Text Resource", mime_type="text/plain",
        description="Static text for the conformance suite",
    )
    def static_text() -> str:
        return "This is the content of the static text resource."

    @mcp.resource(
        "test://static-binary", name="Static Binary Resource", mime_type="image/png",
        description="Static binary fixture for the conformance suite",
    )
    def static_binary() -> bytes:
        return base64.b64decode(_TEST_IMAGE)

    @mcp.resource(
        "test://template/{id}/data", name="Resource Template",
        mime_type="application/json", description="Parameter substitution fixture",
    )
    def template_data(id: str) -> dict[str, str]:
        return {"id": id, "data": f"Template content for ID {id}"}

    @mcp.prompt(name="test_simple_prompt", description="A simple prompt without arguments")
    def simple_prompt() -> str:
        return "This is a simple prompt for testing."

    @mcp.prompt(name="test_prompt_with_arguments", description="A prompt with required arguments")
    def prompt_args(arg1: str, arg2: str) -> str:
        return f"Prompt with arguments: arg1='{arg1}', arg2='{arg2}'"

    @mcp.prompt(name="test_prompt_with_embedded_resource", description="Embedded resource prompt")
    def prompt_resource(resourceUri: str) -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": {
                "type": "resource", "resource": {
                    "uri": resourceUri, "mimeType": "text/plain",
                    "text": "Embedded resource content for testing.",
                }}},
            {"role": "user", "content": {
                "type": "text", "text": "Please process the embedded resource above.",
            }},
        ]

    @mcp.prompt(name="test_input_required_result_prompt", description="Request user context from the client")
    async def input_required_prompt(ctx: Context) -> list[dict[str, Any]] | InputRequiredResult:
        responses = ctx.input_responses or {}
        if "user_context" in responses:
            ans = responses["user_context"]
            value = ans.content.get("context", "?") if isinstance(ans, ElicitResult) and ans.content else "?"
            return [{"role": "user", "content": {"type": "text",
                     "text": f"Use the following context: {value}"}}]
        req = ElicitRequest(params=ElicitRequestFormParams(
            message="What context should the prompt use?",
            requested_schema={"type": "object", "properties": {"context": {"type": "string"}},
                              "required": ["context"]},
        ))
        return InputRequiredResult(input_requests={"user_context": req})

    @mcp.prompt(name="test_prompt_with_image", description="Image fixture prompt")
    def prompt_image() -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": {
                "type": "image", "data": _TEST_IMAGE, "mimeType": "image/png",
            }},
            {"role": "user", "content": {
                "type": "text", "text": "Please analyze the image above.",
            }},
        ]


def make_fixture(*, root: Path, port: int):
    """Build Jaźń's actual public SDK transport with synthetic test handlers."""
    if port < 1024 or port > 65535:
        raise ValueError("conformance_fixture_port_invalid")
    gateway = build_public_mcp_gateway(
        root=root, host="127.0.0.1", port=port,
        backend=_NoPrivateRuntime(),
        allow_unauthenticated_loopback_dev=True,
        json_response=False,  # Required to transmit progress via SSE.
        request_state_security=RequestStateSecurity(keys=[secrets.token_bytes(32)]),
    )
    register_fixture(gateway.mcp)
    return gateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated loopback-only MCP test fixture")
    parser.add_argument("--port", type=int, required=True)
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    make_fixture(root=root, port=options.port).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
