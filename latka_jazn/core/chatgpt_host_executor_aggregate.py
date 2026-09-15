from __future__ import annotations

from typing import Iterable

from latka_jazn.core.chatgpt_host_capability_snapshot import HostCapabilitySnapshot
from latka_jazn.core.chatgpt_host_executor_aggregate_helpers import (
    aggregate_handoff,
    resolve_local_route,
    surface_payload,
)
from latka_jazn.core.chatgpt_host_executor_classify import classify_host_executor_observation
from latka_jazn.core.chatgpt_host_executor_enums import (
    HostEnvironmentState,
    HostExecutionRoute,
    HostExecutorState,
    HostFilesystemState,
    HostRecoveryAction,
)
from latka_jazn.core.chatgpt_host_executor_observation import HostExecutorObservation
from latka_jazn.core.chatgpt_host_executor_route_policy import (
    resolve_external_route,
    resolve_verified_remote_route,
)
from latka_jazn.core.chatgpt_host_handoff_state import HostHandoffState
from latka_jazn.version import schema_version


CAPABILITY_SCHEMA_VERSION = schema_version("chatgpt_host_capability_snapshot")


def aggregate_host_executor_observations(
    observations: Iterable[HostExecutorObservation],
) -> HostCapabilitySnapshot:
    items = tuple(observations)
    if not items:
        return HostCapabilitySnapshot(
            CAPABILITY_SCHEMA_VERSION,
            HostEnvironmentState.UNKNOWN,
            HostFilesystemState.UNKNOWN,
            "unknown",
            "unverified",
            HostRecoveryAction.STOP_LOCAL_BOOTSTRAP,
            HostExecutionRoute.NONE,
            "no_executor_observations",
            False,
            0,
            None,
            False,
            False,
            (),
            HostHandoffState.UNKNOWN,
        )

    seen: set[str] = set()
    classified = []
    for observation in items:
        if observation.surface in seen:
            raise ValueError(f"duplicate_executor_surface:{observation.surface}")
        seen.add(observation.surface)
        classified.append((observation, classify_host_executor_observation(observation)))

    available = [pair for pair in classified if pair[1].executor_state is HostExecutorState.AVAILABLE]
    failed = [pair for pair in classified if pair[1].executor_state is HostExecutorState.HOST_EXECUTOR_UNAVAILABLE]
    unknown = [pair for pair in classified if pair[1].executor_state is HostExecutorState.UNKNOWN]
    retry = [pair for pair in failed if pair[1].retry_allowed]
    filesystem = (
        HostFilesystemState.OBSERVED
        if any(pair[1].filesystem_state is HostFilesystemState.OBSERVED for pair in classified)
        else HostFilesystemState.UNKNOWN
    )

    verified_remote = any(item.remote_runtime_transport_available for item in items)
    if verified_remote and available:
        route = resolve_verified_remote_route()
    elif available:
        route = resolve_local_route(
            degraded=bool(failed or unknown),
            has_success=any(pair[1].next_action is HostRecoveryAction.RESUME_CANONICAL_DISCOVERY for pair in available),
            has_diagnostic=any(pair[1].next_action is HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND for pair in available),
        )
    else:
        route = resolve_external_route(
            remote=any(item.remote_runtime_transport_available for item in items),
            handoff=aggregate_handoff(items),
            retry_allowed=bool(retry),
            retry_budget=max((pair[1].retry_budget_remaining for pair in retry), default=0),
            declined_retry=any(pair[0].execution_handoff_state is HostHandoffState.DECLINED for pair in retry),
            all_failed_known=bool(failed and not unknown),
        )

    return HostCapabilitySnapshot(
        CAPABILITY_SCHEMA_VERSION,
        route.environment,
        filesystem,
        "unknown",
        "unverified",
        route.action,
        route.route,
        route.reason,
        route.retry_allowed,
        route.retry_budget,
        route.resume,
        any(item.remote_runtime_transport_available for item in items),
        any(item.execution_handoff_available for item in items),
        tuple(surface_payload(*pair) for pair in classified),
        aggregate_handoff(items),
    )
