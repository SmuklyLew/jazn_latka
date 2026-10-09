from __future__ import annotations

"""Fail-closed boundary between Memory Studio staging and persistent Jaźń memory."""

from pathlib import Path

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.memory.memory_root import (
    default_memory_root,
    legacy_memory_root,
    resolve_memory_root,
)


def require_isolated_staging_path(path: str | Path, *, tool_root: str | Path) -> Path:
    """Reject writes into runtime state or either canonical/legacy private memory root.

    Resolve symlinks before comparing. This is deliberately stricter than checking
    the daemon PID: stale markers, failed liveness probes or a daemon restarted
    during a long import must never turn a live memory directory into staging.
    """
    candidate = Path(path).expanduser().resolve()
    root = Path(tool_root).expanduser().resolve()
    protected = (
        workspace_runtime_path(root),
        default_memory_root(root),
        legacy_memory_root(root),
        resolve_memory_root(root),
    )
    for base in protected:
        if candidate == base or base in candidate.parents:
            raise ValueError(
                "Blokada zapisu: cel znajduje się w pamięci/runtime Jaźni "
                f"({base}). Wybierz osobny katalog staging."
            )
    if candidate == root:
        raise ValueError("Blokada zapisu: katalog główny Jaźni nie jest stagingiem.")
    return candidate


def require_isolated_database(
    database: str | Path, *, tool_root: str | Path, project_target: str | Path | None = None,
) -> Path:
    """Check the actual selected SQLite and the project's rebuild destination."""
    selected = require_isolated_staging_path(database, tool_root=tool_root)
    if project_target:
        require_isolated_staging_path(project_target, tool_root=tool_root)
    return selected


__all__ = ["require_isolated_database", "require_isolated_staging_path"]
