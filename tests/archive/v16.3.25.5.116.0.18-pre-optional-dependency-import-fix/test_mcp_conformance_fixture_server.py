from __future__ import annotations

from pathlib import Path
from mcp.types import CallToolResult

import pytest

pytest.importorskip("mcp")

from latka_jazn.mcp.http_gateway import build_public_mcp_gateway
from tools.mcp_conformance_fixture_server import make_fixture, _NoPrivateRuntime


@pytest.mark.anyio
async def test_fixture_has_synthetic_protocol_tools_but_production_has_none(tmp_path: Path) -> None:
    fixture = make_fixture(root=tmp_path, port=18796)
    tools = {t.name for t in await fixture.mcp.list_tools()}
    assert {"test_simple_text", "test_image_content", "test_audio_content",
            "test_embedded_resource", "test_multiple_content_types",
            "test_tool_with_progress", "test_error_handling"} <= tools
    assert {"jazn_status", "jazn_generate_visible_reply",
            "jazn_resume_visible_reply", "jazn_finalize_reply"} <= tools
    prod = build_public_mcp_gateway(
        root=tmp_path, backend=_NoPrivateRuntime(),
        allow_unauthenticated_loopback_dev=True,
    )
    prod_tools = {t.name for t in await prod.mcp.list_tools()}
    assert not any(x.startswith("test_") for x in prod_tools)
    assert "jazn_status" in prod_tools
    assert prod.config.json_response is True
    assert fixture.config.json_response is False


@pytest.mark.anyio
async def test_fixture_registers_resources_and_prompts(tmp_path: Path) -> None:
    gateway = make_fixture(root=tmp_path, port=18797)
    resources = {str(r.uri) for r in await gateway.mcp.list_resources()}
    assert "test://static-text" in resources
    assert "test://static-binary" in resources
    prompts = {p.name for p in await gateway.mcp.list_prompts()}
    assert {"test_simple_prompt", "test_prompt_with_arguments",
            "test_prompt_with_image", "test_prompt_with_embedded_resource"} <= prompts


@pytest.mark.anyio
async def test_synthetic_tools_return_real_mcp_content_types(tmp_path: Path) -> None:
    gateway = make_fixture(root=tmp_path, port=18798)
    for name, content_type in (
        ("test_simple_text", "text"), ("test_image_content", "image"),
        ("test_audio_content", "audio"),
        ("test_embedded_resource", "resource"),
    ):
        value = await gateway.mcp.call_tool(name, {})
        assert isinstance(value, CallToolResult)
        assert value.is_error is False
        assert value.content[0].type == content_type


def test_fixture_port_is_bounded_and_no_external_bind(tmp_path: Path) -> None:
    for port in (0, 80, 65536):
        with pytest.raises(ValueError, match="conformance_fixture_port_invalid"):
            make_fixture(root=tmp_path, port=port)
    assert make_fixture(root=tmp_path, port=18799).config.host == "127.0.0.1"
