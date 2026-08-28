from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon import (
    DEFAULT_DAEMON_HOST,
    DEFAULT_DAEMON_PORT,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_START_TIMEOUT_SECONDS,
    DAEMON_SCHEMA_VERSION,
    start_daemon,
    status_daemon,
)
from latka_jazn.version import schema_version

AUTOSTART_ENV = "JAZN_DAEMON_AUTOSTART"
FORCE_ENSURE_ENV = "JAZN_ENSURE_DAEMON"
AUTOSTART_COMMANDS_ENV = "JAZN_DAEMON_AUTOSTART_COMMANDS"

ACTIVE_STATES = {"active_trusted", "active_degraded"}
ACTIVE_TRUSTED = "active_trusted"
ACTIVE_DEGRADED = "active_degraded"

# `active_degraded` is not a single liveness state. Some degradations concern
# trusted time only while others explicitly mean that endpoint/heartbeat
# liveness is not confirmed. Conversation autostart must therefore fail closed
# unless the degraded state came from a fully confirmed endpoint identity.
DEGRADED_TURN_SAFE_REASONS = {
    "endpoint_runtime_identity_confirmed",
}
DEGRADED_TURN_BLOCKING_REASONS = {
    "endpoint_identity_confirmed_heartbeat_stale",
    "fresh_marker_and_live_pid_endpoint_unreachable",
}

RUNTIME_TURN_COMMANDS = {
    "--chat",
    "--chat-gpt",
    "--chat-gpt-final-only",
    "--chat-open-ai",
    "--chat-openai",
    "--chat-ollama",
    "--ollama",
    "--local-llm",
    "--daemon-send",
    "--daemon-submit",
    "direct_message",
}

# ChatGPT has an explicit, verified one-shot runtime path in AGENTS.chatgpt.md.
# The host should reuse a live daemon when one already exists, but inability to
# create a background process must not block the canonical one-shot bridge.
# Explicit --ensure-daemon / JAZN_ENSURE_DAEMON still override this default and
# remain fail-closed through the normal policy order below.
VERIFIED_ONE_SHOT_FALLBACK_COMMANDS = {
    "--chat-gpt",
    "--chat-gpt-final-only",
}

NEVER_AUTOSTART_COMMANDS = {
    "--daemon-status",
    "--daemon-stop",
    "--daemon-run",
    "--daemon-start",
}

OBSERVATIONAL_COMMANDS = {
    "--startup-status",
    "--startup-status-fast",
    "--startup-status-deep",
    "--status-json",
    "--active-cache-status",
    "--llm-route-status",
    "--model-adapter-status",
    "--daemon-result",
}


