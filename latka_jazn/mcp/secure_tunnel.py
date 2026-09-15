from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("secure_mcp_tunnel_transport")
DEFAULT_PROFILE_NAME = "jazn-local-runtime"
DEFAULT_RUNTIME_ALIAS = "jazn-local-runtime"
DEFAULT_TUNNEL_CLIENT_BINARY = "tunnel-client"
TUNNEL_CLIENT_BINARY_ENV = "JAZN_TUNNEL_CLIENT"
CONTROL_PLANE_TUNNEL_ID_ENV = "CONTROL_PLANE_TUNNEL_ID"
CONTROL_PLANE_API_KEY_ENV = "CONTROL_PLANE_API_KEY"
TUNNEL_BOOTSTRAP_RELATIVE_PATH = Path("latka_jazn") / "mcp" / "tunnel_bootstrap.py"
_REQUIRED_READY_FIELDS = ("process_running", "healthy", "ready")


def _platform_name(value: str | None = None) -> str:
    candidate = str(value or sys.platform).strip().lower()
    return "windows" if candidate.startswith("win") else "posix"


def quote_command(argv: Sequence[str], *, platform: str | None = None) -> str:
    """Render one subprocess argv without changing its semantics.

    tunnel-client parses the configured stdio command into argv before spawning
    it. Windows and POSIX use different quoting rules, so the bridge publishes a
    platform-correct command instead of relying on shell interpolation.
    """

    parts = [str(item) for item in argv]
    if _platform_name(platform) == "windows":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def resolve_tunnel_client_binary(
    *,
    env: Mapping[str, str] | None = None,
    binary: str | None = None,
) -> str:
    env_map = os.environ if env is None else env
    configured = str(binary or env_map.get(TUNNEL_CLIENT_BINARY_ENV) or DEFAULT_TUNNEL_CLIENT_BINARY).strip()
    return configured or DEFAULT_TUNNEL_CLIENT_BINARY


def tunnel_client_executable_status(
    *,
    env: Mapping[str, str] | None = None,
    binary: str | None = None,
) -> dict[str, Any]:
    configured = resolve_tunnel_client_binary(env=env, binary=binary)
    candidate = Path(configured).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        found = resolved.is_file()
        path = str(resolved) if found else None
    else:
        path = shutil.which(configured)
        found = bool(path)
    return {
        "schema_version": schema_version("secure_mcp_tunnel_client_probe"),
        "configured_binary": configured,
        "found": found,
        "resolved_path": path,
        "truth_boundary": (
            "Finding the tunnel-client executable proves only local operator availability. "
            "It does not prove tunnel authentication, connector publication, remote reachability, "
            "or an accepted Jaźń turn."
        ),
    }


def build_stdio_mcp_argv(
    root: Path,
    *,
    python_executable: str | None = None,
) -> tuple[str, ...]:
    runtime_root = Path(root).expanduser().resolve()
    bootstrap = runtime_root / TUNNEL_BOOTSTRAP_RELATIVE_PATH
    return (
        str(python_executable or sys.executable),
        "-X",
        "utf8",
        str(bootstrap),
        "--root",
        str(runtime_root),
    )


def _runtime_alias(value: str | None) -> str:
    alias = str(value or DEFAULT_RUNTIME_ALIAS).strip()
    if not alias or any(ch.isspace() for ch in alias):
        raise ValueError("runtime_alias_must_be_nonempty_and_whitespace_free")
    return alias


@dataclass(frozen=True, slots=True)
class SecureMcpTunnelPlan:
    root: str
    profile_name: str
    runtime_alias: str
    tunnel_client_binary: str
    stdio_mcp_argv: tuple[str, ...]
    stdio_mcp_command: str
    init_argv: tuple[str, ...]
    doctor_argv: tuple[str, ...]
    run_argv: tuple[str, ...]
    managed_connect_argv: tuple[str, ...]
    managed_status_argv: tuple[str, ...]
    managed_stop_argv: tuple[str, ...]
    requires_control_plane_tunnel_id: bool = True
    requires_control_plane_api_key: bool = True
    inbound_public_port_required: bool = False
    transport: str = "openai_secure_mcp_tunnel_stdio"
    local_mcp_transport: str = "stdio"
    remote_runtime_transport_bundled: bool = False
    package_contains_tunnel_target: bool = True
    preferred_supervision: str = "tunnel_client_managed_runtime"
    foreground_run_supported: bool = True
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "stdio_mcp_argv",
            "init_argv",
            "doctor_argv",
            "run_argv",
            "managed_connect_argv",
            "managed_status_argv",
            "managed_stop_argv",
        ):
            payload[key] = list(payload[key])
        payload["required_environment"] = [
            CONTROL_PLANE_TUNNEL_ID_ENV,
            CONTROL_PLANE_API_KEY_ENV,
        ]
        payload["runtime_api_key_reference"] = f"env:{CONTROL_PLANE_API_KEY_ENV}"
        payload["readiness_claim_requires"] = [
            "tunnel-client process_running=true",
            "tunnel-client healthy=true",
            "tunnel-client ready=true",
            "Jaźń daemon identity/root verified by tunnel bootstrap",
            "ChatGPT connector/app capability explicitly available to the host",
        ]
        payload["truth_boundary"] = (
            "The SYSTEM package contains a safe local stdio MCP target, not the OpenAI tunnel control plane. "
            "A managed tunnel runtime is the preferred long-lived supervision path. Remote runtime availability "
            "may be claimed only from explicit tunnel-client readiness plus host connector/app capability evidence. "
            "The tunnel is transport only: identity, memory, turn ownership and visible-reply finalization remain "
            "in Jaźń runtime."
        )
        return payload


