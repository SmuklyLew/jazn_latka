from __future__ import annotations

"""Canonical host-level memory root resolution.

Runtime code may live in versioned ``active_root`` directories, while private
memory is mutable host state that should survive code upgrades.  This module
keeps that boundary explicit and preserves a read-compatible fallback for
historical ``<active_root>/memory`` layouts.
"""

import os
from pathlib import Path

from latka_jazn.core.runtime_root import workspace_runtime_path

MEMORY_DIR_NAME = "memory"
MEMORY_ROOT_ENV = "JAZN_MEMORY_ROOT"


def legacy_memory_root(runtime_root: str | Path) -> Path:
    """Return the historical per-version memory directory."""

    return (Path(runtime_root).expanduser().resolve() / MEMORY_DIR_NAME).resolve()


def default_memory_root(runtime_root: str | Path) -> Path:
    """Return the host-level memory directory shared by sibling runtimes."""

    root = Path(runtime_root).expanduser().resolve()
    return (workspace_runtime_path(root) / MEMORY_DIR_NAME).resolve()


def resolve_memory_root(
    runtime_root: str | Path,
    *,
    configured: str | Path | None = None,
    prefer_existing_legacy: bool = True,
) -> Path:
    """Resolve the canonical memory directory without creating it.

    Resolution order:
    1. explicit ``configured`` value;
    2. ``JAZN_MEMORY_ROOT``;
    3. host-level ``workspace_runtime/memory``;
    4. historical ``<active_root>/memory`` only when the host-level directory
       does not yet exist and compatibility fallback is enabled.

    Relative explicit values are resolved against the host-level runtime
    workspace, not the versioned code root.  This prevents a new override from
    accidentally re-introducing version-coupled private memory.
    """

    root = Path(runtime_root).expanduser().resolve()
    raw: str | Path | None = configured
    if raw is None or not str(raw).strip():
        env_value = os.environ.get(MEMORY_ROOT_ENV)
        raw = env_value if env_value and env_value.strip() else None

    if raw is not None and str(raw).strip():
        candidate = Path(str(raw).strip()).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        workspace = workspace_runtime_path(root)
        resolved = (workspace / candidate).resolve()
        try:
            resolved.relative_to(workspace)
        except ValueError as exc:
            raise ValueError(f"{MEMORY_ROOT_ENV} escapes runtime workspace: {raw}") from exc
        return resolved

    canonical = default_memory_root(root)
    if canonical.exists() or not prefer_existing_legacy:
        return canonical
    legacy = legacy_memory_root(root)
    if legacy.exists():
        return legacy
    return canonical


def memory_path(
    runtime_root: str | Path,
    relative: str | Path,
    *,
    configured_root: str | Path | None = None,
    prefer_existing_legacy: bool = True,
) -> Path:
    """Resolve a relative path below the selected memory root, fail-closed."""

    base = resolve_memory_root(
        runtime_root,
        configured=configured_root,
        prefer_existing_legacy=prefer_existing_legacy,
    )
    rel = Path(relative)
    if rel.is_absolute():
        raise ValueError(f"memory path must be relative: {relative}")
    parts = rel.parts
    if parts and parts[0].casefold() == MEMORY_DIR_NAME.casefold():
        rel = Path(*parts[1:])
    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"memory path escapes memory root: {relative}") from exc
    return target


__all__ = [
    "MEMORY_DIR_NAME",
    "MEMORY_ROOT_ENV",
    "default_memory_root",
    "legacy_memory_root",
    "memory_path",
    "resolve_memory_root",
]
