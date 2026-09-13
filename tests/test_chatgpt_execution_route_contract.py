from __future__ import annotations

from latka_jazn.bootstrap.chatgpt_host_preflight import plan_chatgpt_host_preflight
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostEnvironmentState,
    HostExecutionRoute,
    HostExecutorObservation,
    HostExecutorState,
    HostFilesystemState,
    HostRecoveryAction,
    aggregate_host_executor_observations,
    classify_host_executor_observation,
)


def test_local_executor_failure_can_select_explicit_remote_runtime_route() -> None:
    observation = HostExecutorObservation(
        surface="chat",
        process_created=False,
        error_class="ExecutionUnavailable",
        remote_runtime_transport_available=True,
    )

    decision = classify_host_executor_observation(observation)

    assert decision.executor_state is HostExecutorState.HOST_EXECUTOR_UNAVAILABLE
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.execution_route is HostExecutionRoute.REMOTE_RUNTIME
    assert decision.next_action is HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT
    assert decision.canonical_resume_entrypoint is None
    assert decision.runtime_state == "unverified"


def test_local_executor_failure_can_request_execution_handoff_without_claiming_recovery() -> None:
    observation = HostExecutorObservation(
        surface="chat",
        process_created=False,
        error_class="ExecutionUnavailable",
        execution_handoff_available=True,
    )

    decision = classify_host_executor_observation(observation)

    assert decision.executor_state is HostExecutorState.HOST_EXECUTOR_UNAVAILABLE
    assert decision.execution_route is HostExecutionRoute.HOST_HANDOFF
    assert decision.next_action is HostRecoveryAction.REQUEST_EXECUTION_HANDOFF
    assert decision.runtime_state == "unverified"


def test_aggregate_prefers_verified_local_executor_over_external_routes() -> None:
    snapshot = aggregate_host_executor_observations(
        [
            HostExecutorObservation(
                surface="chat",
                process_created=False,
                error_class="ExecutionUnavailable",
                remote_runtime_transport_available=True,
                execution_handoff_available=True,
            ),
            HostExecutorObservation(
                surface="desktop_executor",
                process_created=True,
                command_completed=True,
                returncode=0,
                filesystem_probe_succeeded=True,
            ),
        ]
    )

    assert snapshot.environment_state is HostEnvironmentState.DEGRADED
    assert snapshot.execution_route is HostExecutionRoute.LOCAL_EXECUTOR
    assert snapshot.next_action is HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
    assert snapshot.canonical_resume_entrypoint == "run.py"


def test_remote_runtime_preflight_does_not_require_or_invent_local_filesystem() -> None:
    decision = plan_chatgpt_host_preflight(
        [
            HostExecutorObservation(
                surface="chat",
                process_created=False,
                error_class="ExecutionUnavailable",
                remote_runtime_transport_available=True,
            )
        ],
        package_required=True,
    )

    assert decision.environment_state is HostEnvironmentState.REMOTE_CAPABLE
    assert decision.execution_route is HostExecutionRoute.REMOTE_RUNTIME
    assert decision.bootstrap_allowed is False
    assert decision.remote_runtime_allowed is True
    assert decision.handoff_required is False
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.reason_code == "local_executor_unavailable_remote_runtime_transport_available"


def test_handoff_preflight_is_explicit_and_fail_closed() -> None:
    decision = plan_chatgpt_host_preflight(
        [
            HostExecutorObservation(
                surface="chat",
                process_created=False,
                error_class="ExecutionUnavailable",
                execution_handoff_available=True,
            )
        ]
    )

    assert decision.environment_state is HostEnvironmentState.HANDOFF_REQUIRED
    assert decision.execution_route is HostExecutionRoute.HOST_HANDOFF
    assert decision.bootstrap_allowed is False
    assert decision.remote_runtime_allowed is False
    assert decision.handoff_required is True
    assert decision.next_action is HostRecoveryAction.REQUEST_EXECUTION_HANDOFF
