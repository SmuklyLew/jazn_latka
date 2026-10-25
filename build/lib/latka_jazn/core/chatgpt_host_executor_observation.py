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
_BLOCKER_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HOST_ERROR_TEXT_LIMIT = 1024
_HOST_ERROR_ID_LIMIT = 256
_HOST_PATH_TEXT_LIMIT = 1024
_HOST_ERROR_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie)\s*:\s*[^\r\n]+"
        ),
        r"\1: [REDACTED]",
    ),
    (
        re.compile(
            r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
            r"client[_ -]?secret|password|secret|token)\b\s*[:=]\s*"
            r"[\"']?[^\s,\"';]+"
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
        "Bearer [REDACTED]",
    ),
    (
        re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
        "[REDACTED_OPENAI_KEY]",
    ),
)


def _safe_optional_text(
    value: object,
    *,
    limit: int,
    redact_secrets: bool = False,
) -> str | None:
    raw = str(value or "")
    if redact_secrets:
        for pattern, replacement in _HOST_ERROR_REDACTIONS:
            raw = pattern.sub(replacement, raw)
    normalized = " ".join(raw.split())
    return normalized[:limit] or None


def _normalized_blockers(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip().lower()
        if not value:
            continue
        if not _BLOCKER_RE.fullmatch(value):
            raise ValueError(f"invalid_remote_runtime_blocker:{raw!r}")
        if value not in result:
            result.append(value)
    return tuple(result)


def _normalized_surface(value: str) -> str:
    surface = str(value or "").strip().lower()
    if not _SURFACE_RE.fullmatch(surface):
        raise ValueError(f"invalid_executor_surface:{value!r}")
    return surface


def _normalized_phase(value: object) -> str | None:
    phase = str(value or "").strip().lower()
    if not phase:
        return None
    if not _BLOCKER_RE.fullmatch(phase):
        raise ValueError(f"invalid_spawn_phase:{value!r}")
    return phase


def _normalized_sha256(value: object) -> str | None:
    digest = str(value or "").strip().lower()
    if not digest:
        return None
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError("command_fingerprint_sha256_must_be_64_hex")
    return digest


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
    error_code: str | None = None
    error_message: str | None = None
    host_request_id: str | None = None
    observed_at_utc: str | None = None
    remote_runtime_blockers: tuple[str, ...] = ()

    # Optional host evidence. These fields describe what the host actually
    # observed; absence remains unknown and must not be coerced to false.
    spawn_phase: str | None = None
    intended_cwd: str | None = None
    command_fingerprint_sha256: str | None = None
    executor_allocation_state: bool | None = None
    materialization_state: bool | None = None
    mount_preparation_state: bool | None = None

    # Post-spawn evidence. These values are invalid when process_created=False.
    pid: int | None = None
    observed_cwd: str | None = None
    platform: str | None = None
    effective_uid: int | None = None
    effective_gid: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "surface", _normalized_surface(self.surface))
        object.__setattr__(
            self,
            "error_code",
            _safe_optional_text(self.error_code, limit=_HOST_ERROR_ID_LIMIT),
        )
        object.__setattr__(
            self,
            "error_message",
            _safe_optional_text(
                self.error_message,
                limit=_HOST_ERROR_TEXT_LIMIT,
                redact_secrets=True,
            ),
        )
        object.__setattr__(
            self,
            "host_request_id",
            _safe_optional_text(self.host_request_id, limit=_HOST_ERROR_ID_LIMIT),
        )
        object.__setattr__(
            self,
            "observed_at_utc",
            _safe_optional_text(self.observed_at_utc, limit=_HOST_ERROR_ID_LIMIT),
        )
        object.__setattr__(self, "spawn_phase", _normalized_phase(self.spawn_phase))
        object.__setattr__(
            self,
            "intended_cwd",
            _safe_optional_text(self.intended_cwd, limit=_HOST_PATH_TEXT_LIMIT),
        )
        object.__setattr__(
            self,
            "command_fingerprint_sha256",
            _normalized_sha256(self.command_fingerprint_sha256),
        )
        object.__setattr__(
            self,
            "observed_cwd",
            _safe_optional_text(self.observed_cwd, limit=_HOST_PATH_TEXT_LIMIT),
        )
        object.__setattr__(
            self,
            "platform",
            _safe_optional_text(self.platform, limit=_HOST_ERROR_ID_LIMIT),
        )

        blockers = _normalized_blockers(self.remote_runtime_blockers)
        object.__setattr__(self, "remote_runtime_blockers", blockers)
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
            "registered_mcp_app",
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
        if self.remote_runtime_transport_available and blockers:
            raise ValueError(
                "remote_runtime_transport_available_conflicts_with_blocking_checks"
            )

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

        if self.pid is not None:
            if not self.process_created:
                raise ValueError("pid_requires_process_created")
            if self.pid <= 0:
                raise ValueError("pid_must_be_positive")
        if self.observed_cwd is not None and not self.process_created:
            raise ValueError("observed_cwd_requires_process_created")
        if self.platform is not None and not self.process_created:
            raise ValueError("platform_requires_process_created")
        for field_name, value in (
            ("effective_uid", self.effective_uid),
            ("effective_gid", self.effective_gid),
        ):
            if value is not None:
                if not self.process_created:
                    raise ValueError(f"{field_name}_requires_process_created")
                if value < 0:
                    raise ValueError(f"{field_name}_must_be_non_negative")
