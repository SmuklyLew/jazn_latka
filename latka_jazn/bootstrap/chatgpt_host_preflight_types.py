from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from latka_jazn.core.chatgpt_host_capability_snapshot import HostCapabilitySnapshot
from latka_jazn.core.chatgpt_host_executor_enums import (
    HostEnvironmentState,
    HostExecutionRoute,
    HostFilesystemState,
    HostRecoveryAction,
)
from latka_jazn.core.chatgpt_host_handoff_state import HostHandoffState


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
    remote_runtime_allowed: bool
    handoff_required: bool
    next_action: HostRecoveryAction
    execution_route: HostExecutionRoute
    reason_code: str
    canonical_resume_entrypoint: str | None
    capability_snapshot: HostCapabilitySnapshot
    attachments: tuple[dict[str, Any], ...]
    handoff_state: HostHandoffState = HostHandoffState.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "environment_state": self.environment_state.value,
            "filesystem_state": self.filesystem_state.value,
            "package_state": self.package_state.value,
            "runtime_state": self.runtime_state,
            "bootstrap_allowed": self.bootstrap_allowed,
            "local_bootstrap_allowed": self.bootstrap_allowed,
            "remote_runtime_allowed": self.remote_runtime_allowed,
            "handoff_required": self.handoff_required,
            "handoff_state": self.handoff_state.value,
            "next_action": self.next_action.value,
            "execution_route": self.execution_route.value,
            "reason_code": self.reason_code,
            "canonical_resume_entrypoint": self.canonical_resume_entrypoint,
            "capability_snapshot": self.capability_snapshot.to_dict(),
            "attachments": [dict(item) for item in self.attachments],
        }
