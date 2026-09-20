from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core import bridge_discovery


def test_bridge_discovery_publishes_managed_remote_failover_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        bridge_discovery,
        "status_daemon",
        lambda *_args, **_kwargs: {"active_state": "inactive"},
    )
    monkeypatch.setattr(
        bridge_discovery,
        "build_host_tool_capability_snapshot",
        lambda: {
            "status": "ready",
            "manifest_present": True,
            "manifest_source": "test",
            "verified_tools": [],
            "advertised_tools": [],
            "capability_confirmation_required_for_tools": [],
        },
    )
    monkeypatch.setattr(
        bridge_discovery,
        "tunnel_client_executable_status",
        lambda: {
            "found": True,
            "resolved_path": "/test/tunnel-client",
        },
    )

    payload = bridge_discovery.discover_runtime_bridges(JaznConfig(root=tmp_path))
    secure_mcp = payload["secure_mcp"]
    chatgpt = payload["chatgpt_bridge"]

    assert secure_mcp["status"] == "implemented_secure_tunnel_managed_runtime_target"
    assert secure_mcp["preferred_supervision"] == "tunnel_client_managed_runtime"
    assert secure_mcp["managed_connect_argv"][1:3] == ["runtimes", "connect"]
    assert secure_mcp["managed_status_argv"][1:3] == ["runtimes", "status"]
    assert secure_mcp["managed_stop_argv"][1:3] == ["runtimes", "stop"]
    assert secure_mcp["managed_tunnel_readiness_is_host_route_readiness"] is False
    assert secure_mcp["host_connector_capability_required"] is True
    assert secure_mcp["remote_failover_classifier"] == "classify_remote_runtime_failover"
    assert secure_mcp["remote_runtime_route_evidence"] == (
        "all_managed_readiness_fields_true_plus_host_connector_capability"
    )
    assert chatgpt["remote_failover_policy"] == (
        "managed_tunnel_ready_plus_explicit_host_connector_capability"
    )
