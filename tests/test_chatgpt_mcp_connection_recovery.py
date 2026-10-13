from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.mcp.chatgpt_plugin import (
    build_portable_plugin_documents,
    validate_remote_mcp_endpoint,
)
from tools.chatgpt_mcp_connection_doctor import (
    classify_endpoint,
    inspect_plugin_dir,
    main,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/mcp",
        "https://127.0.0.1/mcp",
        "https://192.168.1.100/mcp",
        "https://10.1.2.3/mcp",
        "https://[::1]:8080/mcp",
        "https://myserver.local/mcp",
        "https://localhost./mcp",
    ],
)
def test_private_plugin_remote_endpoints_are_refused(url: str) -> None:
    with pytest.raises(ValueError):
        validate_remote_mcp_endpoint(url)
    with pytest.raises(ValueError):
        build_portable_plugin_documents(url)
    assert classify_endpoint(url) == "loopback_or_private_endpoint"


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example.org/mcp",
        "https://user:pass@public.example.org/mcp",
        "https://public.example.org/mcp?token=secret",
        "https://public.example.org/mcp#fragment",
        "https://public.example.org/bad",
        "https://public.example.org:bad/mcp",
    ],
)
def test_offline_doctor_never_accepts_unsafe_or_invalid_url(url: str) -> None:
    assert classify_endpoint(url) != "public_https_endpoint_configured_unverified"


def _plugin_fixture(folder: Path, endpoint: str, *, secondary: str | None = None) -> None:
    (folder / "mcp.json").write_text(
        json.dumps({"mcpServers": {"ja_runtime": {"type": "streamable-http", "url": endpoint}}}),
        encoding="utf-8",
    )
    if secondary is not None:
        (folder / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"ja_runtime": {"type": "streamable-http", "url": secondary}}}),
            encoding="utf-8",
        )


def test_existing_desktop_loopback_descriptors_get_actionable_blocker(tmp_path: Path) -> None:
    _plugin_fixture(tmp_path, "http://127.0.0.1:8080/mcp", secondary="http://localhost:8080/mcp")
    report = inspect_plugin_dir(tmp_path)

    assert report["reason_code"] == "loopback_or_private_endpoint"
    assert report["endpoint_config_valid_for_remote_chatgpt"] is False
    assert report["remote_runtime_verified"] is False
    assert report["host_toolset_verified"] is False
    assert report["accepted_visible_reply_verified"] is False
    assert set(report["descriptor_files_found"]) == {"mcp.json", ".mcp.json"}
    assert "127.0.0.1" not in json.dumps(report)
    assert main(["--plugin-dir", str(tmp_path)]) == 2


def test_public_https_metadata_is_not_falsely_promoted_to_live_ready(tmp_path: Path) -> None:
    _plugin_fixture(tmp_path, "https://jazn.example.test/mcp")
    report = inspect_plugin_dir(tmp_path)

    assert report["reason_code"] == "public_https_endpoint_configured_unverified"
    assert report["endpoint_config_valid_for_remote_chatgpt"] is True
    assert report["remote_runtime_verified"] is False
    assert report["host_toolset_verified"] is False
    assert report["accepted_visible_reply_verified"] is False
    assert main(["--plugin-dir", str(tmp_path)]) == 0


def test_incorrect_plugin_descriptor_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "mcp.json").write_text('{"mcpServers": {"other": {}}}', encoding="utf-8")
    assert inspect_plugin_dir(tmp_path)["reason_code"] == "jazn_mcp_server_missing"


def test_doctor_rejects_oversized_descriptor_without_reading_it(tmp_path: Path) -> None:
    (tmp_path / "mcp.json").write_text("x" * 65537, encoding="utf-8")
    assert inspect_plugin_dir(tmp_path)["reason_code"] == "mcp_descriptor_too_large"


def test_stdio_only_package_does_not_claim_browser_web_connectivity(tmp_path: Path) -> None:
    (tmp_path / "mcp.json").write_text(
        json.dumps({"mcpServers": {"ja_runtime": {"command": "python", "args": ["server.py"]}}}),
        encoding="utf-8",
    )
    assert inspect_plugin_dir(tmp_path)["reason_code"] == "local_stdio_only"
