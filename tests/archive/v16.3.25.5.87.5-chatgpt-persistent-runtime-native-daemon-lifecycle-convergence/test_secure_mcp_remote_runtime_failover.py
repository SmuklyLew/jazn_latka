from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.mcp.secure_tunnel import (
    build_secure_mcp_tunnel_plan,
    classify_remote_runtime_failover,
)


def test_managed_runtime_is_preferred_long_lived_supervision(tmp_path: Path) -> None:
    plan = build_secure_mcp_tunnel_plan(
        tmp_path,
        tunnel_id="tunnel_test",
        runtime_alias="jazn-chatgpt",
        tunnel_client_binary="tunnel-client",
        python_executable="python",
        platform="posix",
        env={"CONTROL_PLANE_API_KEY": "sk-must-never-be-embedded"},
    ).to_dict()

    assert plan["preferred_supervision"] == "tunnel_client_managed_runtime"
    assert plan["managed_connect_argv"][:5] == [
        "tunnel-client",
        "runtimes",
        "connect",
        "--alias",
        "jazn-chatgpt",
    ]
    assert plan["managed_connect_argv"][-1] == "--json"
    assert "--tunnel-id" in plan["managed_connect_argv"]
    assert "tunnel_test" in plan["managed_connect_argv"]
    assert "--runtime-api-key" in plan["managed_connect_argv"]
    assert "env:CONTROL_PLANE_API_KEY" in plan["managed_connect_argv"]
    assert "sk-must-never-be-embedded" not in plan["managed_connect_argv"]
    assert plan["managed_status_argv"] == [
        "tunnel-client",
        "runtimes",
        "status",
        "jazn-chatgpt",
        "--json",
    ]
    assert plan["managed_stop_argv"] == [
        "tunnel-client",
        "runtimes",
        "stop",
        "jazn-chatgpt",
        "--json",
    ]


def test_remote_failover_requires_tunnel_and_explicit_chatgpt_connector_capability() -> None:
    tunnel_ready = {"process_running": True, "healthy": True, "ready": True}

    missing_connector = classify_remote_runtime_failover(
        tunnel_ready,
        host_connector_capability_available=None,
    )
    assert missing_connector["tunnel_transport_ready"] is True
    assert missing_connector["host_connector_capability_available"] is False
    assert missing_connector["remote_runtime_transport_available"] is False
    assert missing_connector["execution_route"] == "none"
    assert missing_connector["reason_code"] == "chatgpt_connector_capability_not_verified"

    ready = classify_remote_runtime_failover(
        tunnel_ready,
        host_connector_capability_available=True,
    )
    assert ready["remote_runtime_transport_available"] is True
    assert ready["execution_route"] == "remote_runtime"
    assert ready["next_action"] == "use_remote_runtime_transport"
    assert ready["reason_code"] == "secure_mcp_remote_failover_ready"


def test_remote_failover_fails_closed_when_managed_tunnel_is_not_ready() -> None:
    blocked = classify_remote_runtime_failover(
        {"process_running": True, "healthy": True, "ready": False},
        host_connector_capability_available=True,
    )

    assert blocked["tunnel_transport_ready"] is False
    assert blocked["host_connector_capability_available"] is True
    assert blocked["remote_runtime_transport_available"] is False
    assert blocked["execution_route"] == "none"
    assert blocked["reason_code"] == "secure_mcp_tunnel_not_fully_ready"


def test_runtime_alias_must_be_stable_and_whitespace_free(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="runtime_alias_must_be_nonempty_and_whitespace_free"):
        build_secure_mcp_tunnel_plan(tmp_path, runtime_alias="bad alias", env={})
