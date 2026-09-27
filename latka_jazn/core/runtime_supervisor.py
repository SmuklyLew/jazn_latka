from __future__ import annotations

"""Persistent local supervisor for the Jaźń daemon.

The supervisor is deliberately independent from one ChatGPT executor call.  It
uses the existing canonical daemon lifecycle and a cheap liveness probe during
steady state.  Full integrity/provenance/start checks remain owned by
``start_daemon`` and are invoked only when recovery is actually required.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
import uuid
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon_lifecycle_hotfix import install_runtime_daemon_lifecycle_hotfix

install_runtime_daemon_lifecycle_hotfix()

from latka_jazn.core.runtime_daemon import (  # noqa: E402
    DEFAULT_DAEMON_HOST,
    DEFAULT_DAEMON_PORT,
    DEFAULT_LITE_STATUS_HTTP_TIMEOUT_SECONDS,
    daemon_url,
    http_json,
    pid_is_alive,
    status_daemon,
)
from latka_jazn.core.process_identity import process_fingerprint, process_fingerprint_matches  # noqa: E402
from latka_jazn.core.runtime_health import DaemonHealthClass, classify_daemon_health  # noqa: E402
from latka_jazn.core.runtime_lifecycle import restart_daemon  # noqa: E402
from latka_jazn.core.runtime_root import workspace_runtime_path  # noqa: E402
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version  # noqa: E402

SUPERVISOR_SCHEMA_VERSION = schema_version("persistent_runtime_supervisor")
DEFAULT_SUPERVISOR_CHECK_INTERVAL_SECONDS = 5.0
DEFAULT_SUPERVISOR_BASE_BACKOFF_SECONDS = 2.0
DEFAULT_SUPERVISOR_MAX_BACKOFF_SECONDS = 60.0
DEFAULT_SUPERVISOR_STARTUP_TIMEOUT_SECONDS = 12.0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def supervisor_dir(root: Path) -> Path:
    return workspace_runtime_path(Path(root).expanduser().resolve()) / "supervisor"


def supervisor_state_path(root: Path) -> Path:
    return supervisor_dir(root) / "state.json"


def supervisor_pid_path(root: Path) -> Path:
    return supervisor_dir(root) / "supervisor.pid"


def supervisor_owner_path(root: Path) -> Path:
    return supervisor_dir(root) / "supervisor.owner.json"


def _supervisor_owner_payload(
    root: Path,
    pid: int,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version("persistent_runtime_supervisor_owner"),
        "package_version": PACKAGE_VERSION_FULL,
        "supervisor_instance_id": str(uuid.uuid4()),
        "pid": int(pid),
        "runtime_root": str(Path(root).expanduser().resolve()),
        "claimed_at_utc": utc_now_iso(),
        "process_fingerprint": process_fingerprint(
            pid,
            pid_is_alive=pid_is_alive,
        ),
    }


def _supervisor_identity_observation(
    root: Path,
    pid: int | None,
) -> dict[str, Any]:
    owner = _read_json(supervisor_owner_path(root))
    alive = bool(pid and pid_is_alive(int(pid)))
    observed = (
        process_fingerprint(int(pid), pid_is_alive=pid_is_alive)
        if alive and pid
        else process_fingerprint(None)
    )
    expected = (
        owner.get("process_fingerprint")
        if isinstance(owner, dict)
        else None
    )
    fingerprint_match = process_fingerprint_matches(expected, observed)
    try:
        owner_pid_matches = bool(
            owner
            and pid
            and int(owner.get("pid") or 0) == int(pid)
        )
    except (TypeError, ValueError):
        owner_pid_matches = False
    try:
        root_matches = bool(
            owner
            and str(owner.get("runtime_root") or "")
            and Path(str(owner["runtime_root"])).expanduser().resolve()
            == Path(root).expanduser().resolve()
        )
    except (OSError, RuntimeError, ValueError):
        root_matches = False
    identity_confirmed = bool(
        alive
        and owner_pid_matches
        and root_matches
        and fingerprint_match is True
    )
    if not alive:
        state = "not_alive"
    elif identity_confirmed:
        state = "confirmed"
    elif fingerprint_match is False:
        state = "pid_reused_or_foreign_process"
    else:
        state = "alive_identity_unverified"
    return {
        "pid_alive": alive,
        "owner_record_present": owner is not None,
        "owner_pid_matches": owner_pid_matches,
        "owner_root_matches": root_matches,
        "expected_process_fingerprint": expected,
        "observed_process_fingerprint": observed,
        "process_fingerprint_match": fingerprint_match,
        "identity_confirmed": identity_confirmed,
        "identity_state": state,
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def bounded_restart_backoff_seconds(
    root: Path,
    failure_count: int,
    *,
    base_seconds: float = DEFAULT_SUPERVISOR_BASE_BACKOFF_SECONDS,
    max_seconds: float = DEFAULT_SUPERVISOR_MAX_BACKOFF_SECONDS,
) -> float:
    """Exponential recovery backoff with deterministic bounded jitter."""

    count = max(1, int(failure_count))
    base = max(0.1, float(base_seconds))
    cap = max(base, float(max_seconds))
    raw = min(cap, base * (2 ** min(count - 1, 12)))
    seed = hashlib.sha256(f"{Path(root).resolve()}:{count}".encode("utf-8")).digest()[0]
    jitter_factor = 0.80 + (float(seed) / 255.0) * 0.40
    return min(cap, max(0.1, raw * jitter_factor))


def _cheap_daemon_liveness(
    root: Path,
    *,
    host: str,
    port: int,
    timeout: float = DEFAULT_LITE_STATUS_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    expected_root = Path(root).expanduser().resolve()
    try:
        payload = http_json(
            "GET",
            daemon_url(host, int(port), "/live"),
            timeout=max(0.1, float(timeout)),
        )
    except Exception as exc:
        return {
            "ok": False,
            "liveness_ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "active_root_matches": False,
        }
    reported_root = payload.get("active_root")
    try:
        root_matches = bool(
            reported_root
            and Path(str(reported_root)).expanduser().resolve() == expected_root
        )
    except (OSError, RuntimeError, ValueError):
        root_matches = False
    version_matches = str(payload.get("runtime_version") or "") == PACKAGE_VERSION_FULL
    return {
        **payload,
        "ok": bool(payload.get("liveness_ok") is True and root_matches and version_matches),
        "active_root_matches": root_matches,
        "runtime_version_matches": version_matches,
    }


def _remove_supervisor_claim_files(root: Path) -> None:
    try:
        supervisor_owner_path(root).unlink(missing_ok=True)
    except OSError:
        pass
    try:
        supervisor_pid_path(root).unlink(missing_ok=True)
    except OSError:
        pass


def _claim_supervisor_pid(root: Path) -> tuple[bool, int | None]:
    path = supervisor_pid_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    current_pid = os.getpid()
    for _attempt in range(2):
        try:
            with path.open("x", encoding="ascii") as handle:
                handle.write(str(current_pid))
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            try:
                existing = int(path.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                existing = 0

            if existing > 0:
                identity = _supervisor_identity_observation(root, existing)
                if identity["pid_alive"] is True:
                    if identity["process_fingerprint_match"] is False:
                        _remove_supervisor_claim_files(root)
                        continue
                    return False, existing

            _remove_supervisor_claim_files(root)
            continue
        else:
            try:
                _write_json_atomic(
                    supervisor_owner_path(root),
                    _supervisor_owner_payload(root, current_pid),
                )
            except OSError:
                try:
                    recorded = path.read_text(encoding="ascii").strip()
                    if recorded == str(current_pid):
                        path.unlink(missing_ok=True)
                except OSError:
                    pass
                return False, None
            return True, None
    return False, None


def _release_supervisor_claim(root: Path) -> bool:
    path = supervisor_pid_path(root)
    current_pid = os.getpid()
    try:
        recorded = int(path.read_text(encoding="ascii").strip())
    except (FileNotFoundError, OSError, ValueError):
        return False
    if recorded != current_pid:
        return False
    identity = _supervisor_identity_observation(root, current_pid)
    if identity["identity_confirmed"] is not True:
        return False
    _remove_supervisor_claim_files(root)
    return True

def supervisor_status(root: Path) -> dict[str, Any]:
    runtime_root = Path(root).expanduser().resolve()
    state = _read_json(supervisor_state_path(runtime_root)) or {}
    pid: int | None
    try:
        pid = int(
            supervisor_pid_path(runtime_root)
            .read_text(encoding="ascii")
            .strip()
        )
    except (FileNotFoundError, OSError, ValueError):
        pid = None
    identity = _supervisor_identity_observation(runtime_root, pid)
    active = identity["identity_confirmed"] is True
    return {
        "schema_version": SUPERVISOR_SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION_FULL,
        "ok": active,
        "supervisor_active": active,
        "supervisor_pid": pid,
        "supervisor_pid_alive": identity["pid_alive"],
        "supervisor_identity_confirmed": identity["identity_confirmed"],
        "supervisor_identity_state": identity["identity_state"],
        "supervisor_process_fingerprint_match": identity[
            "process_fingerprint_match"
        ],
        "supervisor_owner_record_present": identity["owner_record_present"],
        "root": str(runtime_root),
        "state": state,
        "truth_boundary": (
            "supervisor_active requires a live PID bound to the persisted "
            "process-creation fingerprint and runtime root. A live PID alone "
            "is untrusted because PIDs may be reused. Daemon readiness, tunnel "
            "readiness, connector capability and accepted visible turns remain "
            "separate evidence."
        ),
    }

def supervisor_installation_plan(root: Path, *, python_executable: str | None = None) -> dict[str, Any]:
    runtime_root = Path(root).expanduser().resolve()
    python = str(python_executable or os.environ.get("JAZN_SUPERVISOR_PYTHON") or "python")
    command = [
        python,
        "-X",
        "utf8",
        str(runtime_root / "run.py"),
        "supervisor-run",
        "--root",
        str(runtime_root),
    ]
    return {
        "schema_version": schema_version("runtime_supervisor_installation_plan"),
        "package_version": PACKAGE_VERSION_FULL,
        "root": str(runtime_root),
        "supervisor_command": command,
        "windows_task_scheduler": {
            "recommended": True,
            "trigger": "AtStartup",
            "StartWhenAvailable": True,
            "MultipleInstancesPolicy": "IgnoreNew",
            "ExecutionTimeLimit": "PT0S",
            "RestartOnFailure": {"Count": 3, "Interval": "PT1M"},
            "network_required": False,
            "purpose": "keep the local supervisor independent from an individual ChatGPT executor call",
        },
        "windows_service": {
            "preferred_for_managed_always-on_installations": True,
            "requires_service_host_contract": True,
            "not_emulated_by_plain_python_process": True,
        },
        "truth_boundary": (
            "This plan describes supported supervisor ownership settings; it does not claim the OS task/service is installed. "
            "A Windows Service requires a real Service Control Manager integration and is not faked by sc.exe around an arbitrary Python process."
        ),
    }


def _state_payload(
    root: Path,
    *,
    state: str,
    failure_count: int,
    last_liveness: dict[str, Any] | None = None,
    last_start: dict[str, Any] | None = None,
    next_retry_seconds: float | None = None,
    started_at_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": SUPERVISOR_SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION_FULL,
        "state": state,
        "root": str(Path(root).expanduser().resolve()),
        "supervisor_pid": os.getpid(),
        "started_at_utc": started_at_utc,
        "heartbeat_at_utc": utc_now_iso(),
        "failure_count": int(failure_count),
        "next_retry_seconds": next_retry_seconds,
        "last_liveness": last_liveness,
        "last_start": last_start,
    }


def run_supervisor(
    root: Path,
    *,
    host: str = DEFAULT_DAEMON_HOST,
    port: int = DEFAULT_DAEMON_PORT,
    check_interval_seconds: float = DEFAULT_SUPERVISOR_CHECK_INTERVAL_SECONDS,
    startup_timeout_seconds: float = DEFAULT_SUPERVISOR_STARTUP_TIMEOUT_SECONDS,
    stop_event: threading.Event | None = None,
) -> int:
    runtime_root = Path(root).expanduser().resolve()
    claimed, _existing_pid = _claim_supervisor_pid(runtime_root)
    if not claimed:
        # A duplicate start must never overwrite the live supervisor's shared
        # state file.  The PID contract is sufficient evidence for the caller;
        # the existing supervisor remains the only owner of state.json.
        return 41

    event = stop_event or threading.Event()
    started_at = utc_now_iso()
    failure_count = 0

    def request_stop(_signum: int, _frame: Any) -> None:
        event.set()

    previous_handlers: dict[int, Any] = {}
    if stop_event is None:
        for signum in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if isinstance(signum, int):
                try:
                    previous_handlers[signum] = signal.signal(signum, request_stop)
                except (OSError, RuntimeError, ValueError):
                    pass

    try:
        while not event.is_set():
            liveness = _cheap_daemon_liveness(runtime_root, host=host, port=port)
            if liveness.get("ok") is True:
                failure_count = 0
                _write_json_atomic(
                    supervisor_state_path(runtime_root),
                    _state_payload(
                        runtime_root,
                        state="daemon_live",
                        failure_count=0,
                        last_liveness=liveness,
                        started_at_utc=started_at,
                    ),
                )
                event.wait(max(0.2, float(check_interval_seconds)))
                continue

            # A full status/recovery path is intentionally paid only after the
            # cheap liveness probe fails. active_degraded is not automatically
            # reusable: stale heartbeat or an unreachable endpoint require the
            # canonical restart transaction, while identity ambiguity must fail
            # closed rather than killing an unverified process.
            observed = status_daemon(JaznConfig(root=runtime_root), host=host, port=port)
            health = classify_daemon_health(observed)
            observed_with_health = {
                "cheap": liveness,
                "full": observed,
                "health": health.to_dict(),
            }
            if health.classification is DaemonHealthClass.HEALTHY:
                failure_count = 0
                _write_json_atomic(
                    supervisor_state_path(runtime_root),
                    _state_payload(
                        runtime_root,
                        state="daemon_live_after_full_probe",
                        failure_count=0,
                        last_liveness=observed_with_health,
                        started_at_utc=started_at,
                    ),
                )
                event.wait(max(0.2, float(check_interval_seconds)))
                continue

            if health.classification is DaemonHealthClass.IDENTITY_AMBIGUOUS:
                failure_count += 1
                delay = bounded_restart_backoff_seconds(runtime_root, failure_count)
                _write_json_atomic(
                    supervisor_state_path(runtime_root),
                    _state_payload(
                        runtime_root,
                        state="daemon_recovery_blocked_identity_ambiguous",
                        failure_count=failure_count,
                        last_liveness=observed_with_health,
                        last_start={
                            "ok": False,
                            "error_code": "daemon_identity_ambiguous",
                            "error": health.reason,
                        },
                        next_retry_seconds=delay,
                        started_at_utc=started_at,
                    ),
                )
                event.wait(delay)
                continue

            if health.classification is DaemonHealthClass.TRANSIENT:
                failure_count += 1
                delay = bounded_restart_backoff_seconds(runtime_root, failure_count)
                _write_json_atomic(
                    supervisor_state_path(runtime_root),
                    _state_payload(
                        runtime_root,
                        state="daemon_observation_transient",
                        failure_count=failure_count,
                        last_liveness=observed_with_health,
                        next_retry_seconds=delay,
                        started_at_utc=started_at,
                    ),
                )
                event.wait(delay)
                continue

            try:
                start_result = restart_daemon(
                    JaznConfig(root=runtime_root),
                    host=host,
                    port=port,
                    startup_timeout=max(0.5, float(startup_timeout_seconds)),
                )
            except Exception as exc:
                start_result = {
                    "ok": False,
                    "error_code": "supervisor_restart_exception",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            if start_result.get("ok") is True:
                failure_count = 0
                _write_json_atomic(
                    supervisor_state_path(runtime_root),
                    _state_payload(
                        runtime_root,
                        state="daemon_recovered",
                        failure_count=0,
                        last_liveness=liveness,
                        last_start={
                            "ok": True,
                            "pid": start_result.get("pid"),
                            "daemon_instance_id": start_result.get("daemon_instance_id"),
                            "already_running": start_result.get("already_running"),
                        },
                        started_at_utc=started_at,
                    ),
                )
                event.wait(max(0.2, float(check_interval_seconds)))
                continue

            failure_count += 1
            delay = bounded_restart_backoff_seconds(runtime_root, failure_count)
            _write_json_atomic(
                supervisor_state_path(runtime_root),
                _state_payload(
                    runtime_root,
                    state="daemon_recovery_backoff",
                    failure_count=failure_count,
                    last_liveness=liveness,
                    last_start={
                        "ok": False,
                        "error_code": start_result.get("error_code"),
                        "error": start_result.get("error"),
                        "pid": start_result.get("pid"),
                    },
                    next_retry_seconds=delay,
                    started_at_utc=started_at,
                ),
            )
            event.wait(delay)
    finally:
        _write_json_atomic(
            supervisor_state_path(runtime_root),
            _state_payload(
                runtime_root,
                state="supervisor_stopped",
                failure_count=failure_count,
                started_at_utc=started_at,
            ),
        )
        _release_supervisor_claim(runtime_root)
        for signum, previous in previous_handlers.items():
            try:
                signal.signal(signum, previous)
            except (OSError, RuntimeError, ValueError):
                pass
    return 0
