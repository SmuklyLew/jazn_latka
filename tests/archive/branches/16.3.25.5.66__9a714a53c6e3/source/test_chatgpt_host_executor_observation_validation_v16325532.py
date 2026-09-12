from __future__ import annotations

import pytest

from latka_jazn.core.chatgpt_host_executor_contract import (
    HostCommandState,
    HostExecutorObservation,
    HostExecutorState,
    HostRecoveryAction,
    classify_host_executor_observation,
)


def test_missing_pre_process_error_evidence_keeps_executor_state_unknown() -> None:
    decision = classify_host_executor_observation(
        HostExecutorObservation(process_created=False)
    )

    assert decision.executor_state is HostExecutorState.UNKNOWN
    assert decision.command_state is HostCommandState.NOT_STARTED
    assert decision.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert decision.reason_code == "insufficient_executor_observation"
    assert decision.retry_allowed is False
    assert decision.filesystem_state.value == "unknown"
    assert decision.package_state == "unknown"
    assert decision.runtime_state == "unverified"


def test_completed_command_requires_explicit_returncode() -> None:
    with pytest.raises(ValueError, match="completed_command_requires_returncode"):
        HostExecutorObservation(
            process_created=True,
            command_completed=True,
        )


def test_successful_filesystem_probe_requires_zero_returncode() -> None:
    with pytest.raises(
        ValueError,
        match="successful_filesystem_probe_requires_zero_returncode",
    ):
        HostExecutorObservation(
            process_created=True,
            command_completed=True,
            returncode=1,
            filesystem_probe_succeeded=True,
        )
