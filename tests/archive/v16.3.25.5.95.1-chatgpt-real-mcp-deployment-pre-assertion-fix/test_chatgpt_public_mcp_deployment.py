from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from latka_jazn.mcp.deployment import (
    DeploymentError,
    PublicMcpDeploymentConfig,
    activate_persistent_runtime,
    run_public_mcp_deployment,
)


ROOT = Path(__file__).resolve().parents[1]


def _env(tmp_path: Path) -> dict[str, str]:
    (tmp_path / "run.py").write_text("# runtime marker\n", encoding="utf-8")
    return {
        "JAZN_ROOT": str(tmp_path),
        "JAZN_MCP_OAUTH_CLIENT_ID": "client-id-secret-value",
        "JAZN_MCP_OAUTH_CLIENT_SECRET": "client-secret-value",
        "JAZN_MCP_OAUTH_ISSUER_URL": "https://id.example.test/",
        "JAZN_MCP_OAUTH_RESOURCE_SERVER_URL": "https://jazn.example.test/mcp",
        "JAZN_MCP_OAUTH_INTROSPECTION_URL": "https://id.example.test/oauth2/introspect",
        "JAZN_MCP_ALLOWED_HOSTS": "jazn.example.test,jazn-alt.example.test",
        "JAZN_MCP_ALLOWED_ORIGINS": "https://chatgpt.com",
    }


def test_public_deployment_builds_canonical_control_plane_commands_without_secrets(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    config = PublicMcpDeploymentConfig.from_environment(env)

    assert config.daemon_start_argv()[-3:] == ["--root", str(tmp_path.resolve())][-3:]
    assert "start" in config.daemon_start_argv()
    assert "status" in config.daemon_status_argv()
    assert "--json" in config.daemon_status_argv()

    gateway = config.gateway_argv()
    assert "mcp-http" in gateway
    assert "--public-oauth" in gateway
    assert "http://127.0.0.1:8787" in gateway
    assert gateway.count("--allowed-host") == 2

    command_text = "\n".join(gateway)
    assert env["JAZN_MCP_OAUTH_CLIENT_ID"] not in command_text
    assert env["JAZN_MCP_OAUTH_CLIENT_SECRET"] not in command_text
    assert config.public_dict()["secrets_in_argv"] is False


def test_public_deployment_rejects_non_loopback_daemon_and_non_https_resource(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    env["JAZN_MCP_DAEMON_URL"] = "https://daemon.example.test"
    with pytest.raises(DeploymentError, match="loopback"):
        PublicMcpDeploymentConfig.from_environment(env)

    env = _env(tmp_path)
    env["JAZN_MCP_OAUTH_RESOURCE_SERVER_URL"] = "http://jazn.example.test/mcp"
    with pytest.raises(DeploymentError, match="HTTPS"):
        PublicMcpDeploymentConfig.from_environment(env)


def test_public_deployment_requires_oauth_credentials_and_allowed_hosts(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    del env["JAZN_MCP_OAUTH_CLIENT_SECRET"]
    with pytest.raises(DeploymentError, match="credentials"):
        PublicMcpDeploymentConfig.from_environment(env)

    env = _env(tmp_path)
    env["JAZN_MCP_ALLOWED_HOSTS"] = ""
    with pytest.raises(DeploymentError, match="ALLOWED_HOSTS"):
        PublicMcpDeploymentConfig.from_environment(env)


def test_activation_requires_live_daemon_status_after_canonical_start(
    tmp_path: Path,
) -> None:
    config = PublicMcpDeploymentConfig.from_environment(_env(tmp_path))
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if "start" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="started\n", stderr="")
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps({"ok": True, "daemon_reachable": True}),
            stderr="",
        )

    result = activate_persistent_runtime(config, runner=runner)
    assert result["ok"] is True
    assert len(calls) == 2
    assert "start" in calls[0]
    assert "status" in calls[1]

    def not_ready(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "start" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps({"ok": True, "daemon_reachable": False}),
            stderr="",
        )

    with pytest.raises(DeploymentError, match="ready status"):
        activate_persistent_runtime(config, runner=not_ready)


def test_container_entrypoint_execs_gateway_only_after_runtime_is_ready(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    calls: list[list[str]] = []
    executed: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if "status" in argv:
            stdout = json.dumps({"ok": True, "daemon_reachable": True})
        else:
            stdout = ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    def execv(_executable: str, argv: Any) -> None:
        executed.append(list(argv))

    assert run_public_mcp_deployment(env, runner=runner, execv=execv) == 0
    assert len(calls) == 2
    assert len(executed) == 1
    assert "mcp-http" in executed[0]
    assert "--public-oauth" in executed[0]


def test_container_contract_is_non_root_and_never_exposes_private_daemon_port() -> None:
    dockerfile = (ROOT / "deploy" / "chatgpt_mcp" / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert 'pip install --no-cache-dir ".[mcp-http]"' in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert "EXPOSE 8787" not in dockerfile
    assert "/readyz" in dockerfile
    assert "latka_jazn.mcp.deployment" in dockerfile

    for private_entry in (".env", "workspace_runtime", "memory", "credentials.json"):
        assert private_entry in dockerignore
