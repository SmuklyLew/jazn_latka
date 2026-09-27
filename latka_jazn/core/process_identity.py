from __future__ import annotations

"""Cross-platform process identity primitives for runtime ownership gates.

A PID is only a routing hint because operating systems may reuse it after a
process exits.  These helpers bind a PID to process-creation evidence whenever
the host exposes a stable token.  Missing evidence remains unknown and must not
be silently promoted to trusted ownership.
"""

import errno
import os
from pathlib import Path
import secrets
from typing import Any, Callable

PROCESS_FINGERPRINT_SCHEMA_VERSION = "daemon_process_fingerprint/v1"
_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_is_alive(pid: int | None) -> bool:
    try:
        pid_int = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if pid_int <= 0:
        return False
    if pid_int == os.getpid():
        return True

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [
                wintypes.DWORD,
                wintypes.BOOL,
                wintypes.DWORD,
            ]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.DWORD),
            ]
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(
                _PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid_int,
            )
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(
                    handle,
                    ctypes.byref(exit_code),
                ):
                    return False
                return int(exit_code.value) == _STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False

    try:
        os.kill(pid_int, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno != errno.ESRCH
    return True


def _linux_process_start_token(pid: int) -> tuple[str | None, str | None]:
    try:
        stat_text = Path(f"/proc/{int(pid)}/stat").read_text(
            encoding="utf-8",
            errors="replace",
        )
        closing = stat_text.rfind(")")
        if closing < 0:
            return None, None
        fields = stat_text[closing + 2 :].split()
        starttime = fields[19] if len(fields) > 19 else None
    except (
        FileNotFoundError,
        ProcessLookupError,
        OSError,
        ValueError,
        IndexError,
    ):
        return None, None
    try:
        boot_id = (
            Path("/proc/sys/kernel/random/boot_id")
            .read_text(encoding="ascii")
            .strip()
            or None
        )
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
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            int(pid),
        )
        if not handle:
            return None
        try:
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None
            return str(
                (int(created.dwHighDateTime) << 32)
                | int(created.dwLowDateTime)
            )
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def process_fingerprint(
    pid: int | None,
    *,
    pid_is_alive: Callable[[int], bool] | None = None,
) -> dict[str, Any]:
    try:
        pid_int = int(pid or 0)
    except (TypeError, ValueError):
        pid_int = 0
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

    alive_probe = pid_is_alive or process_is_alive
    if not alive_probe(pid_int):
        payload["state"] = "not_alive"
        return payload

    if os.name == "posix":
        boot_id, starttime = _linux_process_start_token(pid_int)
        payload.update(
            {
                "boot_id": boot_id,
                "proc_starttime_ticks": starttime,
            }
        )
        if starttime:
            payload.update(
                {
                    "available": True,
                    "identity_token": (
                        f"linux:{boot_id or 'boot-unknown'}:{starttime}"
                    ),
                    "state": "observed",
                }
            )
            return payload
    elif os.name == "nt":
        created = _windows_process_creation_filetime(pid_int)
        payload["creation_filetime_100ns"] = created
        if created:
            payload.update(
                {
                    "available": True,
                    "identity_token": f"windows:{created}",
                    "state": "observed",
                }
            )
            return payload

    payload["state"] = "alive_without_stable_token"
    return payload


def process_fingerprint_matches(
    expected: Any,
    observed: Any,
) -> bool | None:
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
