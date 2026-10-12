from __future__ import annotations

from typing import Any

from latka_jazn.core.chatgpt_host_executor_decision import HostExecutorRecoveryDecision
from latka_jazn.core.chatgpt_host_executor_enums import (
    HostEnvironmentState,
    HostExecutionRoute,
    HostRecoveryAction,
)
from latka_jazn.core.chatgpt_host_executor_failure_codes import classify_prespan_error
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


def host_failure_stage(observation: HostExecutorObservation) -> tuple[str, str]:
    """Return a bounded diagnostic stage without changing routing semantics."""

    if observation.process_created:
        return "post_spawn", "process_evidence"
    if observation.spawn_phase:
        return observation.spawn_phase, "host_reported"
    if observation.executor_allocation_state is False:
        return "executor_allocation", "derived"
    if observation.materialization_state is False:
        return "materialization", "derived"
    if observation.mount_preparation_state is False:
        return "mount_preparation", "derived"
    if (
        observation.executor_allocation_state is True
        and observation.materialization_state is True
        and observation.mount_preparation_state is True
    ):
        return "process_spawn", "derived"
    return "pre_spawn_unknown", "derived"


def surface_payload(
    observation: HostExecutorObservation,
    decision: HostExecutorRecoveryDecision,
) -> dict[str, Any]:
    payload = decision.to_dict()
    payload.pop("schema_version", None)

    candidate = classify_prespan_error(
        observation.error_class, error_message=observation.error_message
    )
    prespawn = (
        candidate
        if not observation.process_created
        and (
            observation.error_class
            or candidate.reason_code != "host_unknown_error_pre_spawn"
        )
        else None
    )
    failure_stage, failure_stage_source = host_failure_stage(observation)
    payload.update(
        surface=observation.surface,
        failure_stage=failure_stage,
        failure_stage_source=failure_stage_source,
        error_class=observation.error_class,
        error_code=observation.error_code,
        error_message=observation.error_message,
        host_request_id=observation.host_request_id,
        observed_at_utc=observation.observed_at_utc,
        process_created=observation.process_created,
        normalized_reason_code=(prespawn.reason_code if prespawn else None),
        retry_class=(prespawn.retry_class if prespawn else None),
        same_request_retry_allowed=(
            prespawn.same_request_retry_allowed if prespawn else False
        ),
        switch_surface_preferred=(
            prespawn.switch_surface_preferred if prespawn else False
        ),
        spawn_phase=observation.spawn_phase,
        intended_cwd=observation.intended_cwd,
        command_fingerprint_sha256=observation.command_fingerprint_sha256,
        executor_allocation_state=observation.executor_allocation_state,
        materialization_state=observation.materialization_state,
        mount_preparation_state=observation.mount_preparation_state,
        pid=observation.pid,
        observed_cwd=observation.observed_cwd,
        platform=observation.platform,
        effective_uid=observation.effective_uid,
        effective_gid=observation.effective_gid,
        remote_runtime_transport_available=observation.remote_runtime_transport_available,
        remote_runtime_transport=observation.remote_runtime_transport,
        remote_runtime_reason_code=observation.remote_runtime_reason_code,
        remote_runtime_blockers=list(observation.remote_runtime_blockers),
        execution_handoff_available=observation.execution_handoff_available,
        execution_handoff_state=observation.execution_handoff_state.value,
        observation_generation=observation.observation_generation,
    )
    return payload
