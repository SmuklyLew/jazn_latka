from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.mcp.chatgpt_plugin import (
    MCP_SCHEMA,
    PLUGIN_SCHEMA,
    build_portable_plugin_documents,
    validate_remote_mcp_endpoint,
    write_portable_plugin_package,
)


def test_plugin_documents_use_published_agent_plugin_schemas() -> None:
    documents = build_portable_plugin_documents("https://jazn.example.test/mcp")
    assert documents["plugin.json"]["$schema"] == PLUGIN_SCHEMA
    assert documents["plugin.json"]["name"] == "jazn-runtime"
    assert documents["mcp.json"] == {
        "$schema": MCP_SCHEMA,
        "mcpServers": {
            "jazn": {
                "type": "streamable-http",
                "url": "https://jazn.example.test/mcp",
            }
        },
    }


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://jazn.example.test/mcp",
        "https://user:pass@jazn.example.test/mcp",
        "https://jazn.example.test/mcp?token=secret",
        "https://jazn.example.test/not-mcp",
    ],
)
def test_plugin_endpoint_is_https_mcp_without_embedded_credentials(endpoint: str) -> None:
    with pytest.raises(ValueError):
        validate_remote_mcp_endpoint(endpoint)


def test_write_plugin_package_is_atomic_bounded_and_refuses_overwrite(tmp_path: Path) -> None:
    result = write_portable_plugin_package(tmp_path, "https://jazn.example.test/mcp")
    payload = result.to_dict()
    assert payload["ok"] is True
    assert {Path(item["path"]).name for item in payload["files"]} == {"plugin.json", "mcp.json"}
    plugin = json.loads((tmp_path / "plugin.json").read_text(encoding="utf-8"))
    mcp = json.loads((tmp_path / "mcp.json").read_text(encoding="utf-8"))
    assert plugin["repository"] == "https://github.com/SmuklyLew/jazn_latka"
    assert mcp["mcpServers"]["jazn"]["url"] == "https://jazn.example.test/mcp"
    with pytest.raises(FileExistsError, match="use_force"):
        write_portable_plugin_package(tmp_path, "https://jazn.example.test/mcp")


def test_cli_parser_accepts_production_oauth_and_plugin_package_modes() -> None:
    from latka_jazn.cli import build_parser

    parser = build_parser()
    public = parser.parse_args(
        [
            "mcp-http",
            "--public-oauth",
            "--oauth-issuer-url",
            "https://id.example.test/",
            "--oauth-resource-server-url",
            "https://jazn.example.test/mcp",
            "--oauth-introspection-url",
            "https://id.example.test/introspect",
        ]
    )
    assert public.public_oauth is True
    assert public.loopback_dev is False
    package = parser.parse_args(
        [
            "chatgpt-plugin-package",
            "--endpoint",
            "https://jazn.example.test/mcp",
            "--output",
            "plugin-out",
        ]
    )
    assert package.command == "chatgpt-plugin-package"
