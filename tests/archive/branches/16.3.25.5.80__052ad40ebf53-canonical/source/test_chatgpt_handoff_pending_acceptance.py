from __future__ import annotations

from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutionRoute,
    HostExecutorObservation,
    HostHandoffState,
    HostRecoveryAction,
    classify_host_executor_observation,
)


def _observation(state: HostHandoffState) -> HostExecutorObservation:
    return HostExecutorObservation(
        process_created=False,
        error_class="ExecutionUnavailable",
        surface="chat",
        execution_handoff_state=state,
    )


def test_requested_handoff_waits_instead_of_reprompting() -> None:
    decision = classify_host_executor_observation(
        _observation(HostHandoffState.REQUESTED)
    )
    assert decision.execution_route is HostExecutionRoute.HOST_HANDOFF
    assert decision.next_action is HostRecoveryAction.AWAIT_EXECUTION_HANDOFF
    assert decision.reason_code == "execution_handoff_decision_pending"
    assert decision.retry_allowed is False


def test_accepted_handoff_uses_existing_user_consent() -> None:
    decision = classify_host_executor_observation(
        _observation(HostHandoffState.ACCEPTED)
    )
    assert decision.execution_route is HostExecutionRoute.HOST_HANDOFF
    assert decision.next_action is HostRecoveryAction.USE_ACCEPTED_EXECUTION_HANDOFF
    assert decision.reason_code == "execution_handoff_accepted_by_user"
    assert decision.retry_allowed is False
