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
    REMOTE_CAPABLE = "remote_capable"
    HANDOFF_REQUIRED = "handoff_required"
    UNAVAILABLE = "unavailable"


class HostCommandState(str, Enum):
    NOT_STARTED = "not_started"
    STARTED_UNFINISHED = "started_unfinished"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class HostFilesystemState(str, Enum):
    UNKNOWN = "unknown"
    OBSERVED = "observed"


class HostExecutionRoute(str, Enum):
    NONE = "none"
    LOCAL_EXECUTOR = "local_executor"
    REMOTE_RUNTIME = "remote_runtime"
    HOST_HANDOFF = "host_handoff"


class HostRecoveryAction(str, Enum):
    PROBE_ALTERNATIVE_ONCE = "probe_alternative_once"
    STOP_LOCAL_BOOTSTRAP = "stop_local_bootstrap"
    RESUME_CANONICAL_DISCOVERY = "resume_canonical_discovery"
    DIAGNOSE_LOCAL_COMMAND = "diagnose_local_command"
    USE_REMOTE_RUNTIME_TRANSPORT = "use_remote_runtime_transport"
    REQUEST_EXECUTION_HANDOFF = "request_execution_handoff"


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
    surfaces.

    ``remote_runtime_transport_available`` and ``execution_handoff_available``
    are host-declared topology capabilities. They do not turn a failed local
    executor into an available executor and do not prove that a runtime is
    active. They only select the next safe route when local bootstrap cannot
    start on this host surface.
    """

    process_created: bool
    command_completed: bool = False
    returncode: int | None = None
    error_class: str | None = None
    alternative_surface_available: bool = False
    alternative_probe_count: int = 0
    filesystem_probe_succeeded: bool | None = None
    surface: str = "default"
    remote_runtime_transport_available: bool = False
    execution_handoff_available: bool = False

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
    execution_route: HostExecutionRoute
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
            "execution_route": self.execution_route.value,
            "reason_code": self.reason_code,
            "retry_allowed": self.retry_allowed,
            "retry_budget_remaining": self.retry_budget_remaining,
            "canonical_resume_entrypoint": self.canonical_resume_entrypoint,
        }


@dataclass(frozen=True)
class HostCapabilitySnapshot:
    """Aggregate independently observed local surfaces and host-declared routes."""

    schema_version: str
    environment_state: HostEnvironmentState
    filesystem_state: HostFilesystemState
    package_state: str
    runtime_state: str
    next_action: HostRecoveryAction
    execution_route: HostExecutionRoute
    reason_code: str
    retry_allowed: bool
    retry_budget_remaining: int
    canonical_resume_entrypoint: str | None
    remote_runtime_transport_available: bool
    execution_handoff_available: bool
    surfaces: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "environment_state": self.environment_state.value,
            "filesystem_state": self.filesystem_state.value,
            "package_state": self.package_state,
            "runtime_state": self.runtime_state,
            "next_action": self.next_action.value,
            "execution_route": self.execution_route.value,
            "reason_code": self.reason_code,
            "retry_allowed": self.retry_allowed,
            "retry_budget_remaining": self.retry_budget_remaining,
            "canonical_resume_entrypoint": self.canonical_resume_entrypoint,
            "remote_runtime_transport_available": self.remote_runtime_transport_available,
            "execution_handoff_available": self.execution_handoff_available,
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
                execution_route=HostExecutionRoute.NONE,
                reason_code="insufficient_executor_observation",
                retry_allowed=False,
                retry_budget_remaining=0,
                canonical_resume_entrypoint=None,
            )

        if observation.remote_runtime_transport_available:
            return HostExecutorRecoveryDecision(
                schema_version=SCHEMA_VERSION,
                executor_state=HostExecutorState.HOST_EXECUTOR_UNAVAILABLE,
                command_state=HostCommandState.NOT_STARTED,
                filesystem_state=HostFilesystemState.UNKNOWN,
                package_state="unknown",
                runtime_state="unverified",
                next_action=HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT,
                execution_route=HostExecutionRoute.REMOTE_RUNTIME,
                reason_code="local_executor_unavailable_remote_runtime_route_available",
                retry_allowed=False,
                retry_budget_remaining=0,
                canonical_resume_entrypoint=None,
            )

        if observation.execution_handoff_available:
            return HostExecutorRecoveryDecision(
                schema_version=SCHEMA_VERSION,
                executor_state=HostExecutorState.HOST_EXECUTOR_UNAVAILABLE,
                command_state=HostCommandState.NOT_STARTED,
                filesystem_state=HostFilesystemState.UNKNOWN,
                package_state="unknown",
                runtime_state="unverified",
                next_action=HostRecoveryAction.REQUEST_EXECUTION_HANDOFF,
                execution_route=HostExecutionRoute.HOST_HANDOFF,
                reason_code="local_executor_unavailable_execution_handoff_available",
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
            execution_route=HostExecutionRoute.NONE,
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
            execution_route=HostExecutionRoute.LOCAL_EXECUTOR,
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
            execution_route=HostExecutionRoute.LOCAL_EXECUTOR,
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
        execution_route=HostExecutionRoute.LOCAL_EXECUTOR,
        reason_code="executor_preflight_succeeded",
        retry_allowed=False,
        retry_budget_remaining=0,
        canonical_resume_entrypoint="run.py",
    )


def aggregate_host_executor_observations(
    observations: Iterable[HostExecutorObservation],
) -> HostCapabilitySnapshot:
    """Aggregate bounded observations without conflating independent routes."""

    items = tuple(observations)
    if not items:
        return HostCapabilitySnapshot(
            schema_version=CAPABILITY_SCHEMA_VERSION,
            environment_state=HostEnvironmentState.UNKNOWN,
            filesystem_state=HostFilesystemState.UNKNOWN,
            package_state="unknown",
            runtime_state="unverified",
            next_action=HostRecoveryAction.STOP_LOCAL_BOOTSTRAP,
            execution_route=HostExecutionRoute.NONE,
            reason_code="no_executor_observations",
            retry_allowed=False,
            retry_budget_remaining=0,
            canonical_resume_entrypoint=None,
            remote_runtime_transport_available=False,
            execution_handoff_available=False,
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
    remote_runtime_transport_available = any(
        item.remote_runtime_transport_available for item in items
    )
    execution_handoff_available = any(item.execution_handoff_available for item in items)

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
        execution_route = HostExecutionRoute.LOCAL_EXECUTOR
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
        else:
            next_action = HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
            canonical_resume_entrypoint = None
            reason_code = "available_surface_without_recovery_action"
        retry_allowed = False
        retry_budget_remaining = 0
    elif remote_runtime_transport_available:
        environment_state = HostEnvironmentState.REMOTE_CAPABLE
        execution_route = HostExecutionRoute.REMOTE_RUNTIME
        next_action = HostRecoveryAction.USE_REMOTE_RUNTIME_TRANSPORT
        canonical_resume_entrypoint = None
        reason_code = "local_executor_unavailable_remote_runtime_route_available"
        retry_allowed = False
        retry_budget_remaining = 0
    elif execution_handoff_available:
        environment_state = HostEnvironmentState.HANDOFF_REQUIRED
        execution_route = HostExecutionRoute.HOST_HANDOFF
        next_action = HostRecoveryAction.REQUEST_EXECUTION_HANDOFF
        canonical_resume_entrypoint = None
        reason_code = "local_executor_unavailable_execution_handoff_available"
        retry_allowed = False
        retry_budget_remaining = 0
    elif retry_decisions:
        environment_state = HostEnvironmentState.UNKNOWN
        execution_route = HostExecutionRoute.NONE
        next_action = HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
        canonical_resume_entrypoint = None
        reason_code = "observed_surface_failed_alternative_probe_pending"
        retry_allowed = True
        retry_budget_remaining = max(pair[1].retry_budget_remaining for pair in retry_decisions)
    elif failed and not unknown:
        environment_state = HostEnvironmentState.UNAVAILABLE
        execution_route = HostExecutionRoute.NONE
        next_action = HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
        canonical_resume_entrypoint = None
        reason_code = "all_observed_executor_surfaces_unavailable"
        retry_allowed = False
        retry_budget_remaining = 0
    else:
        environment_state = HostEnvironmentState.UNKNOWN
        execution_route = HostExecutionRoute.NONE
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
        payload["remote_runtime_transport_available"] = observation.remote_runtime_transport_available
        payload["execution_handoff_available"] = observation.execution_handoff_available
        surface_payloads.append(payload)

    return HostCapabilitySnapshot(
        schema_version=CAPABILITY_SCHEMA_VERSION,
        environment_state=environment_state,
        filesystem_state=filesystem_state,
        package_state="unknown",
        runtime_state="unverified",
        next_action=next_action,
        execution_route=execution_route,
        reason_code=reason_code,
        retry_allowed=retry_allowed,
        retry_budget_remaining=retry_budget_remaining,
        canonical_resume_entrypoint=canonical_resume_entrypoint,
        remote_runtime_transport_available=remote_runtime_transport_available,
        execution_handoff_available=execution_handoff_available,
        surfaces=tuple(surface_payloads),
    )
