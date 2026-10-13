from __future__ import annotations

"""Portable daemon process identity probe, without runtime lifecycle ownership."""

import os
from pathlib import Path


def pid_is_alive(pid: int | None) -> bool:
    if not pid or int(pid) <= 0:
        return False
    if os.name == "posix":
        # ``kill(pid, 0)`` reports zombie children as existing even though they
        # can no longer serve requests.  Treat terminal /proc states as dead so
        # daemon stop can complete without weakening the endpoint+PID identity
        # checks used before shutdown.
        try:
            stat_text = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8", errors="replace")
            closing = stat_text.rfind(")")
            state = stat_text[closing + 2 : closing + 3] if closing >= 0 else ""
            if state in {"Z", "X", "x"}:
                return False
        except (FileNotFoundError, ProcessLookupError):
            return False
        except (OSError, ValueError):
            # /proc may be unavailable in some POSIX environments; the portable
            # signal probe below remains the fallback.
            pass
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            process_query_limited_information = 0x1000
            still_active = 259
            handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
            if not handle:
                return ctypes.get_last_error() == 5  # access denied still proves an existing PID
            try:
                exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return int(exit_code.value) == still_active
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            # Fall through to the portable probe only if the Windows API is
            # unexpectedly unavailable.
            pass
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


__all__ = ["pid_is_alive"]
