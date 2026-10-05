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
    ensure_runtime_supervisor,
    run_public_mcp_deployment,
)
from latka_jazn.version import PACKAGE_VERSION_FULL


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


def _ready_status() -> dict[str, Any]:
    return {
        "ok": True,
        "daemon_reachable": True,
        "system_fully_ready": True,
        "conversation_ready": True,
        "activation_truth_gate_eligible": True,
        "runtime_version": PACKAGE_VERSION_FULL,
        "daemon_instance_id": "daemon-test-instance",
    }


def _supervisor_status() -> dict[str, Any]:
    return {
        "ok": True,
        "supervisor_active": True,
        "supervisor_identity_confirmed": True,
        "supervisor_heartbeat_fresh": True,
        "state": {"state": "daemon_live"},
    }


def test_public_deployment_builds_canonical_control_plane_commands_without_secrets(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    config = PublicMcpDeploymentConfig.from_environment(env)

    assert config.daemon_start_argv()[-2:] == ["--root", str(tmp_path.resolve())]
    assert "start" in config.daemon_start_argv()
    assert "status" in config.daemon_status_argv()
    assert "supervisor-status" in config.supervisor_status_argv()
    assert "supervisor-run" in config.supervisor_run_argv()
    assert config.require_supervisor is True

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


def test_public_deployment_requires_oauth_credentials_allowed_hosts_and_valid_supervisor_flag(
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

    env = _env(tmp_path)
    env["JAZN_MCP_REQUIRE_SUPERVISOR"] = "sometimes"
    with pytest.raises(DeploymentError, match="must be one of"):
        PublicMcpDeploymentConfig.from_environment(env)


def test_activation_requires_full_conversation_ready_status_and_exact_runtime_version(
    tmp_path: Path,
) -> None:
    config = PublicMcpDeploymentConfig.from_environment(_env(tmp_path))
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if "start" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="started\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(_ready_status()), stderr="")

    result = activate_persistent_runtime(config, runner=runner)
    assert result["conversation_ready"] is True
    assert len(calls) == 2

    def reachable_but_not_ready(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "start" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        payload = _ready_status()
        payload["conversation_ready"] = False
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

    with pytest.raises(DeploymentError, match="conversation_ready"):
        activate_persistent_runtime(config, runner=reachable_but_not_ready)

    def version_mismatch(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "start" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        payload = _ready_status()
        payload["runtime_version"] = "stale-version"
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

    with pytest.raises(DeploymentError, match="runtime_version"):
        activate_persistent_runtime(config, runner=version_mismatch)


def test_supervisor_is_reused_or_started_fail_closed(tmp_path: Path) -> None:
    config = PublicMcpDeploymentConfig.from_environment(_env(tmp_path))

    def already_active(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert "supervisor-status" in argv
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(_supervisor_status()), stderr="")

    result = ensure_runtime_supervisor(config, runner=already_active)
    assert result["supervisor_active"] is True

    observations = iter([
        {"ok": False, "supervisor_active": False},
        _supervisor_status(),
    ])
    spawned: list[list[str]] = []

    def transitioning(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert "supervisor-status" in argv
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(next(observations)), stderr="")

    class FakeProcess:
        def poll(self) -> None:
            return None

    def fake_popen(argv: list[str], **_kwargs: Any) -> FakeProcess:
        spawned.append(list(argv))
        return FakeProcess()

    result = ensure_runtime_supervisor(
        config,
        runner=transitioning,
        popen=fake_popen,
        sleeper=lambda _seconds: None,
        startup_timeout_seconds=1.0,
        poll_interval_seconds=0.01,
    )
    assert result["supervisor_active"] is True
    assert len(spawned) == 1
    assert "supervisor-run" in spawned[0]


def test_external_supervision_must_be_explicit(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env["JAZN_MCP_REQUIRE_SUPERVISOR"] = "0"
    config = PublicMcpDeploymentConfig.from_environment(env)
    result = ensure_runtime_supervisor(config)
    assert result["supervisor_required"] is False
    assert result["reason"] == "explicit_external_supervision_mode"


def test_container_entrypoint_execs_gateway_only_after_runtime_and_supervisor_ready(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    calls: list[list[str]] = []
    executed: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if "status" in argv and "supervisor-status" not in argv:
            stdout = json.dumps(_ready_status())
        elif "supervisor-status" in argv:
            stdout = json.dumps(_supervisor_status())
        else:
            stdout = ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    def execv(_executable: str, argv: Any) -> None:
        executed.append(list(argv))

    assert run_public_mcp_deployment(env, runner=runner, execv=execv) == 0
    assert len(executed) == 1
    assert "mcp-http" in executed[0]
    assert "--public-oauth" in executed[0]
    assert any("supervisor-status" in call for call in calls)


def test_container_contract_is_non_root_and_never_exposes_private_daemon_port() -> None:
    dockerfile = (ROOT / "deploy" / "chatgpt_mcp" / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert 'pip install --no-cache-dir ".[mcp-http]"' in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert "EXPOSE 8787" not in dockerfile
    assert "/healthz" in dockerfile
    assert "latka_jazn.mcp.deployment" in dockerfile

    for private_entry in (".env", "workspace_runtime", "memory", "credentials.json"):
        assert private_entry in dockerignore
