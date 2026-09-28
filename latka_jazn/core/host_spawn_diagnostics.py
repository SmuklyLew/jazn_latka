from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from latka_jazn.memory.availability import memory_mode
from latka_jazn.memory.living_memory_gateway import memory_readiness_policy
from latka_jazn.memory.memory_root import (
    MEMORY_ROOT_ENV,
    resolve_memory_root_diagnostic,
)
from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("host_spawn_diagnostics")


def _optional_process_int(name: str) -> int | None:
    func = getattr(os, name, None)
    if not callable(func):
        return None
    try:
        return int(func())
    except (OSError, TypeError, ValueError):
        return None


def _supplementary_groups() -> list[int] | None:
    func = getattr(os, "getgroups", None)
    if not callable(func):
        return None
    try:
        return [int(value) for value in func()]
    except (OSError, TypeError, ValueError):
        return None


def build_host_spawn_diagnostics(root: str | Path) -> dict[str, Any]:
    """Collect post-spawn host evidence without reading private MEMORY content."""

    runtime_root = Path(root).expanduser().resolve()
    memory_resolution = resolve_memory_root_diagnostic(runtime_root)
    selected = Path(str(memory_resolution["selected"])).expanduser().resolve()
    sqlite_dir = selected / "sqlite"
    canonical_database = sqlite_dir / "memory_jazn.sqlite3"

    native_probe = probe_unified_memory_database(canonical_database)

    memory_payload = {
        **memory_resolution,
        "mode": memory_mode(),
        "readiness_policy": memory_readiness_policy(),
        "configured_root": os.environ.get(MEMORY_ROOT_ENV),
        "resolved_root": str(selected),
        "root_readable": bool(selected.exists() and os.access(selected, os.R_OK)),
        "root_writable": bool(selected.exists() and os.access(selected, os.W_OK)),
        "sqlite_directory": str(sqlite_dir),
        "sqlite_directory_exists": sqlite_dir.is_dir(),
        "sqlite_directory_readable": bool(
            sqlite_dir.is_dir() and os.access(sqlite_dir, os.R_OK)
        ),
        "sqlite_directory_writable": bool(
            sqlite_dir.is_dir() and os.access(sqlite_dir, os.W_OK)
        ),
        "canonical_database": str(canonical_database),
        "canonical_database_exists": canonical_database.is_file(),
        "canonical_database_readable": bool(
            canonical_database.is_file() and os.access(canonical_database, os.R_OK)
        ),
        "private_content_read": False,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "process_created": True,
        "pid": os.getpid(),
        "platform": sys.platform,
        "cwd": str(Path.cwd().resolve()),
        "runtime_root": str(runtime_root),
        "effective_uid": _optional_process_int("geteuid")
        if hasattr(os, "geteuid")
        else _optional_process_int("getuid"),
        "effective_gid": _optional_process_int("getegid")
        if hasattr(os, "getegid")
        else _optional_process_int("getgid"),
        "supplementary_groups": _supplementary_groups(),
        "memory": memory_payload,
        "native_memory_probe": native_probe,
        "truth_boundary": (
            "This command is post-spawn evidence only. Its existence proves a process "
            "was created, but not daemon readiness or an accepted visible Jaźń turn. "
            "It reports metadata and readiness probes without returning private MEMORY content."
        ),
    }
