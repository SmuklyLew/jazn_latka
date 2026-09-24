from __future__ import annotations

from dataclasses import dataclass
import re

from latka_jazn.core.chatgpt_host_handoff_state import (
    HANDOFF_ACTIVE_STATES,
    HostHandoffState,
    normalize_handoff_state,
)


MAX_ALTERNATIVE_EXECUTOR_PROBES = 1
_SURFACE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


def _normalized_surface(value: str) -> str:
    surface = str(value or "").strip().lower()
    if not _SURFACE_RE.fullmatch(surface):
        raise ValueError(f"invalid_executor_surface:{value!r}")
    return surface


@dataclass(frozen=True)
class HostExecutorObservation:
    process_created: bool
    command_completed: bool = False
    returncode: int | None = None
    error_class: str | None = None
    alternative_surface_available: bool = False
    alternative_probe_count: int = 0
    filesystem_probe_succeeded: bool | None = None
    surface: str = "default"
    remote_runtime_transport_available: bool = False
    remote_runtime_transport: str = "none"
    remote_runtime_reason_code: str | None = None
    execution_handoff_available: bool = False
    execution_handoff_state: HostHandoffState = HostHandoffState.UNKNOWN
    observation_generation: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "surface", _normalized_surface(self.surface))
        state = normalize_handoff_state(self.execution_handoff_state)
        if state is HostHandoffState.UNKNOWN and self.execution_handoff_available:
            state = HostHandoffState.AVAILABLE
        elif state is HostHandoffState.UNAVAILABLE and self.execution_handoff_available:
            raise ValueError("execution_handoff_unavailable_conflicts_with_available")
        elif state in HANDOFF_ACTIVE_STATES:
            object.__setattr__(self, "execution_handoff_available", True)
        object.__setattr__(self, "execution_handoff_state", state)

        remote_transport = str(self.remote_runtime_transport or "none").strip().lower()
        allowed_remote_transports = {
            "none",
            "public_streamable_http",
            "openai_secure_mcp_tunnel",
            "verified_remote_unspecified",
        }
        if remote_transport not in allowed_remote_transports:
            raise ValueError(f"invalid_remote_runtime_transport:{remote_transport!r}")
        if self.remote_runtime_transport_available and remote_transport == "none":
            # Direct in-process callers from older code already mean "verified"
            # when setting the boolean. Preserve compatibility while making the
            # untrusted JSON parser require concrete evidence and a transport.
            remote_transport = "verified_remote_unspecified"
        object.__setattr__(self, "remote_runtime_transport", remote_transport)
        reason = str(self.remote_runtime_reason_code or "").strip() or None
        object.__setattr__(self, "remote_runtime_reason_code", reason)

        if self.alternative_probe_count < 0:
            raise ValueError("alternative_probe_count_must_be_non_negative")
        if self.observation_generation < 0:
            raise ValueError("observation_generation_must_be_non_negative")
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
