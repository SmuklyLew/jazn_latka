"""Source-bound host-memory observations, never inferred by a language model.

No metric is returned as observed without a successful OS API call.
The observation belongs to the sampled host at the sampled time, not a later
Jaźń turn, remote Cloudflare worker, or ChatGPT browser session.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sys
from typing import Any


def memory_observation(total_bytes: int | None, available_bytes: int | None,
                       *, source: str | None) -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).isoformat()
    trusted = {"windows_globalmemorystatusex", "linux_proc_meminfo"}
    if (source not in trusted or type(total_bytes) is not int or
            type(available_bytes) is not int or total_bytes <= 0 or
            available_bytes < 0 or available_bytes > total_bytes):
        return {
            "status": "not_verified", "source": None,
            "observed_at_utc": None, "physical_ram_percent_used": None,
            "truth_boundary": "RAM percentage unavailable: no valid source observation.",
        }
    percent = round(100.0 * (total_bytes - available_bytes) / total_bytes, 1)
    return {
        "status": "observed", "source": source,
        "observed_at_utc": stamp,
        "physical_ram_total_bytes": total_bytes,
        "physical_ram_available_bytes": available_bytes,
        "physical_ram_percent_used": percent,
        "truth_boundary": (
            "One measured host snapshot. Not a historic sample or a metric "
            "for an unmeasured ChatGPT/Cloudflare environment."
        ),
    }


def sample_host_memory() -> dict[str, Any]:
    if sys.platform == "win32":
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        data = MemoryStatusEx()
        data.dwLength = ctypes.sizeof(MemoryStatusEx)
        try:
            ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(data))
        except (AttributeError, OSError):
            ok = 0
        return memory_observation(int(data.ullTotalPhys), int(data.ullAvailPhys),
                                  source="windows_globalmemorystatusex") if ok else memory_observation(None, None, source=None)
    if sys.platform.startswith("linux"):
        try:
            from pathlib import Path
            rows = {}
            for row in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                key, _, value = row.partition(":")
                rows[key] = int(value.strip().split()[0]) * 1024
            return memory_observation(rows.get("MemTotal"), rows.get("MemAvailable"),
                                      source="linux_proc_meminfo")
        except (OSError, ValueError, IndexError):
            pass
    return memory_observation(None, None, source=None)
