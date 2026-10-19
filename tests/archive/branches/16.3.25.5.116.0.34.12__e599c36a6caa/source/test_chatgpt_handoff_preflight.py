from __future__ import annotations

from latka_jazn.bootstrap.chatgpt_host_preflight import plan_chatgpt_host_preflight
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostEnvironmentState,
    HostExecutionRoute,
    HostExecutorObservation,
    HostFilesystemState,
    HostHandoffState,
    HostRecoveryAction,
)


def _decision(state: HostHandoffState, *, remote: bool = False):
    return plan_chatgpt_host_preflight([
        HostExecutorObservation(
            process_created=False,
            error_class="ExecutionUnavailable",
            surface="chat",
            execution_handoff_state=state,
            remote_runtime_transport_available=remote,
        )
    ])


def test_declined_handoff_preflight_is_terminal_without_reprompt() -> None:
    decision = _decision(HostHandoffState.DECLINED)
    assert decision.environment_state is HostEnvironmentState.HANDOFF_DECLINED
    assert decision.execution_route is HostExecutionRoute.NONE
    assert decision.handoff_required is False
    assert decision.handoff_state is HostHandoffState.DECLINED
    assert decision.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert decision.reason_code == "execution_handoff_declined_by_user"
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.runtime_state == "unverified"


def test_requested_handoff_preflight_waits_for_existing_decision() -> None:
    decision = _decision(HostHandoffState.REQUESTED)
    assert decision.environment_state is HostEnvironmentState.HANDOFF_PENDING
    assert decision.handoff_required is False
    assert decision.next_action is HostRecoveryAction.AWAIT_EXECUTION_HANDOFF


def test_accepted_handoff_preflight_uses_existing_consent() -> None:
    decision = _decision(HostHandoffState.ACCEPTED)
    assert decision.environment_state is HostEnvironmentState.HANDOFF_ACCEPTED
    assert decision.handoff_required is False
    assert decision.next_action is HostRecoveryAction.USE_ACCEPTED_EXECUTION_HANDOFF


def test_remote_runtime_remains_eligible_after_handoff_decline() -> None:
    decision = _decision(HostHandoffState.DECLINED, remote=True)
    assert decision.environment_state is HostEnvironmentState.REMOTE_CAPABLE
    assert decision.remote_runtime_allowed is True
    assert decision.execution_route is HostExecutionRoute.REMOTE_RUNTIME
    assert decision.next_action is HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT
