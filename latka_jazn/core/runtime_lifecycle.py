from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import time

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon_lifecycle_hotfix import install_runtime_daemon_lifecycle_hotfix

install_runtime_daemon_lifecycle_hotfix()
from latka_jazn.core.runtime_daemon import (
    DEFAULT_DAEMON_HOST,
    DEFAULT_DAEMON_PORT,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_START_TIMEOUT_SECONDS,
    DEFAULT_STOP_TIMEOUT_SECONDS,
    start_daemon,
    status_daemon,
    stop_daemon,
)
from latka_jazn.core.runtime_root import (
    RuntimeWorkspaceBusyError,
    find_start_file,
    resolve_active_runtime_marker_path,
    resolve_active_runtime_root,
    runtime_workspace_transition_lock,
)
from latka_jazn.core.source_provenance import read_source_provenance
from latka_jazn.tools.active_extraction_cache import write_active_runtime_marker
from latka_jazn.tools.package_integrity import verify_package_integrity_manifest
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

LIFECYCLE_SCHEMA_VERSION = schema_version("runtime_reload_lifecycle", version=PACKAGE_VERSION_FULL)


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _restore_marker(path: Path, payload: bytes | None) -> dict[str, Any]:
    path = Path(path)
    result: dict[str, Any] = {"ok": False, "path": str(path), "restored": False, "removed": False, "error": None}
    try:
        if payload is None:
            path.unlink(missing_ok=True)
            result.update({"ok": True, "removed": True})
            return result
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.rollback.tmp")
        try:
            with tmp.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        result.update({"ok": True, "restored": True})
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _target_preflight(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    start_file = find_start_file(root)
    package = verify_package_integrity_manifest(root)
    provenance = read_source_provenance(root, profile="system_smoke").to_dict()
    provenance_ok = provenance.get("status") in {
        "clean_checkout_verified",
        "development_dirty_verified",
        "verified_export_without_git_history",
    }
    ok = bool(start_file and package.get("ok") is True and provenance_ok)
    return {
        "ok": ok,
        "root": str(root),
        "start_file": str(start_file) if start_file else None,
        "package_integrity_verification": package,
        "source_provenance": provenance,
        "source_provenance_verified": provenance_ok,
        "error_code": None if ok else (
            "target_start_file_missing" if start_file is None else
            "target_package_integrity_verification_failed" if package.get("ok") is not True else
            "target_source_provenance_not_verified"
        ),
    }


def reload_daemon(
    config: JaznConfig,
    *,
    target_root: Path | None = None,
    host: str = DEFAULT_DAEMON_HOST,
    port: int = DEFAULT_DAEMON_PORT,
    marker_output: Path | None = None,
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    startup_timeout: float = DEFAULT_START_TIMEOUT_SECONDS,
    stop_timeout: float = DEFAULT_STOP_TIMEOUT_SECONDS,
    restart_same_root: bool = True,
) -> dict[str, Any]:
    """Transactionally restart or hand off the singleton daemon to ``target_root``.

    The marker is switched only after the current instance has been stopped and
    the target root passes structural/integrity/provenance preflight.  If target
    startup fails, the previous marker is restored and the previous runtime is
    restarted when it was active before the transaction.
    """

    operator_root = Path(config.root).expanduser().resolve()
    target = Path(target_root or operator_root).expanduser().resolve()
    marker_path = resolve_active_runtime_marker_path(target, marker_output)
    target_preflight = _target_preflight(target)
    if target_preflight.get("ok") is not True:
        return {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "ok": False,
            "state": "target_preflight_failed",
            "error_code": target_preflight.get("error_code"),
            "target_root": str(target),
            "marker_path": str(marker_path),
            "target_preflight": target_preflight,
        }

    try:
        with runtime_workspace_transition_lock(target, "daemon-reload", stale_after_seconds=max(60.0, stop_timeout + startup_timeout + 15.0)):
            marker_before = _read_bytes(marker_path)
            resolution = resolve_active_runtime_root(operator_root, marker_path=marker_path)
            if resolution.marker_found and not resolution.marker_valid:
                return {
                    "schema_version": LIFECYCLE_SCHEMA_VERSION,
                    "ok": False,
                    "state": "current_marker_untrusted",
                    "error_code": "active_runtime_subject_unresolved",
                    "target_root": str(target),
                    "marker_path": str(marker_path),
                    "active_root_validation_error": resolution.error,
                }
            previous_root = resolution.root if resolution.marker_found and resolution.marker_valid else None
            observation_root = previous_root or operator_root
            before = status_daemon(
                JaznConfig(root=observation_root),
                host=host,
                port=port,
                marker_output=marker_path,
            )
            previous_was_active = before.get("active_state") in {"active_trusted", "active_degraded"}
            if before.get("endpoint_reachable") is True and not previous_was_active:
                return {
                    "schema_version": LIFECYCLE_SCHEMA_VERSION,
                    "ok": False,
                    "state": "current_daemon_identity_untrusted",
                    "error_code": "daemon_identity_not_confirmed",
                    "target_root": str(target),
                    "marker_path": str(marker_path),
                    "before": before,
                }
            if before.get("pid_alive_os_probe") is True and before.get("process_identity_confirmed") is not True and before.get("process_fingerprint_match") is not False:
                return {
                    "schema_version": LIFECYCLE_SCHEMA_VERSION,
                    "ok": False,
                    "state": "current_process_identity_untrusted",
                    "error_code": "daemon_process_identity_not_confirmed",
                    "target_root": str(target),
                    "marker_path": str(marker_path),
                    "before": before,
                }

            same_root = bool(previous_root and previous_root.resolve() == target.resolve())
            if previous_was_active and same_root and not restart_same_root:
                return {
                    "schema_version": LIFECYCLE_SCHEMA_VERSION,
                    "ok": True,
                    "state": "already_active_target",
                    "target_root": str(target),
                    "previous_root": str(previous_root),
                    "marker_path": str(marker_path),
                    "before": before,
                    "after": before,
                    "changed": False,
                }

            stop_result: dict[str, Any] | None = None
            if previous_was_active:
                stop_result = stop_daemon(
                    JaznConfig(root=previous_root or observation_root),
                    host=host,
                    port=port,
                    marker_output=marker_path,
                    timeout=stop_timeout,
                )
                if stop_result.get("ok") is not True:
                    return {
                        "schema_version": LIFECYCLE_SCHEMA_VERSION,
                        "ok": False,
                        "state": "stop_failed_no_handoff",
                        "error_code": stop_result.get("error_code") or "daemon_stop_failed",
                        "target_root": str(target),
                        "previous_root": str(previous_root) if previous_root else None,
                        "marker_path": str(marker_path),
                        "before": before,
                        "stop": stop_result,
                        "marker_changed": False,
                    }

            marker_clear = _restore_marker(marker_path, None)
            if marker_clear.get("ok") is not True:
                rollback_marker = _restore_marker(marker_path, marker_before)
                rollback_start = None
                if previous_was_active and previous_root is not None and rollback_marker.get("ok") is True:
                    rollback_start = start_daemon(
                        JaznConfig(root=previous_root),
                        host=host,
                        port=port,
                        marker_output=marker_path,
                        heartbeat_interval=heartbeat_interval,
                        startup_timeout=startup_timeout,
                    )
                return {
                    "schema_version": LIFECYCLE_SCHEMA_VERSION,
                    "ok": False,
                    "state": "target_marker_clear_failed",
                    "error_code": "active_runtime_marker_transition_failed",
                    "target_root": str(target),
                    "previous_root": str(previous_root) if previous_root else None,
                    "marker_path": str(marker_path),
                    "marker_clear": marker_clear,
                    "rollback": {"marker": rollback_marker, "start_previous": rollback_start},
                }
            marker_target = write_active_runtime_marker(
                target,
                marker_output=marker_path,
                action="runtime_reload_target_prestart",
            )
            start_result = start_daemon(
                JaznConfig(root=target),
                host=host,
                port=port,
                marker_output=marker_path,
                heartbeat_interval=heartbeat_interval,
                startup_timeout=startup_timeout,
            )
            if start_result.get("ok") is True:
                after = status_daemon(JaznConfig(root=target), host=host, port=port, marker_output=marker_path)
                success = after.get("active_state") in {"active_trusted", "active_degraded"} and after.get("endpoint_root_matches") is True
                if success:
                    return {
                        "schema_version": LIFECYCLE_SCHEMA_VERSION,
                        "ok": True,
                        "state": "reloaded" if same_root else "handoff_committed",
                        "changed": True,
                        "target_root": str(target),
                        "previous_root": str(previous_root) if previous_root else None,
                        "marker_path": str(marker_path),
                        "target_preflight": target_preflight,
                        "before": before,
                        "stop": stop_result,
                        "marker_clear": marker_clear,
                        "marker_target": marker_target,
                        "start": start_result,
                        "after": after,
                        "rollback": None,
                    }

            rollback_marker = _restore_marker(marker_path, marker_before)
            rollback_start: dict[str, Any] | None = None
            rollback_after: dict[str, Any] | None = None
            if previous_was_active and previous_root is not None and rollback_marker.get("ok") is True:
                rollback_start = start_daemon(
                    JaznConfig(root=previous_root),
                    host=host,
                    port=port,
                    marker_output=marker_path,
                    heartbeat_interval=heartbeat_interval,
                    startup_timeout=startup_timeout,
                )
                rollback_after = status_daemon(
                    JaznConfig(root=previous_root),
                    host=host,
                    port=port,
                    marker_output=marker_path,
                )
            rollback_ok = bool(
                rollback_marker.get("ok") is True
                and (
                    not previous_was_active
                    or (
                        isinstance(rollback_start, dict)
                        and rollback_start.get("ok") is True
                        and isinstance(rollback_after, dict)
                        and rollback_after.get("active_state") in {"active_trusted", "active_degraded"}
                    )
                )
            )
            return {
                "schema_version": LIFECYCLE_SCHEMA_VERSION,
                "ok": False,
                "state": "target_start_failed_rolled_back" if rollback_ok else "target_start_failed_rollback_failed",
                "error_code": "target_daemon_start_failed",
                "target_root": str(target),
                "previous_root": str(previous_root) if previous_root else None,
                "marker_path": str(marker_path),
                "target_preflight": target_preflight,
                "before": before,
                "stop": stop_result,
                "marker_clear": marker_clear,
                "marker_target": marker_target,
                "start": start_result,
                "rollback": {
                    "ok": rollback_ok,
                    "marker": rollback_marker,
                    "start_previous": rollback_start,
                    "after": rollback_after,
                },
            }
    except RuntimeWorkspaceBusyError as exc:
        return {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "ok": False,
            "state": "lifecycle_busy",
            "error_code": "runtime_lifecycle_busy",
            "error": str(exc),
            "target_root": str(target),
            "marker_path": str(marker_path),
        }


def restart_daemon(
    config: JaznConfig,
    **kwargs: Any,
) -> dict[str, Any]:
    return reload_daemon(config, target_root=Path(config.root), restart_same_root=True, **kwargs)


def wait_for_runtime_root(
    config: JaznConfig,
    target_root: Path,
    *,
    timeout: float = 10.0,
    host: str = DEFAULT_DAEMON_HOST,
    port: int = DEFAULT_DAEMON_PORT,
) -> dict[str, Any]:
    """Small monotonic helper used by integration tests/operator diagnostics."""

    deadline = time.monotonic() + max(0.0, float(timeout))
    last = status_daemon(config, host=host, port=port)
    while time.monotonic() < deadline:
        last = status_daemon(config, host=host, port=port)
        if last.get("active_state") in {"active_trusted", "active_degraded"} and Path(str(last.get("active_root"))).resolve() == Path(target_root).resolve():
            return last
        time.sleep(0.1)
    return last
