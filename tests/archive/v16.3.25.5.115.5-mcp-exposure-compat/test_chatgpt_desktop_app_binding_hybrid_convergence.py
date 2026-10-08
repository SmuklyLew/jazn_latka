from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.mcp.chatgpt_plugin import (
    build_portable_plugin_documents,
    validate_registered_app_id,
)
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "app_id",
    (
        "plugin_asdk_app_abc123",
        "asdk_app_abc123",
        "connector_abc123",
        "templated_apps_abc123",
    ),
)
def test_registered_app_id_accepts_supported_chatgpt_binding_prefixes(
    app_id: str,
) -> None:
    assert validate_registered_app_id(app_id) == app_id


def test_registered_app_only_package_preserves_hybrid_turn_policy() -> None:
    documents = build_portable_plugin_documents(
        registered_app_id="plugin_asdk_app_abc123",
    )

    assert set(documents) == {"plugin.json", ".app.json"}
    plugin = documents["plugin.json"]
    assert plugin["extensions"]["com.openai"]["apps"] == "./.app.json"

    prompts = plugin["extensions"]["com.openai"]["interface"]["defaultPrompt"]
    joined = " ".join(prompts).lower()

    assert "complete current-message jaźń mcp/app toolset" in joined
    assert "call jazn_status as the read-only readiness probe" in joined
    assert "bounded verified host-local bootstrap fallback" in joined
    assert "same route and request_id" in joined
    assert "action=display_exact" in joined
    assert "never fall back to a local chatgpt executor" not in joined


def test_startup_contract_separates_registered_app_binding_from_capability_evidence() -> None:
    contract = json.loads(
        (ROOT / "latka_jazn/resources/startup_contract.json").read_text(
            encoding="utf-8"
        )
    )

    assert contract["version"] == PACKAGE_VERSION
    assert contract["chatgpt_ingress_mode"] == "hybrid_adaptive"
    assert contract["chatgpt_registered_app_binding_supported"] is True
    assert contract["chatgpt_registered_app_manifest"] == ".app.json"
    assert contract["chatgpt_registered_app_binding_requires_remote_endpoint"] is False
    assert (
        contract["chatgpt_registered_app_binding_is_current_message_capability_evidence"]
        is False
    )
    assert contract["chatgpt_canonical_turn_tool_visibility"] == ["model", "app"]
    assert contract["chatgpt_legacy_initialize_tool_visibility_normalized"] is True
    assert contract["chatgpt_registered_app_remote_transport"] == "registered_mcp_app"
    assert contract["chatgpt_registered_app_status_schema"] == "jazn_registered_mcp_status/v1"
    assert contract["chatgpt_registered_app_status_redacted"] is True
    assert contract["chatgpt_registered_app_status_requires_current_message_invocation"] is True
    assert contract["chatgpt_route_switch_after_turn_submit_allowed"] is False


def test_release_identity_tracks_desktop_app_binding_hybrid_convergence() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.115.4"
    assert (
        PACKAGE_RELEASE_NAME
        == "unified-conversation-runtime-authority-hotfix"
    )
