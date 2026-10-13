from __future__ import annotations

"""Isolated MCP 2026-07-28 conformance fixture using Jaźń's real SDK gateway.

Never import this from production runtime, the plugin package, or normal
`run.py mcp-http`. The synthetic test:// resources and test_* tools only
exist in this separately launched, loopback-bound test process. No MEMORY,
daemon or Ollama is connected. Real Jaźń tool contracts are tested separately.
"""

import argparse
import base64
from io import BytesIO
from pathlib import Path
import wave
from typing import Any

from mcp.server import MCPServer
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
        # Conformance must never depend on a private runtime or execute Jaźń.
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
