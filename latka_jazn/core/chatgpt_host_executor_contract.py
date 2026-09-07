from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Iterable

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("chatgpt_host_executor_contract")
CAPABILITY_SCHEMA_VERSION = schema_version("chatgpt_host_capability_snapshot")
MAX_ALTERNATIVE_EXECUTOR_PROBES = 1
_SURFACE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class HostExecutorState(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    HOST_EXECUTOR_UNAVAILABLE = "host_executor_unavailable"


class HostEnvironmentState(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


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


def _normalized_surface(value: str) -> str:
    surface = str(value or "").strip().lower()
    if not _SURFACE_RE.fullmatch(surface):
        raise ValueError(f"invalid_executor_surface:{value!r}")
    return surface


@dataclass(frozen=True)
class HostExecutorObservation:
    """Bounded observation of one concrete host execution surface.

    ``process_created`` is the decisive truth boundary for *this surface*.
    A tool-level failure before process creation cannot establish any fact
    about the local filesystem, package set, Jaźń runtime, or other execution
    surfaces.  Once a process exists, failures are command/process failures and
    must be diagnosed from the child process result.

    ``surface`` is deliberately extensible.  Known hosts can use values such as
    ``python_tool``, ``terminal`` or ``jupyter_kernel`` while older callers keep
    the backwards-compatible ``default`` surface.
    """

    process_created: bool
    command_completed: bool = False
    returncode: int | None = None
    error_class: str | None = None
    alternative_surface_available: bool = False
    alternative_probe_count: int = 0
    filesystem_probe_succeeded: bool | None = None
    surface: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "surface", _normalized_surface(self.surface))
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


@dataclass(frozen=True)
class HostCapabilitySnapshot:
    """Aggregate several independently observed host execution surfaces.

    A single broken bridge must never collapse a still-usable host into a
    global ``unavailable`` state.  ``degraded`` means at least one execution
    surface is usable and at least one other observed surface failed before
    process creation.  ``unavailable`` is reserved for an exhausted set of
    observed surfaces with no remaining bounded alternative probe.
    """

    schema_version: str
    environment_state: HostEnvironmentState
    filesystem_state: HostFilesystemState
    package_state: str
    runtime_state: str
    next_action: HostRecoveryAction
    reason_code: str
    retry_allowed: bool
    retry_budget_remaining: int
    canonical_resume_entrypoint: str | None
    surfaces: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "environment_state": self.environment_state.value,
            "filesystem_state": self.filesystem_state.value,
            "package_state": self.package_state,
            "runtime_state": self.runtime_state,
            "next_action": self.next_action.value,
            "reason_code": self.reason_code,
            "retry_allowed": self.retry_allowed,
            "retry_budget_remaining": self.retry_budget_remaining,
            "canonical_resume_entrypoint": self.canonical_resume_entrypoint,
            "surfaces": [dict(item) for item in self.surfaces],
        }


def classify_host_executor_observation(
    observation: HostExecutorObservation,
) -> HostExecutorRecoveryDecision:
    """Classify one host surface without fabricating filesystem/runtime state."""

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


def aggregate_host_executor_observations(
    observations: Iterable[HostExecutorObservation],
) -> HostCapabilitySnapshot:
    """Aggregate bounded observations without conflating independent surfaces."""

    items = tuple(observations)
    if not items:
        return HostCapabilitySnapshot(
            schema_version=CAPABILITY_SCHEMA_VERSION,
            environment_state=HostEnvironmentState.UNKNOWN,
            filesystem_state=HostFilesystemState.UNKNOWN,
            package_state="unknown",
            runtime_state="unverified",
            next_action=HostRecoveryAction.STOP_LOCAL_BOOTSTRAP,
            reason_code="no_executor_observations",
            retry_allowed=False,
            retry_budget_remaining=0,
            canonical_resume_entrypoint=None,
            surfaces=(),
        )

    seen: set[str] = set()
    classified: list[tuple[HostExecutorObservation, HostExecutorRecoveryDecision]] = []
    for observation in items:
        if observation.surface in seen:
            raise ValueError(f"duplicate_executor_surface:{observation.surface}")
        seen.add(observation.surface)
        classified.append((observation, classify_host_executor_observation(observation)))

    available = [pair for pair in classified if pair[1].executor_state is HostExecutorState.AVAILABLE]
    failed = [
        pair
        for pair in classified
        if pair[1].executor_state is HostExecutorState.HOST_EXECUTOR_UNAVAILABLE
    ]
    unknown = [pair for pair in classified if pair[1].executor_state is HostExecutorState.UNKNOWN]
    successful_preflight = [
        pair for pair in available if pair[1].next_action is HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
    ]
    started_unfinished_or_failed = [
        pair for pair in available if pair[1].next_action is HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND
    ]
    retry_decisions = [pair for pair in failed if pair[1].retry_allowed]

    filesystem_state = (
        HostFilesystemState.OBSERVED
        if any(pair[1].filesystem_state is HostFilesystemState.OBSERVED for pair in classified)
        else HostFilesystemState.UNKNOWN
    )

    if available:
        degraded = bool(failed or unknown)
        environment_state = (
            HostEnvironmentState.DEGRADED if degraded else HostEnvironmentState.AVAILABLE
        )
        if successful_preflight:
            next_action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
            canonical_resume_entrypoint = "run.py"
            reason_code = (
                "usable_executor_surface_with_other_surface_failure"
                if degraded
                else "all_observed_executor_surfaces_available"
            )
        elif started_unfinished_or_failed:
            next_action = HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND
            canonical_resume_entrypoint = None
            reason_code = (
                "usable_executor_surface_requires_command_diagnosis"
                if degraded
                else "executor_surfaces_require_command_diagnosis"
            )
        else:  # defensive: every AVAILABLE decision is covered above
            next_action = HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
            canonical_resume_entrypoint = None
            reason_code = "available_surface_without_recovery_action"
        retry_allowed = False
        retry_budget_remaining = 0
    elif retry_decisions:
        environment_state = HostEnvironmentState.UNKNOWN
        next_action = HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
        canonical_resume_entrypoint = None
        reason_code = "observed_surface_failed_alternative_probe_pending"
        retry_allowed = True
        retry_budget_remaining = max(pair[1].retry_budget_remaining for pair in retry_decisions)
    elif failed and not unknown:
        environment_state = HostEnvironmentState.UNAVAILABLE
        next_action = HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
        canonical_resume_entrypoint = None
        reason_code = "all_observed_executor_surfaces_unavailable"
        retry_allowed = False
        retry_budget_remaining = 0
    else:
        environment_state = HostEnvironmentState.UNKNOWN
        next_action = HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
        canonical_resume_entrypoint = None
        reason_code = "insufficient_cross_surface_observation"
        retry_allowed = False
        retry_budget_remaining = 0

    surface_payloads: list[dict[str, Any]] = []
    for observation, decision in classified:
        payload = decision.to_dict()
        payload.pop("schema_version", None)
        payload["surface"] = observation.surface
        payload["error_class"] = observation.error_class
        payload["process_created"] = observation.process_created
        surface_payloads.append(payload)

    return HostCapabilitySnapshot(
        schema_version=CAPABILITY_SCHEMA_VERSION,
        environment_state=environment_state,
        filesystem_state=filesystem_state,
        package_state="unknown",
        runtime_state="unverified",
        next_action=next_action,
        reason_code=reason_code,
        retry_allowed=retry_allowed,
        retry_budget_remaining=retry_budget_remaining,
        canonical_resume_entrypoint=canonical_resume_entrypoint,
        surfaces=tuple(surface_payloads),
    )
