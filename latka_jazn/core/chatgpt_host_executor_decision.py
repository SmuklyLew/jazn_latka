from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from latka_jazn.core.chatgpt_host_executor_enums import (
    HostCommandState,
    HostExecutionRoute,
    HostExecutorState,
    HostFilesystemState,
    HostRecoveryAction,
)
from latka_jazn.core.chatgpt_host_handoff_state import HostHandoffState


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
    execution_handoff_state: HostHandoffState = HostHandoffState.UNKNOWN

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
            "execution_handoff_state": self.execution_handoff_state.value,
        }
