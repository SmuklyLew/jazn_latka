from __future__ import annotations

"""Security and packaging regression tests for MCP deploy v115.21.13."""

from pathlib import Path
import json

import pytest

from latka_jazn.mcp.deployment import DeploymentError, PublicMcpDeploymentConfig
from latka_jazn.version import PACKAGE_VERSION_FULL

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "chatgpt_mcp"


def _env(root: Path) -> dict[str, str]:
    (root / "run.py").write_text("# test marker\n", encoding="utf-8")
    return {
        "JAZN_ROOT": str(root),
        "JAZN_MCP_OAUTH_CLIENT_ID": "test-client",
        "JAZN_MCP_OAUTH_CLIENT_SECRET": "test-secret",
        "JAZN_MCP_OAUTH_ISSUER_URL": "https://identity.example.test/",
        "JAZN_MCP_OAUTH_RESOURCE_SERVER_URL": "https://jazn.example.test/mcp",
        "JAZN_MCP_OAUTH_INTROSPECTION_URL": "https://identity.example.test/introspect",
        "JAZN_MCP_ALLOWED_HOSTS": "jazn.example.test",
    }


def test_cloudflare_token_is_a_mounted_secret_not_an_argv_parameter() -> None:
    compose = (DEPLOY / "compose.cloudflare.example.yml").read_text(encoding="utf-8")
    assert "CLOUDFLARE_TUNNEL_TOKEN_FILE" in compose
    assert "--token-file" in compose
    assert "/run/secrets/cloudflare_tunnel_token" in compose
    assert "secrets:\n  cloudflare_tunnel_token:" in compose
    assert "    file: ${CLOUDFLARE_TUNNEL_TOKEN_FILE:" in compose
    assert "      - --token\n" not in compose
    assert "${CLOUDFLARE_TUNNEL_TOKEN:?" not in compose
    assert "image: ${CLOUDFLARED_IMAGE:?" in compose


def test_memory_is_persistent_and_separate_from_operational_workspace() -> None:
    compose = (DEPLOY / "compose.cloudflare.example.yml").read_text(encoding="utf-8")
    dockerfile = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "JAZN_MEMORY_ROOT: /opt/jazn/memory" in compose
    assert "- jazn-memory:/opt/jazn/memory" in compose
    assert "- jazn-runtime:/opt/jazn/workspace_runtime" in compose
    assert "  jazn-memory:" in compose
    assert 'VOLUME ["/opt/jazn/workspace_runtime", "/opt/jazn/memory"]' in dockerfile
    assert "    JAZN_MEMORY_ROOT=/opt/jazn/memory" in dockerfile
    assert "\nmemory\n" in ignore


def test_public_oauth_resource_host_must_be_allowlisted(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env["JAZN_MCP_ALLOWED_HOSTS"] = "other.example.test"
    with pytest.raises(DeploymentError, match="include the public resource-server"):
        PublicMcpDeploymentConfig.from_environment(env)


@pytest.mark.parametrize("key,value", [
    ("JAZN_MCP_OAUTH_RESOURCE_SERVER_URL", "https://jazn.example.test/mcp?token=bad"),
    ("JAZN_MCP_OAUTH_RESOURCE_SERVER_URL", "https://jazn.example.test/mcp#fragment"),
    ("JAZN_MCP_OAUTH_ISSUER_URL", "https://identity.example.test/#fragment"),
])
def test_public_oauth_url_rejects_ambiguous_suffixes(
    tmp_path: Path, key: str, value: str,
) -> None:
    env = _env(tmp_path)
    env[key] = value
    with pytest.raises(DeploymentError):
        PublicMcpDeploymentConfig.from_environment(env)


def test_deployment_contract_version_and_memory_truth_boundary() -> None:
    data = json.loads((DEPLOY / "deployment.contract.json").read_text(encoding="utf-8"))
    assert data["runtime_version"] == PACKAGE_VERSION_FULL
    assert data["security"]["cloudflare_tunnel_token_transport"] == "docker_compose_secret_token_file"
    assert data["security"]["memory_volume"] == "/opt/jazn/memory"
    assert data["security"]["private_memory_attached_by_release"] is False
