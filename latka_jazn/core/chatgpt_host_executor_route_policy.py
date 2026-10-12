from __future__ import annotations

from dataclasses import dataclass

from latka_jazn.core.chatgpt_host_executor_enums import (
    HostEnvironmentState,
    HostExecutionRoute,
    HostRecoveryAction,
)
from latka_jazn.core.chatgpt_host_handoff_state import HostHandoffState


@dataclass(frozen=True)
class HostAggregateRouteDecision:
    environment: HostEnvironmentState
    route: HostExecutionRoute
    action: HostRecoveryAction
    reason: str
    retry_allowed: bool = False
    retry_budget: int = 0
    resume: str | None = None


def resolve_verified_remote_route() -> HostAggregateRouteDecision:
    """Prefer an already verified remote runtime over local bootstrap surfaces.

    ``remote_runtime_transport_available`` is only set after the managed tunnel
    and the current host connector/app capability have both been verified. Once
    that stronger route exists, ordinary ChatGPT turns must not be coupled back
    to a local executor probe.
    """

    return HostAggregateRouteDecision(
        HostEnvironmentState.REMOTE_CAPABLE,
        HostExecutionRoute.REMOTE_RUNTIME,
        HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT,
        "verified_remote_runtime_route_preferred",
    )


def resolve_external_route(
    *,
    remote: bool,
    handoff: HostHandoffState,
    retry_allowed: bool,
    retry_budget: int,
    declined_retry: bool,
    all_failed_known: bool,
) -> HostAggregateRouteDecision:
    if remote:
        return HostAggregateRouteDecision(
            HostEnvironmentState.REMOTE_CAPABLE,
            HostExecutionRoute.REMOTE_RUNTIME,
            HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT,
            "local_executor_unavailable_remote_runtime_route_available",
        )
    if handoff is HostHandoffState.ACCEPTED:
        return HostAggregateRouteDecision(
            HostEnvironmentState.HANDOFF_ACCEPTED,
            HostExecutionRoute.HOST_HANDOFF,
            HostRecoveryAction.USE_ACCEPTED_EXECUTION_HANDOFF,
            "execution_handoff_accepted_by_user",
        )
    if handoff is HostHandoffState.REQUESTED:
        return HostAggregateRouteDecision(
            HostEnvironmentState.HANDOFF_PENDING,
            HostExecutionRoute.HOST_HANDOFF,
            HostRecoveryAction.AWAIT_EXECUTION_HANDOFF,
            "execution_handoff_decision_pending",
        )
    if handoff is HostHandoffState.AVAILABLE:
        return HostAggregateRouteDecision(
            HostEnvironmentState.HANDOFF_REQUIRED,
            HostExecutionRoute.HOST_HANDOFF,
            HostRecoveryAction.REQUEST_EXECUTION_HANDOFF,
            "local_executor_unavailable_execution_handoff_available",
        )
    if retry_allowed:
        reason = (
            "execution_handoff_declined_alternative_probe_pending"
            if declined_retry
            else "observed_surface_failed_alternative_probe_pending"
        )
        return HostAggregateRouteDecision(
            HostEnvironmentState.UNKNOWN,
            HostExecutionRoute.NONE,
            HostRecoveryAction.PROBE_ALTERNATIVE_ONCE,
            reason,
            True,
            retry_budget,
        )
    if handoff is HostHandoffState.DECLINED:
        return HostAggregateRouteDecision(
            HostEnvironmentState.HANDOFF_DECLINED,
            HostExecutionRoute.NONE,
            HostRecoveryAction.STOP_LOCAL_BOOTSTRAP,
            "execution_handoff_declined_by_user",
        )
    if all_failed_known:
        return HostAggregateRouteDecision(
            HostEnvironmentState.UNAVAILABLE,
            HostExecutionRoute.NONE,
            HostRecoveryAction.STOP_LOCAL_BOOTSTRAP,
            "all_observed_executor_surfaces_unavailable",
        )
    return HostAggregateRouteDecision(
        HostEnvironmentState.UNKNOWN,
        HostExecutionRoute.NONE,
        HostRecoveryAction.STOP_LOCAL_BOOTSTRAP,
        "insufficient_cross_surface_observation",
    )
