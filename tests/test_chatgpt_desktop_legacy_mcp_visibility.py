from __future__ import annotations

from latka_jazn.mcp.server import (
    MCP_PROTOCOL_VERSION_LATEST_LEGACY,
    JaznMcpServer,
)


REQUIRED = {
    "jazn_status",
    "jazn_generate_visible_reply",
    "jazn_resume_visible_reply",
    "jazn_finalize_reply",
}


def test_initialize_era_tools_list_keeps_canonical_turn_tools_model_visible(tmp_path) -> None:
    server = JaznMcpServer(root=tmp_path, trust_stdio_parent=True)

    initialized = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION_LATEST_LEGACY,
                "capabilities": {},
                "clientInfo": {"name": "chatgpt-desktop-regression", "version": "1"},
            },
        }
    )
    assert initialized is not None
    assert initialized["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION_LATEST_LEGACY

    assert (
        server.handle(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        )
        is None
    )

    listing = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
    )
    assert listing is not None
    tools = {item["name"]: item for item in listing["result"]["tools"]}
    assert REQUIRED <= set(tools)

    for name in REQUIRED:
        metadata = tools[name].get("_meta") or {}
        assert metadata["ui"]["visibility"] == ["model", "app"]
        assert "openai/visibility" not in metadata

    audit_meta = tools["jazn_audit_lookup"]["_meta"]
    assert audit_meta["ui"]["visibility"] == ["app"]
    assert audit_meta["openai/visibility"] == "private"
