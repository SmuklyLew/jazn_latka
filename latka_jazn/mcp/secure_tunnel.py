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


@dataclass(frozen=True, slots=True)
class SecureMcpTunnelPlan:
    root: str
    profile_name: str
    tunnel_client_binary: str
    stdio_mcp_argv: tuple[str, ...]
    stdio_mcp_command: str
    init_argv: tuple[str, ...]
    doctor_argv: tuple[str, ...]
    run_argv: tuple[str, ...]
    requires_control_plane_tunnel_id: bool = True
    requires_control_plane_api_key: bool = True
    inbound_public_port_required: bool = False
    transport: str = "openai_secure_mcp_tunnel_stdio"
    local_mcp_transport: str = "stdio"
    remote_runtime_transport_bundled: bool = False
    package_contains_tunnel_target: bool = True
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["stdio_mcp_argv"] = list(self.stdio_mcp_argv)
        payload["init_argv"] = list(self.init_argv)
        payload["doctor_argv"] = list(self.doctor_argv)
        payload["run_argv"] = list(self.run_argv)
        payload["required_environment"] = [
            CONTROL_PLANE_TUNNEL_ID_ENV,
            CONTROL_PLANE_API_KEY_ENV,
        ]
        payload["readiness_claim_requires"] = [
            "tunnel-client process_running=true",
            "tunnel-client healthy=true",
            "tunnel-client ready=true",
            "Jaźń daemon identity/root verified by tunnel bootstrap",
            "ChatGPT connector/app capability explicitly available to the host",
        ]
        payload["truth_boundary"] = (
            "The SYSTEM package contains a safe local stdio MCP target, not the OpenAI tunnel control plane. "
            "Remote runtime availability may be claimed only from explicit tunnel-client readiness and host connector evidence. "
            "The tunnel is transport only: identity, memory, turn ownership and visible-reply finalization remain in Jaźń runtime."
        )
        return payload


def build_secure_mcp_tunnel_plan(
    root: Path,
    *,
    tunnel_id: str | None = None,
    profile_name: str = DEFAULT_PROFILE_NAME,
    tunnel_client_binary: str | None = None,
    python_executable: str | None = None,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> SecureMcpTunnelPlan:
    runtime_root = Path(root).expanduser().resolve()
    profile = str(profile_name or DEFAULT_PROFILE_NAME).strip()
    if not profile or any(ch.isspace() for ch in profile):
        raise ValueError("profile_name_must_be_nonempty_and_whitespace_free")

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
    return SecureMcpTunnelPlan(
        root=str(runtime_root),
        profile_name=profile,
        tunnel_client_binary=client,
        stdio_mcp_argv=stdio_argv,
        stdio_mcp_command=stdio_command,
        init_argv=init_argv,
        doctor_argv=doctor_argv,
        run_argv=run_argv,
    )


def classify_tunnel_runtime_status(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Turn a managed tunnel status snapshot into bounded route evidence.

    OpenAI tunnel-client documents process_running, healthy and ready as the
    fields that must all be true before a managed runtime is reported ready.
    Unknown or differently-shaped payloads fail closed.
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
        "remote_runtime_transport_available": ready,
        "execution_route": "remote_runtime" if ready else "none",
        "next_action": "use_remote_runtime_transport" if ready else "keep_remote_runtime_unverified",
        "reason_code": "secure_mcp_tunnel_ready" if ready else "secure_mcp_tunnel_not_fully_ready",
        "truth_boundary": (
            "Tunnel readiness proves an authenticated transport path only. It does not by itself prove "
            "that a particular Jaźń turn was accepted or finalized for display."
        ),
    }
