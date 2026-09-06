from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("chatgpt_host_executor_contract")
MAX_ALTERNATIVE_EXECUTOR_PROBES = 1


class HostExecutorState(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    HOST_EXECUTOR_UNAVAILABLE = "host_executor_unavailable"


class HostCommandState(str, Enum):
    NOT_STARTED = "not_started"
    STARTED_UNFINISHED = "started_unfinished"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class HostFilesystemState(str, Enum):
    UNKNOWN = "unknown"
    OBSERVED = "observed"


class HostRecoveryAction(str, Enum):
    PROBE_ALTERNATIVE_ONCE = "probe_alternative_once"
    STOP_LOCAL_BOOTSTRAP = "stop_local_bootstrap"
    RESUME_CANONICAL_DISCOVERY = "resume_canonical_discovery"
    DIAGNOSE_LOCAL_COMMAND = "diagnose_local_command"


@dataclass(frozen=True)
class HostExecutorObservation:
    """Bounded host observation that never infers more than was executed.

    ``process_created`` is the decisive truth boundary.  A tool-level failure
    before process creation cannot establish any fact about the local
    filesystem, package set, or Jaźń runtime.  Once a process exists, failures
    are command/process failures and must be diagnosed from the child process
    result rather than reclassified as host-executor absence.
    """

    process_created: bool
    command_completed: bool = False
    returncode: int | None = None
    error_class: str | None = None
    alternative_surface_available: bool = False
    alternative_probe_count: int = 0
    filesystem_probe_succeeded: bool | None = None

    def __post_init__(self) -> None:
        if self.alternative_probe_count < 0:
            raise ValueError("alternative_probe_count_must_be_non_negative")
        if self.command_completed and not self.process_created:
            raise ValueError("command_completed_requires_process_created")
        if self.returncode is not None and not self.command_completed:
            raise ValueError("returncode_requires_completed_command")
        if self.command_completed and self.returncode is None:
            raise ValueError("completed_command_requires_returncode")
        if self.filesystem_probe_succeeded is not None and not self.command_completed:
            raise ValueError("filesystem_probe_result_requires_completed_command")
        if self.filesystem_probe_succeeded is True and self.returncode != 0:
            raise ValueError("successful_filesystem_probe_requires_zero_returncode")


@dataclass(frozen=True)
class HostExecutorRecoveryDecision:
    schema_version: str
    executor_state: HostExecutorState
    command_state: HostCommandState
    filesystem_state: HostFilesystemState
    package_state: str
    runtime_state: str
    next_action: HostRecoveryAction
    reason_code: str
    retry_allowed: bool
    retry_budget_remaining: int
    canonical_resume_entrypoint: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "executor_state": self.executor_state.value,
            "command_state": self.command_state.value,
            "filesystem_state": self.filesystem_state.value,
            "package_state": self.package_state,
            "runtime_state": self.runtime_state,
            "next_action": self.next_action.value,
            "reason_code": self.reason_code,
            "retry_allowed": self.retry_allowed,
            "retry_budget_remaining": self.retry_budget_remaining,
            "canonical_resume_entrypoint": self.canonical_resume_entrypoint,
        }


def classify_host_executor_observation(
    observation: HostExecutorObservation,
) -> HostExecutorRecoveryDecision:
    """Classify one host observation without fabricating filesystem/runtime state."""

    if not observation.process_created:
        if not observation.error_class:
            return HostExecutorRecoveryDecision(
                schema_version=SCHEMA_VERSION,
                executor_state=HostExecutorState.UNKNOWN,
                command_state=HostCommandState.NOT_STARTED,
                filesystem_state=HostFilesystemState.UNKNOWN,
                package_state="unknown",
                runtime_state="unverified",
                next_action=HostRecoveryAction.STOP_LOCAL_BOOTSTRAP,
                reason_code="insufficient_executor_observation",
                retry_allowed=False,
                retry_budget_remaining=0,
                canonical_resume_entrypoint=None,
            )

        probes_remaining = max(
            0,
            MAX_ALTERNATIVE_EXECUTOR_PROBES - observation.alternative_probe_count,
        )
        may_probe_alternative = bool(
            observation.alternative_surface_available and probes_remaining > 0
        )
        return HostExecutorRecoveryDecision(
            schema_version=SCHEMA_VERSION,
            executor_state=HostExecutorState.HOST_EXECUTOR_UNAVAILABLE,
            command_state=HostCommandState.NOT_STARTED,
            filesystem_state=HostFilesystemState.UNKNOWN,
            package_state="unknown",
            runtime_state="unverified",
            next_action=(
                HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
                if may_probe_alternative
                else HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
            ),
            reason_code="host_tool_failed_before_process_creation",
            retry_allowed=may_probe_alternative,
            retry_budget_remaining=probes_remaining if may_probe_alternative else 0,
            canonical_resume_entrypoint=None,
        )

    filesystem_state = (
        HostFilesystemState.OBSERVED
        if observation.filesystem_probe_succeeded is True
        else HostFilesystemState.UNKNOWN
    )

    if not observation.command_completed:
        return HostExecutorRecoveryDecision(
            schema_version=SCHEMA_VERSION,
            executor_state=HostExecutorState.AVAILABLE,
            command_state=HostCommandState.STARTED_UNFINISHED,
            filesystem_state=filesystem_state,
            package_state="unknown",
            runtime_state="unverified",
            next_action=HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND,
            reason_code="local_process_started_without_completed_command",
            retry_allowed=False,
            retry_budget_remaining=0,
            canonical_resume_entrypoint=None,
        )

    if observation.returncode != 0:
        return HostExecutorRecoveryDecision(
            schema_version=SCHEMA_VERSION,
            executor_state=HostExecutorState.AVAILABLE,
            command_state=HostCommandState.FAILED,
            filesystem_state=filesystem_state,
            package_state="unknown",
            runtime_state="unverified",
            next_action=HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND,
            reason_code="local_command_returned_nonzero",
            retry_allowed=False,
            retry_budget_remaining=0,
            canonical_resume_entrypoint=None,
        )

    return HostExecutorRecoveryDecision(
        schema_version=SCHEMA_VERSION,
        executor_state=HostExecutorState.AVAILABLE,
        command_state=HostCommandState.SUCCEEDED,
        filesystem_state=filesystem_state,
        package_state="unknown",
        runtime_state="unverified",
        next_action=HostRecoveryAction.RESUME_CANONICAL_DISCOVERY,
        reason_code="executor_preflight_succeeded",
        retry_allowed=False,
        retry_budget_remaining=0,
        canonical_resume_entrypoint="run.py",
    )
