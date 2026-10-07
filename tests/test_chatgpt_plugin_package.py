from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.mcp.chatgpt_plugin import (
    MCP_SCHEMA,
    PLUGIN_SCHEMA,
    build_portable_plugin_documents,
    validate_registered_app_id,
    validate_remote_mcp_endpoint,
    write_portable_plugin_package,
)


def test_plugin_documents_use_published_agent_plugin_schemas() -> None:
    documents = build_portable_plugin_documents("https://jazn.example.test/mcp")
    assert documents["plugin.json"]["$schema"] == PLUGIN_SCHEMA
    assert documents["plugin.json"]["name"] == "jazn-runtime"
    assert documents["plugin.json"]["extensions"]["com.openai"]["interface"]["displayName"] == "Jaźń Runtime"
    assert documents["mcp.json"] == {
        "$schema": MCP_SCHEMA,
        "mcpServers": {
            "jazn": {
                "type": "streamable-http",
                "url": "https://jazn.example.test/mcp",
            }
        },
    }
    assert ".app.json" not in documents


def test_registered_chatgpt_app_binding_adds_app_manifest() -> None:
    app_id = "plugin_asdk_app_6a4c0062f3b88191855c0a80eac5d53d"
    documents = build_portable_plugin_documents(
        "https://jazn.example.test/mcp",
        registered_app_id=app_id,
    )
    assert documents["plugin.json"]["extensions"]["com.openai"]["apps"] == "./.app.json"
    assert documents[".app.json"] == {
        "apps": {
            "jazn": {
                "id": app_id,
                "required": True,
            }
        }
    }



def test_registered_app_binding_without_endpoint_omits_mcp_manifest() -> None:
    app_id = "plugin_asdk_app_6a4c0062f3b88191855c0a80eac5d53d"
    documents = build_portable_plugin_documents(registered_app_id=app_id)
    assert set(documents) == {"plugin.json", ".app.json"}
    assert documents["plugin.json"]["extensions"]["com.openai"]["apps"] == "./.app.json"
    assert documents[".app.json"]["apps"]["jazn"] == {
        "id": app_id,
        "required": True,
    }


def test_plugin_package_requires_endpoint_or_registered_app() -> None:
    with pytest.raises(
        ValueError,
        match="chatgpt_plugin_requires_endpoint_or_registered_app_id",
    ):
        build_portable_plugin_documents()


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


@pytest.mark.parametrize(
    "app_id",
    [
        "",
        "plugin_asdk_app bad",
        "https://chatgpt.com/plugins/plugin_asdk_app_123",
        "random_123",
    ],
)
def test_registered_app_id_is_fail_closed(app_id: str) -> None:
    with pytest.raises(ValueError, match="chatgpt_registered_app_id_invalid"):
        validate_registered_app_id(app_id)


def test_write_plugin_package_is_atomic_bounded_and_refuses_overwrite(tmp_path: Path) -> None:
    app_id = "plugin_asdk_app_6a4c0062f3b88191855c0a80eac5d53d"
    result = write_portable_plugin_package(
        tmp_path,
        "https://jazn.example.test/mcp",
        registered_app_id=app_id,
    )
    payload = result.to_dict()
    assert payload["ok"] is True
    assert payload["registered_app_id"] == app_id
    assert {Path(item["path"]).name for item in payload["files"]} == {
        "plugin.json",
        "mcp.json",
        ".app.json",
    }
    plugin = json.loads((tmp_path / "plugin.json").read_text(encoding="utf-8"))
    mcp = json.loads((tmp_path / "mcp.json").read_text(encoding="utf-8"))
    app = json.loads((tmp_path / ".app.json").read_text(encoding="utf-8"))
    assert plugin["repository"] == "https://github.com/SmuklyLew/jazn_latka"
    assert plugin["extensions"]["com.openai"]["apps"] == "./.app.json"
    assert mcp["mcpServers"]["jazn"]["url"] == "https://jazn.example.test/mcp"
    assert app["apps"]["jazn"]["id"] == app_id
    with pytest.raises(FileExistsError, match="use_force"):
        write_portable_plugin_package(
            tmp_path,
            "https://jazn.example.test/mcp",
            registered_app_id=app_id,
        )



def test_write_registered_app_binding_omits_mcp_json(tmp_path: Path) -> None:
    app_id = "plugin_asdk_app_6a4c0062f3b88191855c0a80eac5d53d"
    result = write_portable_plugin_package(
        tmp_path,
        registered_app_id=app_id,
    )
    payload = result.to_dict()
    assert payload["endpoint"] is None
    assert payload["registered_app_id"] == app_id
    assert {Path(item["path"]).name for item in payload["files"]} == {
        "plugin.json",
        ".app.json",
    }
    assert not (tmp_path / "mcp.json").exists()
    assert json.loads((tmp_path / ".app.json").read_text(encoding="utf-8"))[
        "apps"
    ]["jazn"]["id"] == app_id


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
            "--registered-app-id",
            "plugin_asdk_app_6a4c0062f3b88191855c0a80eac5d53d",
            "--output",
            "plugin-out",
        ]
    )
    assert package.command == "chatgpt-plugin-package"
    assert package.registered_app_id.startswith("plugin_asdk_app_")

    local_binding = parser.parse_args(
        [
            "chatgpt-plugin-package",
            "--registered-app-id",
            "plugin_asdk_app_6a4c0062f3b88191855c0a80eac5d53d",
            "--output",
            "plugin-local",
        ]
    )
    assert local_binding.endpoint is None
    assert local_binding.registered_app_id.startswith("plugin_asdk_app_")
