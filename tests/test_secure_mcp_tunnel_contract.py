from __future__ import annotations

from pathlib import Path
import shlex
import subprocess

from latka_jazn.mcp.secure_tunnel import (
    build_secure_mcp_tunnel_plan,
    classify_tunnel_runtime_status,
    quote_command,
)


def test_secure_tunnel_plan_targets_verified_stdio_bootstrap_without_public_listener(tmp_path: Path) -> None:
    plan = build_secure_mcp_tunnel_plan(
        tmp_path,
        tunnel_id="tun_test",
        profile_name="jazn-test",
        tunnel_client_binary="tunnel-client",
        python_executable="python",
        platform="posix",
        env={},
    ).to_dict()

    assert plan["transport"] == "openai_secure_mcp_tunnel_stdio"
    assert plan["local_mcp_transport"] == "stdio"
    assert plan["inbound_public_port_required"] is False
    assert plan["remote_runtime_transport_bundled"] is False
    assert plan["package_contains_tunnel_target"] is True
    assert plan["stdio_mcp_argv"][-3:] == ["--root", str(tmp_path.resolve())][-3:]
    assert "latka_jazn/mcp/tunnel_bootstrap.py" in plan["stdio_mcp_command"].replace("\\", "/")
    assert plan["init_argv"][:4] == ["tunnel-client", "init", "--sample", "sample_mcp_stdio_local"]
    assert "tun_test" in plan["init_argv"]
    assert "CONTROL_PLANE_API_KEY" in plan["required_environment"]
    assert "CONTROL_PLANE_TUNNEL_ID" in plan["required_environment"]


def test_command_quoting_is_platform_specific_but_argv_preserving() -> None:
    argv = [r"C:\Program Files\Python\python.exe", "-X", "utf8", r"C:\Jaźń Root\bridge.py"]

    assert quote_command(argv, platform="windows") == subprocess.list2cmdline(argv)
    assert quote_command(argv, platform="linux") == shlex.join(argv)


def test_remote_runtime_route_requires_all_managed_tunnel_readiness_fields() -> None:
    ready = classify_tunnel_runtime_status(
        {"process_running": True, "healthy": True, "ready": True}
    )
    assert ready["remote_runtime_transport_available"] is True
    assert ready["execution_route"] == "remote_runtime"
    assert ready["next_action"] == "use_remote_runtime_transport"

    for missing in ("process_running", "healthy", "ready"):
        payload = {"process_running": True, "healthy": True, "ready": True}
        payload[missing] = False
        blocked = classify_tunnel_runtime_status(payload)
        assert blocked["remote_runtime_transport_available"] is False
        assert blocked["execution_route"] == "none"
        assert blocked["reason_code"] == "secure_mcp_tunnel_not_fully_ready"


def test_unknown_tunnel_status_fails_closed() -> None:
    status = classify_tunnel_runtime_status(None)
    assert status["process_running"] is False
    assert status["healthy"] is False
    assert status["ready"] is False
    assert status["remote_runtime_transport_available"] is False
