from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from latka_jazn.core.chatgpt_host_executor_contract import (
    HostCapabilitySnapshot,
    HostEnvironmentState,
    HostExecutorObservation,
    HostFilesystemState,
    HostRecoveryAction,
    aggregate_host_executor_observations,
)
from latka_jazn.packaging.attachment_materialization import (
    AttachmentMaterializationReport,
    AttachmentMaterializationState,
)
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("chatgpt_host_preflight")


class HostPackageMaterializationState(str, Enum):
    UNKNOWN = "unknown"
    MATERIALIZING = "materializing"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    READY = "ready"


@dataclass(frozen=True)
class ChatGptHostPreflightDecision:
    schema_version: str
    environment_state: HostEnvironmentState
    filesystem_state: HostFilesystemState
    package_state: HostPackageMaterializationState
    runtime_state: str
    bootstrap_allowed: bool
    next_action: HostRecoveryAction
    reason_code: str
    canonical_resume_entrypoint: str | None
    capability_snapshot: HostCapabilitySnapshot
    attachments: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "environment_state": self.environment_state.value,
            "filesystem_state": self.filesystem_state.value,
            "package_state": self.package_state.value,
            "runtime_state": self.runtime_state,
            "bootstrap_allowed": self.bootstrap_allowed,
            "next_action": self.next_action.value,
            "reason_code": self.reason_code,
            "canonical_resume_entrypoint": self.canonical_resume_entrypoint,
            "capability_snapshot": self.capability_snapshot.to_dict(),
            "attachments": [dict(item) for item in self.attachments],
        }


def _aggregate_attachment_state(
    reports: tuple[AttachmentMaterializationReport, ...],
) -> HostPackageMaterializationState:
    if not reports:
        return HostPackageMaterializationState.UNKNOWN
    states = {report.state for report in reports}
    if states == {AttachmentMaterializationState.READY}:
        return HostPackageMaterializationState.READY
    if AttachmentMaterializationState.MATERIALIZING in states:
        return HostPackageMaterializationState.MATERIALIZING
    if states & {
        AttachmentMaterializationState.MISSING,
        AttachmentMaterializationState.INCOMPLETE,
    }:
        return HostPackageMaterializationState.INCOMPLETE
    if states & {
        AttachmentMaterializationState.SIZE_MISMATCH,
        AttachmentMaterializationState.HASH_MISMATCH,
    }:
        return HostPackageMaterializationState.INVALID
    return HostPackageMaterializationState.UNKNOWN


def plan_chatgpt_host_preflight(
    executor_observations: Iterable[HostExecutorObservation],
    *,
    attachment_reports: Iterable[AttachmentMaterializationReport] = (),
    package_required: bool = False,
) -> ChatGptHostPreflightDecision:
    """Compose executor and attachment truth without crossing evidence boundaries.

    Host execution capability and attachment readiness are deliberately
    independent.  A broken ``python_tool`` bridge can yield a degraded but
    usable environment when a terminal succeeds.  Conversely, an observed
    filesystem does not make a still-growing or hash-invalid package safe to
    bootstrap.
    """

    capability = aggregate_host_executor_observations(executor_observations)
    reports = tuple(attachment_reports)
    package_state = _aggregate_attachment_state(reports)

    execution_usable = capability.environment_state in {
        HostEnvironmentState.AVAILABLE,
        HostEnvironmentState.DEGRADED,
    }
    filesystem_observed = capability.filesystem_state is HostFilesystemState.OBSERVED
    package_ready = package_state is HostPackageMaterializationState.READY
    package_gate_ok = package_ready if package_required else package_state not in {
        HostPackageMaterializationState.MATERIALIZING,
        HostPackageMaterializationState.INCOMPLETE,
        HostPackageMaterializationState.INVALID,
    }

    if capability.next_action is HostRecoveryAction.PROBE_ALTERNATIVE_ONCE:
        bootstrap_allowed = False
        next_action = HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
        reason_code = "executor_alternative_probe_pending"
        resume = None
    elif not execution_usable:
        bootstrap_allowed = False
        next_action = capability.next_action
        reason_code = "no_usable_execution_surface"
        resume = None
    elif not filesystem_observed:
        bootstrap_allowed = False
        next_action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
        reason_code = "filesystem_not_observed_yet"
        resume = "run.py"
    elif package_required and package_state is HostPackageMaterializationState.UNKNOWN:
        bootstrap_allowed = False
        next_action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
        reason_code = "required_package_not_observed"
        resume = "run.py"
    elif not package_gate_ok:
        bootstrap_allowed = False
        next_action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
        reason_code = f"attachment_package_{package_state.value}"
        resume = "run.py"
    else:
        bootstrap_allowed = True
        next_action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
        reason_code = (
            "host_degraded_package_ready"
            if capability.environment_state is HostEnvironmentState.DEGRADED
            else "host_preflight_ready"
        )
        resume = "run.py"

    return ChatGptHostPreflightDecision(
        schema_version=SCHEMA_VERSION,
        environment_state=capability.environment_state,
        filesystem_state=capability.filesystem_state,
        package_state=package_state,
        runtime_state="unverified",
        bootstrap_allowed=bootstrap_allowed,
        next_action=next_action,
        reason_code=reason_code,
        canonical_resume_entrypoint=resume,
        capability_snapshot=capability,
        attachments=tuple(report.to_dict() for report in reports),
    )
