from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.bootstrap.chatgpt_host_preflight import (
    ChatGptIngressMode,
    plan_chatgpt_adaptive_ingress_preflight,
    plan_chatgpt_host_preflight,
    plan_chatgpt_remote_ingress_preflight,
)
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutionRoute,
    HostExecutorObservation,
    HostFilesystemState,
    HostRecoveryAction,
)
from latka_jazn.mcp.chatgpt_plugin import build_portable_plugin_documents
from latka_jazn.mcp.chatgpt_toolset import (
    CHATGPT_TOOLSET_REVISION,
    REQUIRED_CHATGPT_TURN_TOOLS,
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


def _prespawn_failure(*, alternative: bool = False) -> HostExecutorObservation:
    return HostExecutorObservation(
        surface="ordinary_chat_local_executor",
        process_created=False,
        error_class="ClientError",
        alternative_surface_available=alternative,
    )


def _handoff_available() -> HostExecutorObservation:
    return HostExecutorObservation(
        surface="ordinary_chat_local_executor",
        process_created=False,
        error_class="ExecutionUnavailable",
        execution_handoff_available=True,
    )


def test_hybrid_adaptive_promotes_verified_local_executor_when_remote_is_absent() -> None:
    decision = plan_chatgpt_adaptive_ingress_preflight([_local_success()])

    assert decision.ingress_mode is ChatGptIngressMode.HYBRID_ADAPTIVE
    assert decision.local_executor_fallback_allowed is True
    assert decision.bootstrap_allowed is True
    assert decision.remote_runtime_allowed is False
    assert decision.execution_route is HostExecutionRoute.LOCAL_EXECUTOR
    assert decision.next_action is HostRecoveryAction.RESUME_CANONICAL_DISCOVERY


def test_verified_remote_runtime_wins_over_available_local_executor() -> None:
    decision = plan_chatgpt_adaptive_ingress_preflight(
        [_local_success(), _remote_success()]
    )

    assert decision.ingress_mode is ChatGptIngressMode.HYBRID_ADAPTIVE
    assert decision.remote_runtime_available is True
    assert decision.remote_runtime_allowed is True
    assert decision.bootstrap_allowed is False
    assert decision.execution_route is HostExecutionRoute.REMOTE_RUNTIME
    assert decision.next_action is HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT


def test_strict_remote_only_mode_remains_available_and_blocks_local_executor() -> None:
    decision = plan_chatgpt_remote_ingress_preflight([_local_success()])

    assert decision.ingress_mode is ChatGptIngressMode.REMOTE_ONLY
    assert decision.local_executor_fallback_allowed is False
    assert decision.bootstrap_allowed is False
    assert decision.execution_route is HostExecutionRoute.NONE
    assert decision.reason_code == "chatgpt_remote_only_requires_verified_runtime"


def test_hybrid_prespawn_failure_keeps_filesystem_unknown_and_fails_closed() -> None:
    decision = plan_chatgpt_adaptive_ingress_preflight([_prespawn_failure()])

    assert decision.executor_available is False
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.bootstrap_allowed is False
    assert decision.remote_runtime_allowed is False
    assert decision.execution_route is HostExecutionRoute.NONE
    assert decision.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP


def test_hybrid_allows_only_the_existing_single_alternative_probe_contract() -> None:
    decision = plan_chatgpt_adaptive_ingress_preflight(
        [_prespawn_failure(alternative=True)]
    )

    assert decision.bootstrap_allowed is False
    assert decision.execution_route is HostExecutionRoute.NONE
    assert decision.next_action is HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
    assert decision.capability_snapshot.retry_allowed is True
    assert decision.capability_snapshot.retry_budget_remaining == 1


def test_hybrid_ordinary_chat_never_promotes_host_handoff() -> None:
    decision = plan_chatgpt_adaptive_ingress_preflight([_handoff_available()])

    assert decision.handoff_required is False
    assert decision.bootstrap_allowed is False
    assert decision.remote_runtime_allowed is False
    assert decision.execution_route is HostExecutionRoute.NONE
    assert decision.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert decision.reason_code == "chatgpt_hybrid_adaptive_handoff_not_allowed"


def test_operator_recovery_retains_explicit_service_handoff_and_local_route() -> None:
    local = plan_chatgpt_host_preflight(
        [_local_success()],
        ingress_mode=ChatGptIngressMode.OPERATOR_RECOVERY,
    )
    handoff = plan_chatgpt_host_preflight(
        [_handoff_available()],
        ingress_mode=ChatGptIngressMode.OPERATOR_RECOVERY,
    )

    assert local.bootstrap_allowed is True
    assert local.execution_route is HostExecutionRoute.LOCAL_EXECUTOR
    assert handoff.execution_route is HostExecutionRoute.HOST_HANDOFF
    assert handoff.handoff_required is True


def test_startup_contract_declares_remote_first_local_fallback_without_midturn_switch() -> None:
    contract = json.loads(
        (ROOT / "latka_jazn/resources/startup_contract.json").read_text(encoding="utf-8")
    )

    assert contract["version"] == PACKAGE_VERSION
    assert contract["chatgpt_ingress_mode"] == "hybrid_adaptive"
    assert contract["chatgpt_remote_first"] is True
    assert contract["chatgpt_local_executor_fallback_allowed"] is True
    assert contract["chatgpt_local_executor_probe_budget"] == 1
    assert contract["chatgpt_local_executor_independent_alternative_probe_budget"] == 1
    assert contract["chatgpt_local_fallback_before_turn_submit_only"] is True
    assert contract["chatgpt_route_switch_after_turn_submit_allowed"] is False
    assert contract["chatgpt_ordinary_ingress_handoff_allowed"] is False
    assert contract["chatgpt_ordinary_ingress_fallback_transport"] == "verified_local_host_bootstrap"
    assert contract["chatgpt_required_turn_tools_revision"] == CHATGPT_TOOLSET_REVISION
    assert contract["chatgpt_required_turn_tools"] == list(REQUIRED_CHATGPT_TURN_TOOLS)


def test_project_loader_declares_hybrid_remote_first_and_preserves_finalization_gate() -> None:
    loader = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(
        encoding="utf-8"
    )

    assert len(loader) <= 5000
    assert "hybrid/adaptive remote-first" in loader
    assert "bounded local fallback" in loader
    assert "najwyżej jedną minimalną próbę" in loader
    assert "filesystem i paczka pozostają `unknown`" in loader
    assert "nie zmieniaj trasy" in loader
    assert "nie replayuj wiadomości użytkownika" in loader
    assert "action=display_exact" in loader


def test_portable_plugin_prefers_remote_but_allows_bounded_verified_local_bootstrap() -> None:
    plugin = build_portable_plugin_documents("https://jazn.example.test/mcp")["plugin.json"]
    prompts = plugin["extensions"]["com.openai"]["interface"]["defaultPrompt"]
    joined = " ".join(prompts).lower()

    assert "prefer the complete current-message jaźń remote toolset" in joined
    assert "bounded verified host-local bootstrap fallback" in joined
    assert "never replay the user message" in joined
    assert "never fall back to a local chatgpt executor" not in joined


def test_release_identity_tracks_hybrid_adaptive_ingress_contract() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.114"
    assert PACKAGE_RELEASE_NAME == "hybrid-adaptive-ingress-convergence"
