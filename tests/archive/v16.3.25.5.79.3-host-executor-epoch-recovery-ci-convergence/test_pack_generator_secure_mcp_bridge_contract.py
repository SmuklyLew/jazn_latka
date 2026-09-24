from __future__ import annotations

from pathlib import Path

from tools.jazn_pack_generator_app.constants import SYSTEM_BOOTSTRAP_REQUIRED_FILES
from tools.jazn_pack_generator_app.manifest import (
    SECURE_MCP_SERVER_MEMBER,
    SECURE_MCP_TUNNEL_BOOTSTRAP_MEMBER,
    SECURE_MCP_TUNNEL_CONTRACT_MEMBER,
    build_host_bootstrap_contract,
)
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry


def _plan(tmp_path: Path, members: tuple[str, ...]) -> PackPlan:
    source_root = tmp_path / "source"
    source_root.mkdir()
    entries = tuple(
        SourceEntry(
            source=source_root / name,
            archive_path=name,
            size_bytes=1,
            is_dir=False,
        )
        for name in members
    )
    return PackPlan(
        request=PackRequest(
            source_root=source_root,
            output_root=tmp_path / "out",
            content=ContentMode.SYSTEM,
        ),
        package_version="16.3.25.5.73-test",
        package_basename="jazn_latka_v16.3.25.5.73-test.system.zip",
        entries=entries,
        excluded=(),
        source_total_size_bytes=len(entries),
    )


def test_system_package_can_bundle_local_secure_mcp_target_without_claiming_remote_control_plane(
    tmp_path: Path,
) -> None:
    members = tuple(SYSTEM_BOOTSTRAP_REQUIRED_FILES) + (
        SECURE_MCP_SERVER_MEMBER,
        SECURE_MCP_TUNNEL_BOOTSTRAP_MEMBER,
        SECURE_MCP_TUNNEL_CONTRACT_MEMBER,
    )

    contract = build_host_bootstrap_contract(_plan(tmp_path, members))

    assert contract["active_system_root_eligible"] is True
    assert contract["secure_mcp_tunnel_target_bundled"] is True
    assert contract["secure_mcp_tunnel_target_members"] == [
        SECURE_MCP_SERVER_MEMBER,
        SECURE_MCP_TUNNEL_BOOTSTRAP_MEMBER,
        SECURE_MCP_TUNNEL_CONTRACT_MEMBER,
    ]
    assert contract["remote_runtime_transport_bundled"] is False
    assert contract["remote_runtime_transport_external"] == "openai_secure_mcp_tunnel"
    assert contract["package_can_create_host_executor"] is False
    assert "external_tunnel_client" in contract["remote_runtime_readiness_requires"]
    assert "explicit_chatgpt_connector_or_app_capability" in contract["remote_runtime_readiness_requires"]


def test_incomplete_secure_mcp_target_is_not_advertised_as_bundled(tmp_path: Path) -> None:
    members = tuple(SYSTEM_BOOTSTRAP_REQUIRED_FILES) + (SECURE_MCP_SERVER_MEMBER,)

    contract = build_host_bootstrap_contract(_plan(tmp_path, members))

    assert contract["active_system_root_eligible"] is True
    assert contract["secure_mcp_tunnel_target_bundled"] is False
    assert contract["remote_runtime_transport_bundled"] is False
