from __future__ import annotations

from dataclasses import dataclass

from latka_jazn.bootstrap.chatgpt_host_preflight_types import HostPackageMaterializationState
from latka_jazn.core.chatgpt_host_capability_snapshot import HostCapabilitySnapshot
from latka_jazn.core.chatgpt_host_executor_enums import (
    HostEnvironmentState,
    HostExecutionRoute,
    HostFilesystemState,
    HostRecoveryAction,
)


@dataclass(frozen=True)
class PreflightRouteDecision:
    bootstrap_allowed: bool
    remote_runtime_allowed: bool
    handoff_required: bool
    next_action: HostRecoveryAction
    execution_route: HostExecutionRoute
    reason_code: str
    resume: str | None


def resolve_preflight_route(
    capability: HostCapabilitySnapshot,
    *,
    package_state: HostPackageMaterializationState,
    package_required: bool,
) -> PreflightRouteDecision:
    execution_usable = capability.environment_state in {
        HostEnvironmentState.AVAILABLE,
        HostEnvironmentState.DEGRADED,
    }
    filesystem_observed = capability.filesystem_state is HostFilesystemState.OBSERVED
    package_ready = package_state is HostPackageMaterializationState.READY
    package_gate_ok = package_ready if package_required else package_state not in {
        HostPackageMaterializationState.MATERIALIZING,
        HostPackageMaterializationState.INCOMPLETE,
        HostPackageMaterializationState.INVALID,
    }

    if capability.next_action is HostRecoveryAction.PROBE_ALTERNATIVE_ONCE:
        return PreflightRouteDecision(False, False, False, capability.next_action, capability.execution_route, capability.reason_code, None)
    if capability.next_action is HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND:
        return PreflightRouteDecision(False, False, False, capability.next_action, HostExecutionRoute.LOCAL_EXECUTOR, "executor_command_requires_diagnosis", None)
    if capability.execution_route is HostExecutionRoute.REMOTE_RUNTIME:
        return PreflightRouteDecision(False, True, False, capability.next_action, capability.execution_route, capability.reason_code, None)
    if capability.execution_route is HostExecutionRoute.HOST_HANDOFF:
        return PreflightRouteDecision(
            False,
            False,
            capability.next_action is HostRecoveryAction.REQUEST_EXECUTION_HANDOFF,
            capability.next_action,
            capability.execution_route,
            capability.reason_code,
            None,
        )
    if not execution_usable:
        return PreflightRouteDecision(False, False, False, capability.next_action, capability.execution_route, capability.reason_code, None)
    if not filesystem_observed:
        return PreflightRouteDecision(False, False, False, HostRecoveryAction.RESUME_CANONICAL_DISCOVERY, HostExecutionRoute.LOCAL_EXECUTOR, "filesystem_not_observed_yet", "run.py")
    if package_required and package_state is HostPackageMaterializationState.UNKNOWN:
        return PreflightRouteDecision(False, False, False, HostRecoveryAction.RESUME_CANONICAL_DISCOVERY, HostExecutionRoute.LOCAL_EXECUTOR, "required_package_not_observed", "run.py")
    if not package_gate_ok:
        return PreflightRouteDecision(False, False, False, HostRecoveryAction.RESUME_CANONICAL_DISCOVERY, HostExecutionRoute.LOCAL_EXECUTOR, f"attachment_package_{package_state.value}", "run.py")
    reason = "host_degraded_package_ready" if capability.environment_state is HostEnvironmentState.DEGRADED else "host_preflight_ready"
    return PreflightRouteDecision(True, False, False, HostRecoveryAction.RESUME_CANONICAL_DISCOVERY, HostExecutionRoute.LOCAL_EXECUTOR, reason, "run.py")
