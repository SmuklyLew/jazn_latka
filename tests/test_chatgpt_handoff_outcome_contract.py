from __future__ import annotations

from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutionRoute,
    HostExecutorObservation,
    HostFilesystemState,
    HostHandoffState,
    HostRecoveryAction,
    classify_host_executor_observation,
)


def _failed(
    *,
    state: HostHandoffState | str = HostHandoffState.UNKNOWN,
    handoff_available: bool = False,
    alternative_available: bool = False,
    alternative_probe_count: int = 0,
    remote_available: bool = False,
) -> HostExecutorObservation:
    return HostExecutorObservation(
        process_created=False,
        error_class="ExecutionUnavailable",
        surface="chat",
        execution_handoff_available=handoff_available,
        execution_handoff_state=state,
        alternative_surface_available=alternative_available,
        alternative_probe_count=alternative_probe_count,
        remote_runtime_transport_available=remote_available,
    )


def test_boolean_handoff_capability_remains_backward_compatible() -> None:
    observation = _failed(handoff_available=True)
    assert observation.execution_handoff_state is HostHandoffState.AVAILABLE
    decision = classify_host_executor_observation(observation)
    assert decision.next_action is HostRecoveryAction.REQUEST_EXECUTION_HANDOFF
    assert decision.execution_route is HostExecutionRoute.HOST_HANDOFF


def test_declined_handoff_is_not_requested_again() -> None:
    decision = classify_host_executor_observation(_failed(state=HostHandoffState.DECLINED))
    assert decision.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert decision.execution_route is HostExecutionRoute.NONE
    assert decision.reason_code == "execution_handoff_declined_by_user"
    assert decision.retry_allowed is False
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.runtime_state == "unverified"


def test_declined_handoff_can_probe_one_distinct_local_alternative() -> None:
    decision = classify_host_executor_observation(
        _failed(state="declined", alternative_available=True)
    )
    assert decision.next_action is HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
    assert decision.execution_route is HostExecutionRoute.NONE
    assert decision.reason_code == "execution_handoff_declined_alternative_probe_pending"
    assert decision.retry_allowed is True
    assert decision.retry_budget_remaining == 1


def test_remote_runtime_wins_after_handoff_decline() -> None:
    decision = classify_host_executor_observation(
        _failed(state="declined", remote_available=True)
    )
    assert decision.next_action is HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT
    assert decision.execution_route is HostExecutionRoute.REMOTE_RUNTIME
