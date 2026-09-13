from __future__ import annotations

from latka_jazn.core.chatgpt_host_executor_decision import HostExecutorRecoveryDecision
from latka_jazn.core.chatgpt_host_executor_enums import (
    HostCommandState,
    HostExecutionRoute,
    HostExecutorState,
    HostFilesystemState,
    HostRecoveryAction,
)
from latka_jazn.core.chatgpt_host_executor_failure_policy import classify_failed_surface
from latka_jazn.core.chatgpt_host_executor_observation import HostExecutorObservation
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("chatgpt_host_executor_contract")


def classify_host_executor_observation(
    observation: HostExecutorObservation,
) -> HostExecutorRecoveryDecision:
    if not observation.process_created:
        if observation.error_class:
            return classify_failed_surface(observation)
        return HostExecutorRecoveryDecision(
            SCHEMA_VERSION,
            HostExecutorState.UNKNOWN,
            HostCommandState.NOT_STARTED,
            HostFilesystemState.UNKNOWN,
            "unknown",
            "unverified",
            HostRecoveryAction.STOP_LOCAL_BOOTSTRAP,
            HostExecutionRoute.NONE,
            "insufficient_executor_observation",
            False,
            0,
            None,
            observation.execution_handoff_state,
        )

    filesystem = (
        HostFilesystemState.OBSERVED
        if observation.filesystem_probe_succeeded is True
        else HostFilesystemState.UNKNOWN
    )
    if not observation.command_completed:
        command = HostCommandState.STARTED_UNFINISHED
        action = HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND
        reason = "local_process_started_without_completed_command"
        resume = None
    elif observation.returncode != 0:
        command = HostCommandState.FAILED
        action = HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND
        reason = "local_command_returned_nonzero"
        resume = None
    else:
        command = HostCommandState.SUCCEEDED
        action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
        reason = "executor_preflight_succeeded"
        resume = "run.py"

    return HostExecutorRecoveryDecision(
        SCHEMA_VERSION,
        HostExecutorState.AVAILABLE,
        command,
        filesystem,
        "unknown",
        "unverified",
        action,
        HostExecutionRoute.LOCAL_EXECUTOR,
        reason,
        False,
        0,
        resume,
        observation.execution_handoff_state,
    )
