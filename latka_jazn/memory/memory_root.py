from __future__ import annotations

"""Canonical SYSTEM-root memory path resolution.

Private MEMORY is separate from the SYSTEM release package even when placed
at <active_root>/memory. Historical host-workspace MEMORY remains read-compatible
until a separately approved, verified migration. Code upgrades must not silently
move or replace private data.
"""

import os
from pathlib import Path, PureWindowsPath
from typing import Any

from latka_jazn.core.runtime_root import workspace_runtime_path

MEMORY_DIR_NAME = "memory"
MEMORY_ROOT_ENV = "JAZN_MEMORY_ROOT"


def memory_root_has_payload(root: str | Path) -> bool:
    """Return whether root contains a plausible persistent MEMORY payload.

    The check is intentionally shallow: root resolution must not recursively
    scan large private archives merely to decide between canonical and legacy
    locations. Explicit JAZN_MEMORY_ROOT remains authoritative even when
    empty; this helper is only used for automatic fallback selection.
    """

    candidate = Path(root).expanduser()
    if not candidate.is_dir():
        return False
    known_files = (
        candidate / "MEMORY_PACKAGE_MANIFEST.json",
        candidate / "raw" / "dziennik.json",
        candidate / "raw" / "chat.html",
        candidate / "sqlite" / "memory_jazn.sqlite3",
        candidate / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3",
        candidate / "sqlite" / "runtime_write_v2" / "runtime_memory.sqlite3",
        candidate / "sqlite" / "conversation_archive_v1" / "conversation_archive_manifest.sqlite3",
    )
    if any(path.is_file() for path in known_files):
        return True
    for dirname in ("sqlite", "raw", "layered", "versioned_sources"):
        directory = candidate / dirname
        if not directory.is_dir():
            continue
        try:
            next(directory.iterdir())
        except (StopIteration, OSError):
            continue
        return True
    return False


def legacy_memory_root(runtime_root: str | Path) -> Path:
    """Return the historical per-version memory directory."""

    return (Path(runtime_root).expanduser().resolve() / MEMORY_DIR_NAME).resolve()


def default_memory_root(runtime_root: str | Path) -> Path:
    """Return <SYSTEM root>/memory, independent of the process working directory."""

    return legacy_memory_root(runtime_root)


def previous_host_memory_root(runtime_root: str | Path) -> Path:
    """Return the pre-v115.21.7 host-level MEMORY location for compatibility."""

    root = Path(runtime_root).expanduser().resolve()
    return (workspace_runtime_path(root) / MEMORY_DIR_NAME).resolve()


def resolve_memory_root(
    runtime_root: str | Path,
    *,
    configured: str | Path | None = None,
    prefer_existing_legacy: bool = True,
) -> Path:
    """Select MEMORY without creating or migrating any data.

    Explicit paths override all fallback rules; relative values are anchored to
    the SYSTEM root (not CWD or workspace_runtime). In compatibility mode an
    existing older host MEMORY payload remains selectable until migration.
    """

    root = Path(runtime_root).expanduser().resolve()
    raw: str | Path | None = configured
    if raw is None or not str(raw).strip():
        value = os.environ.get(MEMORY_ROOT_ENV)
        raw = value if value and value.strip() else None
    if raw is not None and str(raw).strip():
        portable = str(raw).strip().replace("\\", "/")
        windows = PureWindowsPath(str(raw).strip())
        # On POSIX do not misinterpret Windows absolute paths as relative.
        if os.name != "nt" and (
            windows.drive or (windows.root and not portable.startswith("/"))
        ):
            raise ValueError(f"{MEMORY_ROOT_ENV} Windows-absolute path invalid on this host: {raw}")
        candidate = Path(portable).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        if ".." in portable.split("/"):
            raise ValueError(f"{MEMORY_ROOT_ENV} relative traversal denied: {raw}")
        resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"{MEMORY_ROOT_ENV} escapes SYSTEM root: {raw}") from exc
        return resolved

    canonical = default_memory_root(root)
    if not prefer_existing_legacy:
        return canonical
    if memory_root_has_payload(canonical):
        return canonical
    previous_host = previous_host_memory_root(root)
    if previous_host != canonical and memory_root_has_payload(previous_host):
        return previous_host
    return canonical


def resolve_memory_root_diagnostic(
    runtime_root: str | Path,
    *,
    configured: str | Path | None = None,
    prefer_existing_legacy: bool = True,
) -> dict[str, Any]:
    """Explain selected MEMORY paths without opening private records."""

    root = Path(runtime_root).expanduser().resolve()
    canonical = default_memory_root(root)
    legacy = legacy_memory_root(root)
    previous_host = previous_host_memory_root(root)
    env_raw = os.environ.get(MEMORY_ROOT_ENV)
    explicit_raw = configured if configured is not None else env_raw
    explicit_configured = bool(str(explicit_raw or "").strip())
    selected = resolve_memory_root(
        root,
        configured=configured,
        prefer_existing_legacy=prefer_existing_legacy,
    )
    if explicit_configured:
        source = "explicit_configured" if configured is not None else "environment"
    elif selected == canonical:
        source = "canonical_system_memory"
    elif selected == previous_host:
        source = "previous_host_memory_compatibility"
    else:
        source = "resolved_other"
    canonical_has_payload = memory_root_has_payload(canonical)
    previous_host_has_payload = memory_root_has_payload(previous_host)
    return {
        "selected": str(selected),
        "selection_source": source,
        "explicit_configured": explicit_configured,
        "canonical": str(canonical),
        "canonical_exists": canonical.exists(),
        "canonical_has_payload": canonical_has_payload,
        "legacy": str(legacy),
        "legacy_exists": legacy.exists(),
        "legacy_has_payload": memory_root_has_payload(legacy),
        "previous_host": str(previous_host),
        "previous_host_exists": previous_host.exists(),
        "previous_host_has_payload": previous_host_has_payload,
        "empty_canonical_placeholder_detected": bool(
            canonical.is_dir() and not canonical_has_payload and previous_host_has_payload
        ),
        "selected_exists": selected.exists(),
        "selected_has_payload": memory_root_has_payload(selected),
        "prefer_existing_legacy": bool(prefer_existing_legacy),
        "private_content_read": False,
    }


def normalize_memory_relative_path(relative: str | Path) -> Path:
    """Normalize one historical MEMORY prefix without accepting unsafe aliases.

    Both path separators are accepted on every host because profiles and shard
    manifests can travel between Windows and POSIX. Validate before Path erases
    traversal components, and reject Windows drives even on a POSIX host.
    """

    raw = str(relative)
    windows = PureWindowsPath(raw)
    portable = raw.replace("\\", "/")
    if not raw.strip() or windows.drive or windows.root or portable.startswith("/"):
        raise ValueError(f"memory path must be relative: {relative}")
    parts = portable.split("/")
    if ".." in parts:
        raise ValueError(f"memory path contains traversal: {relative}")
    parts = [part for part in parts if part not in {"", "."}]
    if parts and parts[0].casefold() == MEMORY_DIR_NAME:
        parts = parts[1:]
        if parts and parts[0].casefold() == MEMORY_DIR_NAME:
            raise ValueError(f"memory path has duplicated memory prefix: {relative}")
    if not parts:
        raise ValueError(f"memory path must name a child of memory root: {relative}")
    return Path(*parts)


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
    rel = normalize_memory_relative_path(relative)
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
    "memory_root_has_payload",
    "normalize_memory_relative_path",
    "previous_host_memory_root",
    "resolve_memory_root",
    "resolve_memory_root_diagnostic",
]
