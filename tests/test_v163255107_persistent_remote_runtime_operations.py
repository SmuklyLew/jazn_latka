from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.version import PACKAGE_VERSION_FULL


ROOT = Path(__file__).resolve().parents[1]


def test_v107_deployment_contract_tracks_runtime_and_real_mcp_wire_names() -> None:
    path = ROOT / "deploy" / "chatgpt_mcp" / "deployment.contract.json"
    contract = json.loads(path.read_text(encoding="utf-8"))

    assert contract["schema_version"] == "jazn_public_mcp_deployment/v1"
    assert contract["runtime_version"] == PACKAGE_VERSION_FULL
    transport = contract["transport"]
    assert transport["protocol_version"] == "2026-07-28"
    assert transport["canonical_methods"] == [
        "server/discover",
        "tools/list",
        "tools/call",
    ]
    assert "mcp/list-tools" in transport["forbidden_non_mcp_aliases"]
    assert "mcp/invoke" in transport["forbidden_non_mcp_aliases"]


def test_v107_deployment_contract_requires_strict_readiness_and_supervision() -> None:
    contract = json.loads(
        (ROOT / "deploy" / "chatgpt_mcp" / "deployment.contract.json").read_text(
            encoding="utf-8"
        )
    )
    readiness = contract["runtime_readiness"]
    assert set(readiness["required_true_paths"]) >= {
        "ok",
        "system_fully_ready",
        "activation_truth_gate_eligible",
        "daemon.endpoint_reachable",
        "capability_matrix.conversation_ready",
    }
    assert readiness["required_non_empty_paths"] == ["daemon.daemon_instance_id"]
    assert set(readiness["runtime_version_paths"]) == {
        "runtime_version",
        "daemon.runtime_version",
    }
    assert readiness["runtime_version_must_match_package"] is True

    supervision = contract["supervision"]
    assert supervision["required_by_default"] is True
    assert supervision["opt_out_requires_external_supervision"] is True
    assert set(supervision["verified_reuse_requires"]) == {
        "supervisor_active",
        "supervisor_identity_confirmed",
        "supervisor_heartbeat_fresh",
    }


def test_v107_deployment_examples_keep_secrets_and_daemon_private() -> None:
    compose = (ROOT / "deploy" / "chatgpt_mcp" / "compose.cloudflare.example.yml").read_text(
        encoding="utf-8"
    )
    env_example = (ROOT / "deploy" / "chatgpt_mcp" / "jazn-mcp.env.example").read_text(
        encoding="utf-8"
    )
    service = (ROOT / "deploy" / "chatgpt_mcp" / "jazn-mcp.service").read_text(
        encoding="utf-8"
    )

    assert "8787:" not in compose
    assert "CLOUDFLARE_TUNNEL_TOKEN:?" in compose
    assert "CLOUDFLARED_IMAGE:?" in compose
    assert "cloudflare/cloudflared:latest" not in compose
    assert "JAZN_MCP_REQUIRE_SUPERVISOR: \"1\"" in compose
    assert "CLOUDFLARE_TUNNEL_TOKEN=" in env_example
    assert "Restart=on-failure" in service
    assert "KillMode=control-group" in service
