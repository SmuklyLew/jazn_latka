"""Opt-in dedicated-root private data scope; not a new public ingress policy.

One independently provisioned SYSTEM and process per principal. The .26
reviewed-owner gate remains mandatory. This module never assigns ownership,
creates a root, imports history, or enables multi-tenant routing.
"""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import stat

from latka_jazn.core.admission_owner_context import (
    PRIVATE_CONTEXT_OWNER_FILE, public_private_context_authorized,
)

DEDICATED_CONTEXT_ENV = "JAZN_PRIVATE_CONTEXT_ISOLATION"
DEDICATED_OWNER_ENV = "JAZN_PRIVATE_CONTEXT_OWNER_SHA256"


def dedicated_context_enabled() -> bool:
    mode = os.environ.get(DEDICATED_CONTEXT_ENV, "off").strip().casefold()
    if mode not in {"off", "dedicated_root"}:
        raise ValueError("private_context_isolation_mode_invalid")
    return mode == "dedicated_root"


def _inspect_component(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if stat.S_ISLNK(info.st_mode) or reparse:
        raise ValueError("private_context_link_not_allowed")
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("private_context_directory_required")
    elif not stat.S_ISDIR(info.st_mode):
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("private_context_file_alias_not_allowed")


def private_child(base: Path, target: Path, *, directory: bool = False) -> Path:
    """Check a lexical child before any resolve/open can follow an alias.

    Existing components must not be links/reparse points or special files;
    existing regular files must have one link. Missing children are allowed for
    canonical creation. This assumes trusted operators and stable filesystem
    permissions, not protection against concurrent privileged path replacement.
    """
    base = Path(base)
    target = Path(target)
    if not base.is_absolute() or not target.is_absolute() or ".." in base.parts:
        raise ValueError("private_context_path_must_be_absolute")
    try:
        relative = target.relative_to(base)
    except ValueError as exc:
        raise ValueError("private_context_path_escapes_scope") from exc
    if not relative.parts:
        raise ValueError("private_context_child_required")
    _inspect_component(base, directory=True)
    current = base
    for index, part in enumerate(relative.parts):
        if (part in {"", ".", ".."} or ":" in part or part.endswith((" ", "."))
                or PureWindowsPath(part).is_reserved()):
            raise ValueError("private_context_path_component_invalid")
        current = current / part
        _inspect_component(current, directory=directory or index < len(relative.parts) - 1)
    return current


def private_database_path(base: Path, target: Path) -> Path:
    """Validate a SQLite file and its standard sidecars before use."""
    target = private_child(base, target)
    if target.exists() and not target.is_file():
        raise ValueError("private_context_database_file_required")
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = private_child(base, target.with_name(target.name + suffix))
        if sidecar.exists() and not sidecar.is_file():
            raise ValueError("private_context_database_file_required")
    return target


def dedicated_context_root(root: Path | str) -> Path | None:
    if not dedicated_context_enabled():
        return None
    base = Path(root).expanduser().resolve(strict=True)
    resources = private_child(base, base / "local_resources", directory=True)
    private_child(base, base / PRIVATE_CONTEXT_OWNER_FILE)
    owner = os.environ.get(DEDICATED_OWNER_ENV)
    if not resources.is_dir() or not public_private_context_authorized(base, owner):
        raise ValueError("dedicated_private_context_owner_unverified")
    if os.environ.get("JAZN_MEMORY_SYNC_MODE", "off").strip().casefold() != "off":
        raise ValueError("dedicated_private_context_sync_not_verified")
    return base


def dedicated_workspace_path(root: Path, configured: str | Path | None = None) -> Path | None:
    base = dedicated_context_root(root)
    if base is None:
        return None
    for raw in (configured, os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR")):
        name = str(raw or "").strip().replace("\\", "/").casefold()
        if name not in {"", "workspace_runtime", "$root/workspace_runtime", "${root}/workspace_runtime"}:
            raise ValueError("dedicated_private_context_workspace_override_not_allowed")
    return private_child(base, base / "workspace_runtime", directory=True)


def dedicated_memory_path(root: Path | str, configured: str | Path | None = None) -> Path | None:
    base = dedicated_context_root(root)
    if base is None:
        return None
    for raw in (configured, os.environ.get("JAZN_MEMORY_ROOT")):
        if str(raw or "").strip().casefold() not in {"", "memory"}:
            raise ValueError("dedicated_private_context_memory_override_not_allowed")
    return private_child(base, base / "memory", directory=True)