@dataclass(slots=True)
class DaemonAutostartDecision:
    command: str | None
    should_ensure: bool
    reason: str
    explicit_ensure: bool = False
    disabled_for_turn: bool = False
    env_autostart: bool = True
    env_force: bool = False
    command_known_runtime_turn: bool = False
    command_observational: bool = False
    command_forbidden: bool = False
    schema_version: str = schema_version("daemon_autostart_decision")
    truth_boundary: str = (
        "Autostart daemonu dotyczy tylko tras rozmowy/runtime turn. "
        "Status, stop i foreground run pozostają komendami obserwacyjnymi/kontrolnymi i nie uruchamiają daemonu przypadkiem."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DaemonEnsureResult:
    ok: bool
    ensured: bool
    active_state: str
    reason: str
    decision: dict[str, Any]
    status_before: dict[str, Any] | None = None
    startup: dict[str, Any] | None = None
    status_after: dict[str, Any] | None = None
    selected_transport: str = "host_diagnostic"
    fallback_reason: str = "transport_not_classified"
    requested_runtime_root: str | None = None
    resolved_active_root: str | None = None
    daemon_endpoint_root: str | None = None
    daemon_identity_verified: bool = False
    daemon_reused: bool = False
    daemon_started: bool = False
    one_shot_allowed: bool = False
    one_shot_verified: bool = False
    schema_version: str = schema_version("daemon_ensure_result")
    truth_boundary: str = (
        "ensure_daemon_for_runtime_turn może uruchomić daemon tylko dla trasy rozmowy albo jawnego --ensure-daemon. "
        "Sukces oznacza aktywny trusted runtime albo bezpiecznie zdegradowany runtime z potwierdzonym markerem, PID-em, endpointem i świeżym heartbeat według status_daemon."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def transport_observability(self) -> dict[str, Any]:
        return {
            "selected_transport": self.selected_transport,
            "fallback_reason": self.fallback_reason,
            "requested_runtime_root": self.requested_runtime_root,
            "resolved_active_root": self.resolved_active_root,
            "daemon_endpoint_root": self.daemon_endpoint_root,
            "daemon_identity_verified": self.daemon_identity_verified,
            "daemon_reused": self.daemon_reused,
            "daemon_started": self.daemon_started,
            "one_shot_allowed": self.one_shot_allowed,
            "one_shot_verified": self.one_shot_verified,
        }


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "tak", "on"}


def _falsey(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"0", "false", "no", "nie", "off"}


def _command_set_from_env(env: Mapping[str, str]) -> set[str] | None:
    raw = str(env.get(AUTOSTART_COMMANDS_ENV, "")).strip()
    if not raw:
        return None
    values = {item.strip() for item in raw.replace(";", ",").split(",") if item.strip()}
    return values or None


def _status_active_state(status: Mapping[str, Any] | None) -> str:
    if not isinstance(status, Mapping):
        return "inactive"
    return str(status.get("active_state") or status.get("runtime_active_state") or "inactive")


def _status_active_reason(status: Mapping[str, Any] | None) -> str:
    if not isinstance(status, Mapping):
        return ""
    return str(status.get("active_state_reason") or "").strip()


def _resolved_subject_config(
    config: JaznConfig,
    status: Mapping[str, Any],
) -> JaznConfig | None:
    if status.get("marker_found") is True and status.get("marker_valid") is not True:
        return None
    raw_root = status.get("resolved_active_root") or status.get("subject_runtime_root")
    if raw_root in (None, ""):
        raw_root = config.root
    try:
        candidate = Path(str(raw_root)).expanduser()
        if not candidate.is_absolute():
            return None
        subject_root = candidate.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return replace(config, root=subject_root)


def _transport_roots(
    config: JaznConfig,
    status: Mapping[str, Any],
) -> tuple[str, str, str | None]:
    requested = str(status.get("requested_runtime_root") or Path(config.root).resolve())
    resolved = str(
        status.get("resolved_active_root")
        or status.get("subject_runtime_root")
        or Path(config.root).resolve()
    )
    endpoint = status.get("endpoint_reported_active_root")
    return requested, resolved, str(endpoint) if endpoint not in (None, "") else None


def _fallback_truth_boundary_failure(status: Mapping[str, Any]) -> str | None:
    reason = _status_active_reason(status)
    if status.get("marker_found") is True and status.get("marker_valid") is not True:
        return "ambiguous_subject_root"
    if reason.startswith("active_marker_") or reason.startswith("marker_"):
        return "ambiguous_subject_root"
    if reason == "endpoint_runtime_root_mismatch":
        return "daemon_identity_root_mismatch"
    if reason == "endpoint_pid_mismatch":
        return "daemon_identity_pid_mismatch"
    if reason == "package_integrity_verification_failed":
        return "runtime_integrity_failure"
    if reason == "source_provenance_not_verified":
        return "runtime_provenance_failure"
    if reason in DEGRADED_TURN_BLOCKING_REASONS:
        return (
            "daemon_heartbeat_stale"
            if reason == "endpoint_identity_confirmed_heartbeat_stale"
            else "daemon_endpoint_unreachable_with_live_process"
        )
    return None


def status_allows_runtime_turn(status: Mapping[str, Any] | None, *, allow_degraded: bool = True) -> bool:
    active_state = _status_active_state(status)
    if active_state == ACTIVE_TRUSTED:
        return True
    if active_state != ACTIVE_DEGRADED or not allow_degraded:
        return False

    reason = _status_active_reason(status)
    if reason in DEGRADED_TURN_BLOCKING_REASONS:
        return False
    # Fail closed for unknown/missing degraded reasons. The only currently safe
    # degraded state is one where endpoint identity and heartbeat are confirmed
    # and the degradation comes from the timestamp trust path.
    return reason in DEGRADED_TURN_SAFE_REASONS


def daemon_autostart_decision(
    command: str | None,
    *,
    explicit_ensure: bool = False,
    disabled_for_turn: bool = False,
    env: Mapping[str, str] | None = None,
) -> DaemonAutostartDecision:
    env_map: Mapping[str, str] = env or {}
    command_norm = str(command or "").strip() or None
    env_autostart = not _falsey(env_map.get(AUTOSTART_ENV))
    env_force = _truthy(env_map.get(FORCE_ENSURE_ENV), default=False)
    command_set = _command_set_from_env(env_map)
    command_forbidden = bool(command_norm in NEVER_AUTOSTART_COMMANDS)
    command_observational = bool(command_norm in OBSERVATIONAL_COMMANDS)
    command_known_runtime_turn = bool(command_norm in RUNTIME_TURN_COMMANDS)

    if disabled_for_turn:
        return DaemonAutostartDecision(
            command=command_norm,
            should_ensure=False,
            reason="disabled_by_cli_no_ensure_daemon",
            explicit_ensure=explicit_ensure,
            disabled_for_turn=True,
            env_autostart=env_autostart,
            env_force=env_force,
            command_known_runtime_turn=command_known_runtime_turn,
            command_observational=command_observational,
            command_forbidden=command_forbidden,
        )
    if command_forbidden:
        return DaemonAutostartDecision(
            command=command_norm,
            should_ensure=False,
            reason="command_must_not_autostart_daemon",
            explicit_ensure=explicit_ensure,
            env_autostart=env_autostart,
            env_force=env_force,
            command_known_runtime_turn=command_known_runtime_turn,
            command_observational=command_observational,
            command_forbidden=True,
        )
    if explicit_ensure or env_force:
        return DaemonAutostartDecision(
            command=command_norm,
            should_ensure=True,
            reason="explicit_ensure_daemon" if explicit_ensure else "env_JAZN_ENSURE_DAEMON",
            explicit_ensure=explicit_ensure,
            env_autostart=env_autostart,
            env_force=env_force,
            command_known_runtime_turn=command_known_runtime_turn,
            command_observational=command_observational,
            command_forbidden=False,
        )
    if command_observational:
        return DaemonAutostartDecision(
            command=command_norm,
            should_ensure=False,
            reason="observational_command_does_not_autostart",
            env_autostart=env_autostart,
            env_force=env_force,
            command_known_runtime_turn=command_known_runtime_turn,
            command_observational=True,
        )
    if not env_autostart:
        return DaemonAutostartDecision(
            command=command_norm,
            should_ensure=False,
            reason="env_JAZN_DAEMON_AUTOSTART_disabled",
            env_autostart=False,
            env_force=env_force,
            command_known_runtime_turn=command_known_runtime_turn,
            command_observational=command_observational,
        )
    if command_set is not None and command_norm not in command_set:
        return DaemonAutostartDecision(
            command=command_norm,
            should_ensure=False,
            reason="command_not_in_JAZN_DAEMON_AUTOSTART_COMMANDS",
            env_autostart=env_autostart,
            env_force=env_force,
            command_known_runtime_turn=command_known_runtime_turn,
            command_observational=command_observational,
        )
    if command_norm in VERIFIED_ONE_SHOT_FALLBACK_COMMANDS:
        return DaemonAutostartDecision(
            command=command_norm,
            should_ensure=False,
            reason="verified_one_shot_fallback_allowed",
            env_autostart=env_autostart,
            env_force=env_force,
            command_known_runtime_turn=command_known_runtime_turn,
            command_observational=command_observational,
        )
    return DaemonAutostartDecision(
        command=command_norm,
        should_ensure=command_known_runtime_turn,
        reason="runtime_turn_requires_daemon" if command_known_runtime_turn else "command_not_runtime_turn",
        env_autostart=env_autostart,
        env_force=env_force,
        command_known_runtime_turn=command_known_runtime_turn,
        command_observational=command_observational,
    )


def ensure_daemon_for_runtime_turn(
    config: JaznConfig,
    *,
    command: str | None,
    host: str = DEFAULT_DAEMON_HOST,
    port: int = DEFAULT_DAEMON_PORT,
    marker_output: Path | None = None,
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    startup_timeout: float = DEFAULT_START_TIMEOUT_SECONDS,
    explicit_ensure: bool = False,
    disabled_for_turn: bool = False,
    env: Mapping[str, str] | None = None,
    allow_degraded: bool = True,
) -> DaemonEnsureResult:
    env_map = env if env is not None else __import__("os").environ
    decision = daemon_autostart_decision(
        command,
        explicit_ensure=explicit_ensure,
        disabled_for_turn=disabled_for_turn,
        env=env_map,
    )
    status_before = status_daemon(config, host=host, port=port, marker_output=marker_output)
    before_state = _status_active_state(status_before)
    requested_root, resolved_root, endpoint_root = _transport_roots(config, status_before)
    if status_allows_runtime_turn(status_before, allow_degraded=allow_degraded):
        return DaemonEnsureResult(
            ok=True,
            ensured=True,
            active_state=before_state,
            reason="daemon_already_active",
            decision=decision.to_dict(),
            status_before=status_before,
            status_after=status_before,
            selected_transport="persistent_daemon",
            fallback_reason="daemon_reused",
            requested_runtime_root=requested_root,
            resolved_active_root=resolved_root,
            daemon_endpoint_root=endpoint_root,
            daemon_identity_verified=bool(status_before.get("endpoint_identity_matches")),
            daemon_reused=True,
        )
    if not decision.should_ensure:
        boundary_failure = _fallback_truth_boundary_failure(status_before)
        one_shot_allowed = bool(
            decision.command in VERIFIED_ONE_SHOT_FALLBACK_COMMANDS
            and boundary_failure is None
        )
        return DaemonEnsureResult(
            ok=False,
            ensured=False,
            active_state=before_state,
            reason=boundary_failure or decision.reason,
            decision=decision.to_dict(),
            status_before=status_before,
            status_after=status_before,
            selected_transport=(
                "verified_one_shot_fallback"
                if one_shot_allowed
                else "host_diagnostic"
            ),
            fallback_reason=(boundary_failure or decision.reason),
            requested_runtime_root=requested_root,
            resolved_active_root=resolved_root,
            daemon_endpoint_root=endpoint_root,
            daemon_identity_verified=False,
            one_shot_allowed=one_shot_allowed,
        )
    subject_config = _resolved_subject_config(config, status_before)
    if subject_config is None:
        return DaemonEnsureResult(
            ok=False,
            ensured=False,
            active_state=before_state,
            reason="ambiguous_subject_root",
            decision=decision.to_dict(),
            status_before=status_before,
            status_after=status_before,
            selected_transport="host_diagnostic",
            fallback_reason="ambiguous_subject_root",
            requested_runtime_root=requested_root,
            resolved_active_root=resolved_root,
            daemon_endpoint_root=endpoint_root,
        )
    startup = start_daemon(
        subject_config,
        host=host,
        port=port,
        marker_output=marker_output,
        heartbeat_interval=heartbeat_interval,
        startup_timeout=startup_timeout,
    )
    status_after = status_daemon(config, host=host, port=port, marker_output=marker_output)
    after_state = _status_active_state(status_after)
    ok = status_allows_runtime_turn(status_after, allow_degraded=allow_degraded)
    after_requested, after_resolved, after_endpoint = _transport_roots(config, status_after)
    startup_reused = bool(startup.get("already_running"))
    return DaemonEnsureResult(
        ok=ok,
        ensured=ok,
        active_state=after_state,
        reason="daemon_started_or_reused" if ok else "daemon_start_failed",
        decision=decision.to_dict(),
        status_before=status_before,
        startup=startup,
        status_after=status_after,
        selected_transport="persistent_daemon" if ok else "host_diagnostic",
        fallback_reason=(
            "daemon_reused"
            if ok and startup_reused
            else "daemon_started"
            if ok
            else "daemon_start_required_failed"
        ),
        requested_runtime_root=after_requested,
        resolved_active_root=after_resolved,
        daemon_endpoint_root=after_endpoint,
        daemon_identity_verified=bool(
            ok and status_after.get("endpoint_identity_matches")
        ),
        daemon_reused=bool(ok and startup_reused),
        daemon_started=bool(ok and not startup_reused),
    )


def daemon_autostart_policy_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env_map = env if env is not None else __import__("os").environ
    return {
        "schema_version": schema_version("daemon_autostart_policy"),
        "daemon_schema_version": DAEMON_SCHEMA_VERSION,
        "enabled_by_default": not _falsey(env_map.get(AUTOSTART_ENV)),
        "force_env": _truthy(env_map.get(FORCE_ENSURE_ENV), default=False),
        "autostart_env": env_map.get(AUTOSTART_ENV),
        "command_filter_env": env_map.get(AUTOSTART_COMMANDS_ENV),
        "runtime_turn_commands": sorted(RUNTIME_TURN_COMMANDS),
        "verified_one_shot_fallback_commands": sorted(VERIFIED_ONE_SHOT_FALLBACK_COMMANDS),
        "observational_commands": sorted(OBSERVATIONAL_COMMANDS),
        "never_autostart_commands": sorted(NEVER_AUTOSTART_COMMANDS),
        "degraded_turn_safe_reasons": sorted(DEGRADED_TURN_SAFE_REASONS),
        "degraded_turn_blocking_reasons": sorted(DEGRADED_TURN_BLOCKING_REASONS),
        "truth_boundary": (
            "Autostart jest kontraktem liveness dla tras rozmowy, nie dowodem świadomości ani zgodą na start przy komendach status/stop. "
            "Kanoniczny --chat-gpt może ponownie użyć zweryfikowanego żywego daemonu albo wykonać zweryfikowaną turę one-shot; jawne wymaganie daemonu pozostaje fail-closed. "
            "active_degraded dopuszcza turę tylko wtedy, gdy status_daemon jawnie potwierdza zgodność endpointu i świeży heartbeat; nieznane degradacje są fail-closed."
        ),
    }
