from __future__ import annotations

"""Production deployment orchestration for the public ChatGPT MCP gateway.

This module deliberately does not own Jaźń lifecycle. It composes the existing
public ``run.py`` control-plane commands so a container or service manager can
start the persistent daemon, verify *conversation-ready* state, ensure/reuse the
canonical runtime supervisor, and then replace itself with the OAuth-protected
Streamable HTTP MCP gateway.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from latka_jazn.version import PACKAGE_VERSION_FULL


DEFAULT_CONTAINER_ROOT = Path("/opt/jazn")
DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_PUBLIC_PORT = 8080
DEFAULT_DAEMON_URL = "http://127.0.0.1:8787"
DEFAULT_SUPERVISOR_STARTUP_TIMEOUT_SECONDS = 15.0
DEFAULT_SUPERVISOR_POLL_INTERVAL_SECONDS = 0.25

CLIENT_ID_ENV = "JAZN_MCP_OAUTH_CLIENT_ID"
CLIENT_SECRET_ENV = "JAZN_MCP_OAUTH_CLIENT_SECRET"
REQUIRE_SUPERVISOR_ENV = "JAZN_MCP_REQUIRE_SUPERVISOR"


class DeploymentError(RuntimeError):
    """Fail-closed public MCP deployment configuration/runtime error."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = str(code)


def _csv_values(value: str | None) -> tuple[str, ...]:
    return tuple(
        item
        for item in (part.strip() for part in str(value or "").split(","))
        if item
    )


def _bool_env(value: str | None, *, name: str, default: bool) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise DeploymentError(
        f"{name} must be one of 1/0, true/false, yes/no or on/off",
        code=f"invalid_{name.lower()}",
    )


