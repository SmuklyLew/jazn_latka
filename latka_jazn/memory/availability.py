from __future__ import annotations

"""Memory availability and core-runtime storage boundaries.

The Jaźń SYSTEM package is executable without private/persistent MEMORY data.
Private memory is an optional host-level capability that can be attached later.
Operational runtime state must therefore never create or impersonate the
canonical ``workspace_runtime/memory`` tree when no memory package is present.
"""

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.memory.memory_root import (
    MEMORY_ROOT_ENV,
    default_memory_root,
    legacy_memory_root,
    resolve_memory_root,
)
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("memory_availability")
MEMORY_MODE_ENV = "JAZN_MEMORY_MODE"
MEMORY_MODES = frozenset({"optional", "required", "off"})
CORE_STATE_DIR_NAME = "core_state"
CORE_MEMORY_RUNTIME_DIR_NAME = "memory_runtime"


def memory_mode(value: str | None = None) -> str:
    """Return the validated runtime memory mode.

    ``optional`` is the normal SYSTEM-only capable mode. ``required`` is an
    explicit operator/test policy that makes persistent memory a readiness
    requirement. ``off`` forbids use of persistent memory for the process.
    """

    raw = str(value if value is not None else os.environ.get(MEMORY_MODE_ENV, "optional"))
    normalized = raw.strip().lower() or "optional"
    if normalized not in MEMORY_MODES:
        raise ValueError(
            f"{MEMORY_MODE_ENV} must be one of {sorted(MEMORY_MODES)}, got {raw!r}"
        )
    return normalized


def _root_has_memory_payload(root: Path) -> bool:
    """Detect an existing memory payload without creating or recursively scanning it."""

    if not root.is_dir():
        return False
    if (root / "MEMORY_PACKAGE_MANIFEST.json").is_file():
        return True
    known_files = (
        root / "raw" / "dziennik.json",
        root / "raw" / "chat.html",
        root / "sqlite" / "memory_jazn.sqlite3",
        root / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3",
        root / "sqlite" / "runtime_write_v2" / "runtime_memory.sqlite3",
        root / "sqlite" / "conversation_archive_v1" / "conversation_archive_manifest.sqlite3",
    )
    if any(path.is_file() for path in known_files):
        return True
    for dirname in ("sqlite", "raw", "layered", "versioned_sources"):
        directory = root / dirname
        if not directory.is_dir():
            continue
        try:
            next(directory.iterdir())
        except (StopIteration, OSError):
            continue
        return True
    return False


@dataclass(frozen=True, slots=True)
class MemoryAvailabilityStatus:
    schema_version: str
    mode: str
    status: str
    memory_root: str
    source: str
    persistent_memory_present: bool
    persistent_memory_enabled: bool
    persistent_memory_required: bool
    required_satisfied: bool
    core_runtime_allowed: bool
    ordinary_dialogue_allowed: bool
    recall_candidate_present: bool
    external_attach_supported: bool
    canonical_host_memory_root: str
    operational_core_state_root: str
    memory_root_env: str = MEMORY_ROOT_ENV
    memory_mode_env: str = MEMORY_MODE_ENV
    truth_boundary: str = (
        "SYSTEM readiness is independent from private MEMORY in optional/off modes. "
        "Only an existing persistent memory root may enable recall/persistent-memory writes; "
        "core operational state lives under workspace_runtime/core_state and must never be "
        "presented as autobiographical recall."
    )

    @property
    def ok(self) -> bool:
        return self.required_satisfied and self.core_runtime_allowed

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "ok": self.ok}


def build_memory_availability_status(
    runtime_root: str | Path,
    *,
    mode: str | None = None,
) -> MemoryAvailabilityStatus:
    root = Path(runtime_root).expanduser().resolve()
    resolved_mode = memory_mode(mode)
    canonical = default_memory_root(root)
    legacy = legacy_memory_root(root)
    selected = resolve_memory_root(root)

    configured = str(os.environ.get(MEMORY_ROOT_ENV) or "").strip()
    if configured:
        source = "environment_override"
    elif selected == canonical:
        source = "canonical_host_memory_root"
    elif selected == legacy:
        source = "legacy_runtime_memory_root"
    else:
        source = "configured_memory_root"

    present = bool(_root_has_memory_payload(selected))
    enabled = bool(resolved_mode != "off" and present)
    required = resolved_mode == "required"
    required_satisfied = bool(not required or present)
    core_runtime_allowed = required_satisfied
    if resolved_mode == "off":
        status = "disabled_by_policy"
    elif present:
        status = "persistent_memory_present"
    elif required:
        status = "persistent_memory_required_missing"
    else:
        status = "persistent_memory_absent_optional"

    return MemoryAvailabilityStatus(
        schema_version=SCHEMA_VERSION,
        mode=resolved_mode,
        status=status,
        memory_root=str(selected),
        source=source,
        persistent_memory_present=present,
        persistent_memory_enabled=enabled,
        persistent_memory_required=required,
        required_satisfied=required_satisfied,
        core_runtime_allowed=core_runtime_allowed,
        ordinary_dialogue_allowed=core_runtime_allowed,
        recall_candidate_present=enabled,
        external_attach_supported=True,
        canonical_host_memory_root=str(canonical),
        operational_core_state_root=str(core_state_root(root)),
    )


def core_state_root(runtime_root: str | Path) -> Path:
    """Return non-memory mutable runtime state root without creating it."""

    root = Path(runtime_root).expanduser().resolve()
    return (workspace_runtime_path(root) / CORE_STATE_DIR_NAME).resolve()


def runtime_memory_storage_root(
    runtime_root: str | Path,
    *,
    mode: str | None = None,
) -> Path:
    """Return storage for runtime writers without fabricating canonical MEMORY.

    With verified/present persistent memory this is the selected memory root.
    Otherwise it is an operational core-state namespace that is intentionally
    excluded from recall discovery and MEMORY packaging.
    """

    status = build_memory_availability_status(runtime_root, mode=mode)
    if status.persistent_memory_enabled:
        return Path(status.memory_root).resolve()
    return (core_state_root(runtime_root) / CORE_MEMORY_RUNTIME_DIR_NAME).resolve()


def runtime_memory_storage_path(
    runtime_root: str | Path,
    relative: str | Path,
    *,
    mode: str | None = None,
) -> Path:
    base = runtime_memory_storage_root(runtime_root, mode=mode)
    rel = Path(relative)
    if rel.is_absolute():
        raise ValueError(f"runtime memory storage path must be relative: {relative}")
    parts = rel.parts
    if parts and parts[0].casefold() == "memory":
        rel = Path(*parts[1:])
    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"runtime memory storage path escapes storage root: {relative}") from exc
    return target


__all__ = [
    "CORE_MEMORY_RUNTIME_DIR_NAME",
    "CORE_STATE_DIR_NAME",
    "MEMORY_MODE_ENV",
    "MEMORY_MODES",
    "MemoryAvailabilityStatus",
    "build_memory_availability_status",
    "core_state_root",
    "memory_mode",
    "runtime_memory_storage_path",
    "runtime_memory_storage_root",
]
