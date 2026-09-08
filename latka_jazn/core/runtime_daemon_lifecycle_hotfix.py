from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import os
import secrets
import signal
import subprocess as subprocess_module
import sys
import time as time_module

from latka_jazn.core.version_source import read_runtime_version_from_version_py

PROCESS_FINGERPRINT_SCHEMA_VERSION = "daemon_process_fingerprint/v1"
DEFAULT_PROCESS_TERMINATION_GRACE_SECONDS = 1.5
_INSTALLED = False


def _linux_process_start_token(pid: int) -> tuple[str | None, str | None]:
    try:
        stat_text = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8", errors="replace")
        closing = stat_text.rfind(")")
        if closing < 0:
            return None, None
        fields = stat_text[closing + 2 :].split()
        starttime = fields[19] if len(fields) > 19 else None
    except (FileNotFoundError, ProcessLookupError, OSError, ValueError, IndexError):
        return None, None
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip() or None
    except (FileNotFoundError, OSError, UnicodeError):
        boot_id = None
    return boot_id, starttime


def _windows_process_creation_filetime(pid: int) -> str | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return None
        try:
            created = wintypes.FILETIME(); exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME(); user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
                return None
            return str((int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime))
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def process_fingerprint(pid: int | None, *, pid_is_alive: Callable[[int], bool] | None = None) -> dict[str, Any]:
    pid_int = int(pid or 0)
    payload: dict[str, Any] = {
        "schema_version": PROCESS_FINGERPRINT_SCHEMA_VERSION,
        "pid": pid_int if pid_int > 0 else None,
        "platform": os.name,
        "available": False,
        "identity_token": None,
    }
    if pid_int <= 0:
        payload["state"] = "not_alive"
        return payload
    if pid_is_alive is not None and not pid_is_alive(pid_int):
        payload["state"] = "not_alive"
        return payload
    if os.name == "posix":
        boot_id, starttime = _linux_process_start_token(pid_int)
        payload.update({"boot_id": boot_id, "proc_starttime_ticks": starttime})
        if starttime:
            payload.update({
                "available": True,
                "identity_token": f"linux:{boot_id or 'boot-unknown'}:{starttime}",
                "state": "observed",
            })
            return payload
    elif os.name == "nt":
        created = _windows_process_creation_filetime(pid_int)
        payload["creation_filetime_100ns"] = created
        if created:
            payload.update({"available": True, "identity_token": f"windows:{created}", "state": "observed"})
            return payload
    payload["state"] = "alive_without_stable_token"
    return payload


def process_fingerprint_matches(expected: Any, observed: Any) -> bool | None:
    if not isinstance(expected, dict) or expected.get("available") is not True:
        return None
    if not isinstance(observed, dict) or observed.get("available") is not True:
        return None
    try:
        if int(expected.get("pid") or 0) != int(observed.get("pid") or 0):
            return False
    except (TypeError, ValueError):
        return False
    left = str(expected.get("identity_token") or "")
    right = str(observed.get("identity_token") or "")
    return bool(left and right and secrets.compare_digest(left, right))


def _runtime_versions(root: Path, fallback: str, *, reader: Callable[..., Any] = read_runtime_version_from_version_py) -> tuple[str, str]:
    full = str(reader(Path(root), fallback=fallback) or fallback).strip()
    base = full.split("-", 1)[0].lstrip("v")
    return base, full


def _cleanup_owned_pid_file(rd: Any, root: Path, expected_pid: int | None) -> dict[str, Any]:
    path = rd.daemon_pid_path(root)
    result = {"path": str(path), "removed": False, "owned": False, "error": None}
    if not expected_pid:
        return result
    try:
        recorded = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return result
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    result["owned"] = recorded == str(int(expected_pid))
    if result["owned"]:
        try:
            path.unlink(missing_ok=True)
            result["removed"] = True
        except OSError as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _terminate_spawned_process(proc: subprocess_module.Popen[Any], grace_seconds: float = DEFAULT_PROCESS_TERMINATION_GRACE_SECONDS) -> dict[str, Any]:
    result: dict[str, Any] = {"attempted": False, "terminated": False, "killed": False, "returncode": proc.poll(), "error": None}
    if proc.poll() is not None:
        result.update({"terminated": True, "returncode": proc.returncode})
        return result
    result["attempted"] = True
    try:
        proc.terminate()
        try:
            proc.wait(timeout=max(0.05, float(grace_seconds)))
            result["terminated"] = True
        except subprocess_module.TimeoutExpired:
            proc.kill(); result["killed"] = True
            proc.wait(timeout=max(0.05, float(grace_seconds)))
            result["terminated"] = True
        result["returncode"] = proc.returncode
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["returncode"] = proc.poll()
    return result


class _TimeProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(time_module, name)

    @staticmethod
    def time() -> float:
        return time_module.monotonic()