def _required_https_url(value: str | None, *, name: str) -> str:
    candidate = str(value or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise DeploymentError(
            f"{name} must be an absolute HTTPS URL",
            code=f"invalid_{name}",
        )
    if parsed.username is not None or parsed.password is not None:
        raise DeploymentError(
            f"{name} must not contain embedded credentials",
            code=f"invalid_{name}",
        )
    return candidate


def _loopback_daemon_url(value: str | None) -> str:
    candidate = str(value or DEFAULT_DAEMON_URL).strip()
    parsed = urlsplit(candidate)
    hostname = str(parsed.hostname or "").lower()
    if parsed.scheme.lower() not in {"http", "https"}:
        raise DeploymentError(
            "daemon URL must use HTTP(S)",
            code="invalid_daemon_url",
        )
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise DeploymentError(
            "public MCP deployment must keep the Jaźń daemon on loopback",
            code="daemon_must_remain_loopback",
        )
    if parsed.username is not None or parsed.password is not None:
        raise DeploymentError(
            "daemon URL must not contain credentials",
            code="invalid_daemon_url",
        )
    return candidate


def _port(value: str | int | None) -> int:
    try:
        port = int(value if value is not None else DEFAULT_PUBLIC_PORT)
    except (TypeError, ValueError) as exc:
        raise DeploymentError(
            "JAZN_MCP_PORT must be an integer",
            code="invalid_public_mcp_port",
        ) from exc
    if not 1 <= port <= 65535:
        raise DeploymentError(
            "JAZN_MCP_PORT must be between 1 and 65535",
            code="invalid_public_mcp_port",
        )
    return port


def _json_object_from_completed_process(
    completed: subprocess.CompletedProcess[str],
    *,
    invalid_code: str,
    command_label: str,
) -> dict[str, Any]:
    if int(completed.returncode) != 0:
        raise DeploymentError(
            f"{command_label} failed",
            code=f"{invalid_code}_command_failed",
        )
    try:
        payload = json.loads(str(completed.stdout or "").strip())
    except json.JSONDecodeError as exc:
        raise DeploymentError(
            f"{command_label} did not return one JSON object",
            code=f"{invalid_code}_invalid_json",
        ) from exc
    if not isinstance(payload, dict):
        raise DeploymentError(
            f"{command_label} JSON must be an object",
            code=f"{invalid_code}_invalid_json",
        )
    return dict(payload)


def _runtime_status_blockers(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for field in (
        "ok",
        "daemon_reachable",
        "system_fully_ready",
        "conversation_ready",
        "activation_truth_gate_eligible",
    ):
        if payload.get(field) is not True:
            blockers.append(field)

    runtime_version = str(payload.get("runtime_version") or "").strip()
    if runtime_version != PACKAGE_VERSION_FULL:
        blockers.append("runtime_version")

    daemon_instance_id = str(
        payload.get("daemon_instance_id")
        or payload.get("runtime_instance_id")
        or ""
    ).strip()
    if not daemon_instance_id:
        blockers.append("daemon_instance_id")

    return blockers


@dataclass(frozen=True)
class PublicMcpDeploymentConfig:
    root: Path
    bind_host: str
    port: int
    daemon_url: str
    oauth_issuer_url: str
    oauth_resource_server_url: str
    oauth_introspection_url: str
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...] = ()
    oauth_scopes: tuple[str, ...] = ()
    require_supervisor: bool = True

    @classmethod
    def from_environment(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        require_runtime_root: bool = True,
    ) -> "PublicMcpDeploymentConfig":
        source: Mapping[str, str] = os.environ if env is None else env
        root = Path(str(source.get("JAZN_ROOT", DEFAULT_CONTAINER_ROOT))).expanduser().resolve()
        if require_runtime_root and not (root / "run.py").is_file():
            raise DeploymentError(
                f"Jaźń runtime root does not contain run.py: {root}",
                code="runtime_root_missing",
            )

        missing_secret_envs = [
            name for name in (CLIENT_ID_ENV, CLIENT_SECRET_ENV)
            if not str(source.get(name, "")).strip()
        ]
        if missing_secret_envs:
            raise DeploymentError(
                "required OAuth client credentials are absent: "
                + ", ".join(missing_secret_envs),
                code="oauth_client_credentials_missing",
            )

        allowed_hosts = _csv_values(source.get("JAZN_MCP_ALLOWED_HOSTS"))
        if not allowed_hosts:
            raise DeploymentError(
                "JAZN_MCP_ALLOWED_HOSTS must contain at least one public host",
                code="public_allowed_hosts_missing",
            )

        resource_url = _required_https_url(
            source.get("JAZN_MCP_OAUTH_RESOURCE_SERVER_URL"),
            name="oauth_resource_server_url",
        )
        resource_path = urlsplit(resource_url).path.rstrip("/")
        if resource_path != "/mcp":
            raise DeploymentError(
                "OAuth resource-server URL must identify the public /mcp endpoint",
                code="oauth_resource_server_path_mismatch",
            )

        return cls(
            root=root,
            bind_host=str(source.get("JAZN_MCP_BIND_HOST", DEFAULT_BIND_HOST)).strip()
            or DEFAULT_BIND_HOST,
            port=_port(source.get("JAZN_MCP_PORT")),
            daemon_url=_loopback_daemon_url(source.get("JAZN_MCP_DAEMON_URL")),
            oauth_issuer_url=_required_https_url(
                source.get("JAZN_MCP_OAUTH_ISSUER_URL"),
                name="oauth_issuer_url",
            ),
            oauth_resource_server_url=resource_url,
            oauth_introspection_url=_required_https_url(
                source.get("JAZN_MCP_OAUTH_INTROSPECTION_URL"),
                name="oauth_introspection_url",
            ),
            allowed_hosts=allowed_hosts,
            allowed_origins=_csv_values(source.get("JAZN_MCP_ALLOWED_ORIGINS")),
            oauth_scopes=_csv_values(source.get("JAZN_MCP_OAUTH_SCOPES")),
            require_supervisor=_bool_env(
                source.get(REQUIRE_SUPERVISOR_ENV),
                name=REQUIRE_SUPERVISOR_ENV,
                default=True,
            ),
        )

    def _run_py(self, command: str) -> list[str]:
        return [
            sys.executable,
            "-X",
            "utf8",
            str(self.root / "run.py"),
            command,
            "--root",
            str(self.root),
        ]

    def daemon_start_argv(self) -> list[str]:
        return self._run_py("start")

    def daemon_status_argv(self) -> list[str]:
        return [*self._run_py("status"), "--json"]

    def supervisor_status_argv(self) -> list[str]:
        return [*self._run_py("supervisor-status"), "--json"]

    def supervisor_run_argv(self) -> list[str]:
        return self._run_py("supervisor-run")

    def gateway_argv(self) -> list[str]:
        argv = [
            *self._run_py("mcp-http"),
            "--public-oauth",
            "--host",
            self.bind_host,
            "--port",
            str(self.port),
            "--daemon-url",
            self.daemon_url,
            "--oauth-issuer-url",
            self.oauth_issuer_url,
            "--oauth-resource-server-url",
            self.oauth_resource_server_url,
            "--oauth-introspection-url",
            self.oauth_introspection_url,
        ]
        for value in self.oauth_scopes:
            argv.extend(("--oauth-scope", value))
        for value in self.allowed_hosts:
            argv.extend(("--allowed-host", value))
        for value in self.allowed_origins:
            argv.extend(("--allowed-origin", value))
        return argv

    def public_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "bind_host": self.bind_host,
            "port": self.port,
            "daemon_url": self.daemon_url,
            "oauth_issuer_url": self.oauth_issuer_url,
            "oauth_resource_server_url": self.oauth_resource_server_url,
            "oauth_introspection_url": self.oauth_introspection_url,
            "allowed_hosts": list(self.allowed_hosts),
            "allowed_origins": list(self.allowed_origins),
            "oauth_scopes": list(self.oauth_scopes),
            "require_supervisor": self.require_supervisor,
            "oauth_client_id_env": CLIENT_ID_ENV,
            "oauth_client_secret_env": CLIENT_SECRET_ENV,
            "secrets_in_argv": False,
        }