def build_secure_mcp_tunnel_plan(
    root: Path,
    *,
    tunnel_id: str | None = None,
    profile_name: str = DEFAULT_PROFILE_NAME,
    runtime_alias: str = DEFAULT_RUNTIME_ALIAS,
    tunnel_client_binary: str | None = None,
    python_executable: str | None = None,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> SecureMcpTunnelPlan:
    runtime_root = Path(root).expanduser().resolve()
    profile = str(profile_name or DEFAULT_PROFILE_NAME).strip()
    if not profile or any(ch.isspace() for ch in profile):
        raise ValueError("profile_name_must_be_nonempty_and_whitespace_free")
    alias = _runtime_alias(runtime_alias)

    env_map = os.environ if env is None else env
    resolved_tunnel_id = str(tunnel_id or env_map.get(CONTROL_PLANE_TUNNEL_ID_ENV) or "<tunnel-id>").strip()
    if not resolved_tunnel_id:
        resolved_tunnel_id = "<tunnel-id>"
    client = resolve_tunnel_client_binary(env=env_map, binary=tunnel_client_binary)
    stdio_argv = build_stdio_mcp_argv(runtime_root, python_executable=python_executable)
    stdio_command = quote_command(stdio_argv, platform=platform)
    init_argv = (
        client,
        "init",
        "--sample",
        "sample_mcp_stdio_local",
        "--profile",
        profile,
        "--tunnel-id",
        resolved_tunnel_id,
        "--mcp-command",
        stdio_command,
    )
    doctor_argv = (client, "doctor", "--profile", profile, "--explain")
    run_argv = (client, "run", "--profile", profile)
    managed_connect_argv = (
        client,
        "runtimes",
        "connect",
        "--alias",
        alias,
        "--tunnel-id",
        resolved_tunnel_id,
        "--runtime-api-key",
        f"env:{CONTROL_PLANE_API_KEY_ENV}",
        "--mcp-command",
        stdio_command,
        "--json",
    )
    managed_status_argv = (client, "runtimes", "status", alias, "--json")
    managed_stop_argv = (client, "runtimes", "stop", alias, "--json")
    return SecureMcpTunnelPlan(
        root=str(runtime_root),
        profile_name=profile,
        runtime_alias=alias,
        tunnel_client_binary=client,
        stdio_mcp_argv=stdio_argv,
        stdio_mcp_command=stdio_command,
        init_argv=init_argv,
        doctor_argv=doctor_argv,
        run_argv=run_argv,
        managed_connect_argv=managed_connect_argv,
        managed_status_argv=managed_status_argv,
        managed_stop_argv=managed_stop_argv,
    )


def classify_tunnel_runtime_status(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Classify managed tunnel process/health/readiness evidence only.

    This function intentionally does not claim that ChatGPT can use the tunnel.
    Host connector/app capability is a separate gate handled by
    ``classify_remote_runtime_failover``.
    """

    value: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
    observations = {field: value.get(field) is True for field in _REQUIRED_READY_FIELDS}
    ready = all(observations.values())
    return {
        "schema_version": schema_version("secure_mcp_tunnel_readiness"),
        "package_version": PACKAGE_VERSION_FULL,
        "process_running": observations["process_running"],
        "healthy": observations["healthy"],
        "ready": observations["ready"],
        "tunnel_transport_ready": ready,
        "remote_runtime_transport_available": ready,
        "execution_route": "remote_runtime" if ready else "none",
        "next_action": "use_remote_runtime_transport" if ready else "keep_remote_runtime_unverified",
        "reason_code": "secure_mcp_tunnel_ready" if ready else "secure_mcp_tunnel_not_fully_ready",
        "truth_boundary": (
            "Tunnel readiness proves the managed transport process and its health/readiness only. "
            "A host-usable failover route additionally requires explicit ChatGPT connector/app capability evidence, "
            "and an accepted Jaźń visible turn still requires its own finalization evidence."
        ),
    }


def classify_remote_runtime_failover(
    payload: Mapping[str, Any] | None,
    *,
    host_connector_capability_available: bool | None,
) -> dict[str, Any]:
    """Combine managed tunnel readiness with host connector capability evidence.

    The route fails closed unless both sides are explicitly verified.  This is
    the evidence that may safely populate HostExecutorObservation's
    ``remote_runtime_transport_available`` field after a local executor failure.
    """

    tunnel = classify_tunnel_runtime_status(payload)
    connector_ready = host_connector_capability_available is True
    route_ready = bool(tunnel["tunnel_transport_ready"] and connector_ready)
    if not tunnel["tunnel_transport_ready"]:
        reason = "secure_mcp_tunnel_not_fully_ready"
    elif not connector_ready:
        reason = "chatgpt_connector_capability_not_verified"
    else:
        reason = "secure_mcp_remote_failover_ready"
    return {
        "schema_version": schema_version("secure_mcp_remote_failover"),
        "package_version": PACKAGE_VERSION_FULL,
        "process_running": tunnel["process_running"],
        "healthy": tunnel["healthy"],
        "ready": tunnel["ready"],
        "tunnel_transport_ready": tunnel["tunnel_transport_ready"],
        "host_connector_capability_available": connector_ready,
        "remote_runtime_transport_available": route_ready,
        "execution_route": "remote_runtime" if route_ready else "none",
        "next_action": "use_remote_runtime_transport" if route_ready else "keep_remote_runtime_unverified",
        "reason_code": reason,
        "truth_boundary": (
            "Remote failover readiness is true only when the managed Secure MCP Tunnel is fully ready and the "
            "current ChatGPT host explicitly exposes the matching connector/app capability. It does not prove an "
            "accepted or finalized visible Jaźń turn."
        ),
    }