class _SubprocessProxy:
    def __init__(self, sink: list[subprocess_module.Popen[Any]]) -> None:
        self._sink = sink

    def __getattr__(self, name: str) -> Any:
        return getattr(subprocess_module, name)

    def Popen(self, *args: Any, **kwargs: Any) -> subprocess_module.Popen[Any]:  # noqa: N802 - mirrors stdlib API
        proc = subprocess_module.Popen(*args, **kwargs)
        self._sink.append(proc)
        return proc


def _private_daemon_start_command(rd: Any, root: Path, **kwargs: Any) -> list[str]:
    root = Path(root).resolve()
    run_file = root / "run.py"
    hotfix_module = root / "latka_jazn" / "core" / "runtime_daemon_lifecycle_hotfix.py"
    if not run_file.is_file() or not hotfix_module.is_file():
        return rd._v50_original_build_daemon_start_command(root, **kwargs)
    command = [
        sys.executable, str(run_file), "__daemon-run-hotfix",
        "--root", str(root), "--daemon-run",
        "--daemon-host", str(kwargs.get("host", rd.DEFAULT_DAEMON_HOST)),
        "--daemon-port", str(int(kwargs.get("port", rd.DEFAULT_DAEMON_PORT))),
        "--daemon-heartbeat-interval", str(float(kwargs.get("heartbeat_interval", rd.DEFAULT_HEARTBEAT_INTERVAL_SECONDS))),
    ]
    execution_timeout = kwargs.get("execution_timeout_seconds")
    if execution_timeout is not None:
        command.extend(["--daemon-chat-timeout", str(float(execution_timeout))])
    marker_output = kwargs.get("marker_output")
    if marker_output:
        command.extend(["--daemon-marker-output", str(rd.resolve_active_runtime_marker_path(root, marker_output))])
    instance_id = kwargs.get("daemon_instance_id")
    if instance_id:
        command.extend(["--daemon-instance-id", str(instance_id)])
    return command