Runner = Callable[..., subprocess.CompletedProcess[str]]
PopenFactory = Callable[..., Any]
Sleeper = Callable[[float], None]


def activate_persistent_runtime(
    config: PublicMcpDeploymentConfig,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Start through canonical lifecycle, then require strict ready evidence."""

    start = runner(
        config.daemon_start_argv(),
        cwd=config.root,
        text=True,
        capture_output=True,
        check=False,
    )
    if int(start.returncode) != 0:
        raise DeploymentError(
            "canonical Jaźń daemon start failed",
            code="daemon_start_failed",
        )

    status = runner(
        config.daemon_status_argv(),
        cwd=config.root,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = _json_object_from_completed_process(
        status,
        invalid_code="daemon_status",
        command_label="canonical Jaźń status probe",
    )
    blockers = _runtime_status_blockers(payload)
    if blockers:
        raise DeploymentError(
            "Jaźń daemon did not reach verified conversation-ready status; blockers="
            + ",".join(blockers),
            code="daemon_not_conversation_ready",
        )
    return payload


def ensure_runtime_supervisor(
    config: PublicMcpDeploymentConfig,
    *,
    runner: Runner = subprocess.run,
    popen: PopenFactory = subprocess.Popen,
    sleeper: Sleeper = time.sleep,
    startup_timeout_seconds: float = DEFAULT_SUPERVISOR_STARTUP_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_SUPERVISOR_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Reuse a verified supervisor or start one and wait for its lease evidence."""

    if not config.require_supervisor:
        return {
            "ok": True,
            "supervisor_required": False,
            "supervisor_active": False,
            "reason": "explicit_external_supervision_mode",
        }

    def read_status() -> dict[str, Any] | None:
        result = runner(
            config.supervisor_status_argv(),
            cwd=config.root,
            text=True,
            capture_output=True,
            check=False,
        )
        if int(result.returncode) != 0:
            return None
        try:
            payload = json.loads(str(result.stdout or "").strip())
        except json.JSONDecodeError:
            return None
        return dict(payload) if isinstance(payload, dict) else None

    existing = read_status()
    if (
        isinstance(existing, dict)
        and existing.get("ok") is True
        and existing.get("supervisor_active") is True
        and existing.get("supervisor_identity_confirmed") is True
        and existing.get("supervisor_heartbeat_fresh") is True
    ):
        return existing

    process = popen(
        config.supervisor_run_argv(),
        cwd=config.root,
        stdin=subprocess.DEVNULL,
    )

    timeout = max(0.5, float(startup_timeout_seconds))
    interval = max(0.05, float(poll_interval_seconds))
    deadline = time.monotonic() + timeout
    last_status: dict[str, Any] | None = existing
    while time.monotonic() < deadline:
        observed = read_status()
        if observed is not None:
            last_status = observed
            if (
                observed.get("ok") is True
                and observed.get("supervisor_active") is True
                and observed.get("supervisor_identity_confirmed") is True
                and observed.get("supervisor_heartbeat_fresh") is True
            ):
                return observed

        poll = getattr(process, "poll", None)
        if callable(poll):
            return_code = poll()
            if return_code not in (None, 41):
                raise DeploymentError(
                    f"runtime supervisor exited before readiness: returncode={return_code}",
                    code="supervisor_start_failed",
                )
        sleeper(interval)

    detail = ""
    if isinstance(last_status, Mapping):
        detail = f"; last_state={last_status.get('state')!r}"
    raise DeploymentError(
        "runtime supervisor did not become active before startup timeout" + detail,
        code="supervisor_not_ready",
    )


def run_public_mcp_deployment(
    env: Mapping[str, str] | None = None,
    *,
    runner: Runner = subprocess.run,
    popen: PopenFactory = subprocess.Popen,
    sleeper: Sleeper = time.sleep,
    execv: Callable[[str, list[str]], Any] | None = None,
) -> int:
    """Activate runtime, ensure supervision, then exec the protected gateway."""

    try:
        config = PublicMcpDeploymentConfig.from_environment(env)
        activate_persistent_runtime(config, runner=runner)
        ensure_runtime_supervisor(
            config,
            runner=runner,
            popen=popen,
            sleeper=sleeper,
        )
    except DeploymentError as exc:
        print(
            json.dumps(
                {"ok": False, "reason": exc.code, "detail": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    argv = config.gateway_argv()
    exec_impl = os.execv if execv is None else execv
    exec_impl(argv[0], argv)
    return 0


def main() -> int:
    return run_public_mcp_deployment()


if __name__ == "__main__":
    raise SystemExit(main())
