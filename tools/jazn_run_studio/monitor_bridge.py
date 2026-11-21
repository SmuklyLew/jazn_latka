"""Canonical Jaźń Monitor snapshot projection for JSS operator status UI.

The monitor snapshot owns service readiness. JSS lifecycle/controller jobs
remain separate operator actions and must not fabricate readiness evidence.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

MAX_MONITOR_AGE_SECONDS = 45.0

# Never conflate local MCP with authenticated public MCP HTTPS.
SERVICE_NAMES: dict[str, str | None] = {
    "runtime": "Runtime Core",
    "ollama": "Ollama",
    "gateway": "MCP",
    "cloudflare": "MCP HTTPS",  # no green without separate public auth proof
    "supervisor": "Supervisor",
    "memory": "MEMORY",
}

VALID_STATES = frozenset({
    "ready", "reachable", "unknown", "disabled", "error", "stopped",
    "unavailable",
})

def _root_identity(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve())).casefold()


def validated_snapshot(value: object, expected_root: Path) -> dict[str, Any] | None:
    """Accept one bounded, properly sourced read-only observation.

    An observation for another SYSTEM ROOT must never update this JSS window.
    This validation does not independently certify the daemon's identity;
    such proof is the monitor probe's responsibility.
    """
    if not isinstance(value, dict):
        return None
    if (value.get("schema_version") != "jazn_monitor_snapshot/v1"
            or value.get("observation_only") is not True
            or not isinstance(value.get("services"), dict)):
        return None
    root = value.get("selected_root")
    if not isinstance(root, str) or not root:
        return None
    try:
        if _root_identity(root) != _root_identity(expected_root):
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    return value


def monitor_service(report: dict[str, Any] | None, service: str, *,
                    age_seconds: float | None = None) -> tuple[str, str]:
    """One source for both the read-only monitor and service table.

    Unknown/missing/expired evidence never becomes READY. The public HTTPS
    MCP capability is unobserved by this local monitor and stays unknown.
    """
    name = SERVICE_NAMES.get(service)
    if name is None:
        return "unknown", "Nieznana usługa"
    if report is None:
        return "unknown", "Oczekiwanie na odczyt Monitora Jaźni"
    if age_seconds is None or not 0 <= age_seconds <= MAX_MONITOR_AGE_SECONDS:
        return "unknown", "Odczyt Monitora Jaźni nieaktualny"
    raw = report.get("services", {}).get(name)
    if not isinstance(raw, dict):
        return "unknown", "Brak dowodu dla: " + name
    state = raw.get("state")
    if not isinstance(state, str) or state not in VALID_STATES:
        state = "unknown"
    detail = raw.get("detail")
    if not isinstance(detail, str):
        detail = "Brak zweryfikowanych danych"
    return state, detail[:400]


def verified_daemon_pid(report: dict[str, Any] | None, *,
                        age_seconds: float | None) -> int | None:
    """A system-inventory PID is displayed only with verified instance evidence."""
    if report is None or age_seconds is None or not 0 <= age_seconds <= MAX_MONITOR_AGE_SECONDS:
        return None
    processes = report.get("processes")
    if not isinstance(processes, dict):
        return None
    rows = processes.get("items")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if (isinstance(row, dict) and row.get("name") == "Jaźń — Daemon"
                and row.get("evidence") == "verified_instance"
                and type(row.get("pid")) is int and row["pid"] > 0):
            return row["pid"]
    return None