def install_runtime_daemon_lifecycle_hotfix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from latka_jazn.core import runtime_daemon as rd

    if getattr(rd, "_v50_runtime_lifecycle_hotfix_installed", False):
        _INSTALLED = True
        return

    rd.PROCESS_FINGERPRINT_SCHEMA_VERSION = PROCESS_FINGERPRINT_SCHEMA_VERSION
    rd.read_runtime_version_from_version_py = read_runtime_version_from_version_py
    rd._terminate_spawned_process = _terminate_spawned_process
    rd._cleanup_owned_pid_file = lambda root, expected_pid: _cleanup_owned_pid_file(rd, Path(root), expected_pid)
    rd._v50_original_build_daemon_start_command = rd.build_daemon_start_command
    rd._v50_original_start_daemon = rd.start_daemon
    rd._v50_original_status_daemon = rd.status_daemon
    rd._v50_original_stop_daemon = rd.stop_daemon
    rd._v50_original_run_daemon = rd.run_daemon
    rd.process_fingerprint = lambda pid: process_fingerprint(pid, pid_is_alive=rd.pid_is_alive)
    rd.process_fingerprint_matches = process_fingerprint_matches
    rd.build_daemon_start_command = lambda root, **kwargs: _private_daemon_start_command(rd, root, **kwargs)

    for method_name in ("marker_payload", "liveness_status_payload"):
        original = getattr(rd.JaznDaemonServer, method_name)
        def wrapped(self: Any, _original: Callable[..., Any] = original, **kwargs: Any) -> dict[str, Any]:
            payload = _original(self, **kwargs)
            if isinstance(payload, dict):
                payload["process_fingerprint"] = process_fingerprint(self.state.pid, pid_is_alive=rd.pid_is_alive)
            return payload
        setattr(rd.JaznDaemonServer, method_name, wrapped)

    def status_daemon(config: Any, **kwargs: Any) -> dict[str, Any]:
        payload = rd._v50_original_status_daemon(config, **kwargs)
        root = Path(str(payload.get("active_root") or config.root)).expanduser().resolve()
        _base, full = _runtime_versions(root, rd.PACKAGE_VERSION_FULL, reader=rd.read_runtime_version_from_version_py)
        payload["runtime_version"] = full
        marker = payload.get("marker") if isinstance(payload.get("marker"), dict) else {}
        expected = marker.get("process_fingerprint") if isinstance(marker, dict) else None
        pid = payload.get("pid")
        raw_alive = bool(payload.get("pid_alive_os_probe"))
        observed = rd.process_fingerprint(int(pid) if pid else None) if raw_alive else process_fingerprint(None)
        match = process_fingerprint_matches(expected, observed)
        identity_alive = bool(raw_alive and match is not False)
        payload.update({
            "marker_process_fingerprint": expected,
            "current_process_fingerprint": observed,
            "process_fingerprint_match": match,
            "pid_alive_os_identity": identity_alive,
        })
        if match is False and payload.get("process_identity_confirmed") is not True:
            payload.update({
                "pid_alive": False,
                "pid_alive_source": "pid_reused_fingerprint_mismatch",
                "process_state": "pid_reused",
                "identity_state": "process_fingerprint_mismatch",
                "active_state": "inactive",
                "runtime_active_state": "inactive",
                "degraded": False,
                "ok": False,
                "active_state_reason": "pid_reused_process_fingerprint_mismatch",
                "readiness_state": "not_ready",
                "observation_state": "live_probe_failed" if payload.get("endpoint_probe_performed") else "endpoint_not_probed",
            })
        return payload

    def start_daemon(config: Any, *, prefer_requested_root: bool = False, **kwargs: Any) -> dict[str, Any]:
        requested_root = Path(config.root).expanduser().resolve()
        marker_output = kwargs.get("marker_output")
        marker_path = rd.resolve_active_runtime_marker_path(requested_root, marker_output)
        if prefer_requested_root:
            subject_root = requested_root
        else:
            resolution = rd.resolve_active_runtime_root(requested_root, marker_path=marker_path)
            subject_root = resolution.root
        base_version, full_version = _runtime_versions(subject_root, rd.PACKAGE_VERSION_FULL, reader=rd.read_runtime_version_from_version_py)
        old_base, old_full, old_time, old_subprocess = rd.PACKAGE_VERSION, rd.PACKAGE_VERSION_FULL, rd.time, rd.subprocess
        spawned: list[subprocess_module.Popen[Any]] = []
        rd.PACKAGE_VERSION, rd.PACKAGE_VERSION_FULL = base_version, full_version
        rd.time = _TimeProxy()
        rd.subprocess = _SubprocessProxy(spawned)
        try:
            result = rd._v50_original_start_daemon(config, **kwargs)
        finally:
            rd.PACKAGE_VERSION, rd.PACKAGE_VERSION_FULL, rd.time, rd.subprocess = old_base, old_full, old_time, old_subprocess
        if result.get("ok") is True:
            pid = int(result.get("pid") or result.get("spawned_pid") or 0)
            marker = rd.read_json_file(marker_path) or {}
            if pid > 0 and isinstance(marker, dict):
                marker["process_fingerprint"] = process_fingerprint(pid, pid_is_alive=rd.pid_is_alive)
                rd.write_json_atomic(marker_path, marker)
            return result
        cleanup = None
        if spawned:
            cleanup = _terminate_spawned_process(spawned[-1])
            if cleanup.get("terminated"):
                result["pid_file_cleanup"] = _cleanup_owned_pid_file(rd, subject_root, spawned[-1].pid)
        result.setdefault("error_code", "daemon_startup_not_ready")
        result["process_cleanup"] = cleanup
        return result

    def stop_daemon(config: Any, **kwargs: Any) -> dict[str, Any]:
        marker_output = kwargs.get("marker_output")
        marker_path = rd.resolve_active_runtime_marker_path(config.root, marker_output)
        marker = rd.read_json_file(marker_path) or {}
        expected = marker.get("process_fingerprint") if isinstance(marker, dict) else None
        expected_pid = rd._daemon_pid_from_status(marker) if isinstance(marker, dict) else None
        original_pid_is_alive = rd.pid_is_alive
        def guarded_pid_is_alive(pid: int) -> bool:
            if not original_pid_is_alive(pid):
                return False
            if expected_pid and int(pid) == int(expected_pid) and isinstance(expected, dict):
                observed = process_fingerprint(pid, pid_is_alive=original_pid_is_alive)
                return process_fingerprint_matches(expected, observed) is not False
            return True
        rd.pid_is_alive = guarded_pid_is_alive
        try:
            result = rd._v50_original_stop_daemon(config, **kwargs)
        finally:
            rd.pid_is_alive = original_pid_is_alive
        result["expected_process_fingerprint"] = expected
        if result.get("ok") is True:
            result["process_exit_observed"] = True
            result["pid_file_cleanup"] = _cleanup_owned_pid_file(rd, Path(str((result.get("before") or {}).get("active_root") or config.root)), expected_pid)
        return result

    def run_daemon(*args: Any, **kwargs: Any) -> int:
        root = Path(args[0].root if args else kwargs["config"].root).expanduser().resolve()
        try:
            return int(rd._v50_original_run_daemon(*args, **kwargs))
        finally:
            _cleanup_owned_pid_file(rd, root, os.getpid())

    rd.status_daemon = status_daemon
    rd.start_daemon = start_daemon
    rd.stop_daemon = stop_daemon
    rd.run_daemon = run_daemon
    rd._v50_runtime_lifecycle_hotfix_installed = True
    _INSTALLED = True
