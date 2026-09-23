from __future__ import annotations

from latka_jazn.core.chatgpt_host_executor_contract import (
    HostEnvironmentState,
    HostExecutorObservation,
    HostHandoffState,
    HostRecoveryAction,
    aggregate_host_executor_observations,
)


def test_explicit_decline_suppresses_other_unaccepted_handoff_offer() -> None:
    snapshot = aggregate_host_executor_observations([
        HostExecutorObservation(
            process_created=False,
            error_class="ExecutionUnavailable",
            surface="chat",
            execution_handoff_state=HostHandoffState.DECLINED,
        ),
        HostExecutorObservation(
            process_created=False,
            error_class="ExecutionUnavailable",
            surface="alternate_ui",
            execution_handoff_available=True,
        ),
    ])
    assert snapshot.environment_state is HostEnvironmentState.HANDOFF_DECLINED
    assert snapshot.execution_handoff_state is HostHandoffState.DECLINED
    assert snapshot.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert snapshot.reason_code == "execution_handoff_declined_by_user"
    assert snapshot.retry_allowed is False
