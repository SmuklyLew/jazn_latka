from __future__ import annotations

from typing import Any

from latka_jazn.core.chatgpt_host_executor_decision import HostExecutorRecoveryDecision
from latka_jazn.core.chatgpt_host_executor_enums import (
    HostEnvironmentState,
    HostExecutionRoute,
    HostRecoveryAction,
)
from latka_jazn.core.chatgpt_host_executor_observation import HostExecutorObservation
from latka_jazn.core.chatgpt_host_executor_route_policy import HostAggregateRouteDecision
from latka_jazn.core.chatgpt_host_handoff_state import HostHandoffState


def aggregate_handoff(items: tuple[HostExecutorObservation, ...]) -> HostHandoffState:
    states = {item.execution_handoff_state for item in items}
    for state in (
        HostHandoffState.ACCEPTED,
        HostHandoffState.REQUESTED,
        HostHandoffState.DECLINED,
        HostHandoffState.AVAILABLE,
        HostHandoffState.UNAVAILABLE,
    ):
        if state in states:
            return state
    return HostHandoffState.UNKNOWN


def resolve_local_route(
    *,
    degraded: bool,
    has_success: bool,
    has_diagnostic: bool,
) -> HostAggregateRouteDecision:
    environment = HostEnvironmentState.DEGRADED if degraded else HostEnvironmentState.AVAILABLE
    if has_success:
        reason = "usable_executor_surface_with_other_surface_failure" if degraded else "all_observed_executor_surfaces_available"
        return HostAggregateRouteDecision(
            environment,
            HostExecutionRoute.LOCAL_EXECUTOR,
            HostRecoveryAction.RESUME_CANONICAL_DISCOVERY,
            reason,
            resume="run.py",
        )
    if has_diagnostic:
        reason = "usable_executor_surface_requires_command_diagnosis" if degraded else "executor_surfaces_require_command_diagnosis"
        return HostAggregateRouteDecision(
            environment,
            HostExecutionRoute.LOCAL_EXECUTOR,
            HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND,
            reason,
        )
    return HostAggregateRouteDecision(
        environment,
        HostExecutionRoute.LOCAL_EXECUTOR,
        HostRecoveryAction.STOP_LOCAL_BOOTSTRAP,
        "available_surface_without_recovery_action",
    )


def surface_payload(
    observation: HostExecutorObservation,
    decision: HostExecutorRecoveryDecision,
) -> dict[str, Any]:
    payload = decision.to_dict()
    payload.pop("schema_version", None)
    payload.update(
        surface=observation.surface,
        error_class=observation.error_class,
        process_created=observation.process_created,
        remote_runtime_transport_available=observation.remote_runtime_transport_available,
        execution_handoff_available=observation.execution_handoff_available,
        execution_handoff_state=observation.execution_handoff_state.value,
    )
    return payload
