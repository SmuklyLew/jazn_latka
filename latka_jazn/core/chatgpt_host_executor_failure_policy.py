from __future__ import annotations

from latka_jazn.core.chatgpt_host_executor_decision import HostExecutorRecoveryDecision
from latka_jazn.core.chatgpt_host_executor_enums import (
    HostCommandState,
    HostExecutionRoute,
    HostExecutorState,
    HostFilesystemState,
    HostRecoveryAction,
)
from latka_jazn.core.chatgpt_host_executor_observation import (
    MAX_ALTERNATIVE_EXECUTOR_PROBES,
    HostExecutorObservation,
)
from latka_jazn.core.chatgpt_host_handoff_state import HostHandoffState
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("chatgpt_host_executor_contract")


def _failed(
    observation: HostExecutorObservation,
    action: HostRecoveryAction,
    route: HostExecutionRoute,
    reason: str,
    *,
    retry: bool = False,
    budget: int = 0,
) -> HostExecutorRecoveryDecision:
    return HostExecutorRecoveryDecision(
        SCHEMA_VERSION,
        HostExecutorState.HOST_EXECUTOR_UNAVAILABLE,
        HostCommandState.NOT_STARTED,
        HostFilesystemState.UNKNOWN,
        "unknown",
        "unverified",
        action,
        route,
        reason,
        retry,
        budget,
        None,
        observation.execution_handoff_state,
    )


def classify_failed_surface(observation: HostExecutorObservation) -> HostExecutorRecoveryDecision:
    if observation.remote_runtime_transport_available:
        return _failed(
            observation,
            HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT,
            HostExecutionRoute.REMOTE_RUNTIME,
            "local_executor_unavailable_remote_runtime_route_available",
        )

    state = observation.execution_handoff_state
    handoff_map = {
        HostHandoffState.REQUESTED: (
            HostRecoveryAction.AWAIT_EXECUTION_HANDOFF,
            "execution_handoff_decision_pending",
        ),
        HostHandoffState.ACCEPTED: (
            HostRecoveryAction.USE_ACCEPTED_EXECUTION_HANDOFF,
            "execution_handoff_accepted_by_user",
        ),
        HostHandoffState.AVAILABLE: (
            HostRecoveryAction.REQUEST_EXECUTION_HANDOFF,
            "local_executor_unavailable_execution_handoff_available",
        ),
    }
    if state in handoff_map:
        action, reason = handoff_map[state]
        return _failed(observation, action, HostExecutionRoute.HOST_HANDOFF, reason)

    remaining = max(0, MAX_ALTERNATIVE_EXECUTOR_PROBES - observation.alternative_probe_count)
    probe = bool(observation.alternative_surface_available and remaining > 0)
    action = HostRecoveryAction.PROBE_ALTERNATIVE_ONCE if probe else HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    if state is HostHandoffState.DECLINED:
        reason = "execution_handoff_declined_alternative_probe_pending" if probe else "execution_handoff_declined_by_user"
    elif state is HostHandoffState.UNAVAILABLE:
        reason = "execution_handoff_unavailable_alternative_probe_pending" if probe else "execution_handoff_unavailable"
    else:
        reason = "host_tool_failed_before_process_creation"
    return _failed(
        observation,
        action,
        HostExecutionRoute.NONE,
        reason,
        retry=probe,
        budget=remaining if probe else 0,
    )
