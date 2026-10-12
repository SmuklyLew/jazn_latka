from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.bootstrap.chatgpt_host_preflight import (
    ChatGptIngressMode,
    plan_chatgpt_host_preflight,
    plan_chatgpt_remote_ingress_preflight,
)
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutionRoute,
    HostExecutorObservation,
    HostRecoveryAction,
)
from latka_jazn.mcp.chatgpt_plugin import build_portable_plugin_documents
from latka_jazn.mcp.chatgpt_toolset import (
    CHATGPT_TOOLSET_REVISION,
    REQUIRED_CHATGPT_TURN_TOOLS,
    REQUIRED_CHATGPT_TURN_TOOLS_SHA256,
    classify_current_message_toolset,
)
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _local_success() -> HostExecutorObservation:
    return HostExecutorObservation(
        surface="ordinary_chat_local_executor",
        process_created=True,
        command_completed=True,
        returncode=0,
        filesystem_probe_succeeded=True,
    )


def _remote_success() -> HostExecutorObservation:
    return HostExecutorObservation(
        surface="ordinary_chat_remote_app",
        process_created=False,
        error_class="ExecutionUnavailable",
        remote_runtime_transport_available=True,
        remote_runtime_transport="public_streamable_http",
        remote_runtime_reason_code="public_streamable_http_remote_failover_ready",
    )


def test_ordinary_chat_remote_only_never_promotes_local_executor() -> None:
    decision = plan_chatgpt_remote_ingress_preflight([_local_success()])

    assert decision.ingress_mode is ChatGptIngressMode.REMOTE_ONLY
    assert decision.local_executor_fallback_allowed is False
    assert decision.bootstrap_allowed is False
    assert decision.remote_runtime_allowed is False
    assert decision.execution_route is HostExecutionRoute.NONE
    assert decision.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert decision.reason_code == "chatgpt_remote_only_requires_verified_runtime"


def test_operator_recovery_must_be_explicit_to_use_local_executor() -> None:
    decision = plan_chatgpt_host_preflight(
        [_local_success()],
        ingress_mode=ChatGptIngressMode.OPERATOR_RECOVERY,
    )

    assert decision.ingress_mode is ChatGptIngressMode.OPERATOR_RECOVERY
    assert decision.local_executor_fallback_allowed is True
    assert decision.bootstrap_allowed is True
    assert decision.execution_route is HostExecutionRoute.LOCAL_EXECUTOR


def test_verified_remote_runtime_wins_in_remote_only_mode() -> None:
    decision = plan_chatgpt_remote_ingress_preflight([_remote_success()])

    assert decision.remote_runtime_available is True
    assert decision.remote_runtime_allowed is True
    assert decision.bootstrap_allowed is False
    assert decision.execution_route is HostExecutionRoute.REMOTE_RUNTIME
    assert decision.next_action is HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT


def test_toolset_fingerprint_is_stable_and_reported() -> None:
    result = classify_current_message_toolset(
        REQUIRED_CHATGPT_TURN_TOOLS,
        current_message_toolset_observed=True,
    )

    assert result["full_turn_toolset_callable"] is True
    assert result["required_chatgpt_turn_tools_revision"] == CHATGPT_TOOLSET_REVISION
    assert result["required_chatgpt_turn_tools_sha256"] == REQUIRED_CHATGPT_TURN_TOOLS_SHA256
    assert len(REQUIRED_CHATGPT_TURN_TOOLS_SHA256) == 64


def test_startup_contract_declares_remote_only_ingress() -> None:
    contract = json.loads(
        (ROOT / "latka_jazn/resources/startup_contract.json").read_text(encoding="utf-8")
    )

    assert contract["version"] == PACKAGE_VERSION
    assert contract["chatgpt_ingress_mode"] == "remote_only"
    assert contract["chatgpt_local_executor_fallback_allowed"] is False
    assert contract["chatgpt_operator_recovery_mode"] == "operator_recovery"
    assert contract["chatgpt_operator_recovery_requires_explicit_opt_in"] is True
    assert contract["chatgpt_fallback_transport"] == "daemon_bound_transactional_turns"
    assert contract["chatgpt_ordinary_ingress_fallback_transport"] == "none_fail_closed"
    assert contract["chatgpt_ordinary_ingress_transport"] == "remote_mcp_app"
    assert contract["chatgpt_required_turn_tools_revision"] == CHATGPT_TOOLSET_REVISION
    assert contract["chatgpt_required_turn_tools"] == list(REQUIRED_CHATGPT_TURN_TOOLS)
    assert contract["chatgpt_frozen_snapshot_refresh_required_on_tool_change"] is True


def test_project_loader_forbids_executor_fallback_for_ordinary_chat() -> None:
    loader = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(
        encoding="utf-8"
    )

    assert len(loader) <= 5000
    assert "zwykła rozmowa chatgpt = remote-only" in loader.lower()
    assert "NIE próbuj lokalnego/process executora" in loader
    assert "operator_recovery" in loader
    assert "Refresh/Recreate/republish" in loader
    assert "Jeżeli `remote_runtime` nie jest zweryfikowany, oceń local process execution" not in loader


def test_portable_plugin_fails_closed_on_stale_tool_surface() -> None:
    plugin = build_portable_plugin_documents("https://jazn.example.test/mcp")["plugin.json"]
    prompts = plugin["extensions"]["com.openai"]["interface"]["defaultPrompt"]

    assert any("refresh/recreate" in value.lower() for value in prompts)
    assert any("never fall back to a local chatgpt executor" in value.lower() for value in prompts)


def test_release_identity_tracks_remote_only_ingress_contract() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.113"
    assert PACKAGE_RELEASE_NAME == "remote-only-chatgpt-ingress-convergence"
