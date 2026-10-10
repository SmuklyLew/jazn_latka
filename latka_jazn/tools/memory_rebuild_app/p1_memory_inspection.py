"""Read-only P1 inspection: source, target, rebuild staging and host MEMORY."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from latka_jazn.memory.database_identity import inspect_memory_database
from latka_jazn.memory.memory_root import resolve_memory_root_diagnostic

from .canonical_rebuild import canonical_database_path
from .models import RebuildProject
from .unified_schema import CANONICAL_DATABASE_NAME

SCHEMA = "jazn_memory_studio_p1_inspection/v1"
MAX_STAGING_ENTRIES = 32


def _has_symlink(path: Path) -> bool:
    return any(p.is_symlink() for p in (path, *path.parents))


def _code(value: object) -> str:
    # Never leak a private filename or a SQLite exception string.
    candidate = str(value).split(":", 1)[0].lower().strip()
    return candidate if re.fullmatch(r"[a-z_]{3,60}", candidate) else "inspection_failed"


def _inspect_db(path: Path | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "not_selected", "exists": False, "schema_kind": "unknown",
        "schema_compatible": False, "size_bytes": None, "issues": [],
        "read_only": True,
    }
    if path is None:
        return result
    if _has_symlink(path):
        return {**result, "status": "unsafe_path", "issues": ["symlink_rejected"]}
    if not path.exists():
        return {**result, "status": "missing"}
    if not path.is_file() or path.name != CANONICAL_DATABASE_NAME:
        return {**result, "status": "invalid", "issues": ["invalid_database_file"]}
    wal, shm = Path(str(path) + "-wal"), Path(str(path) + "-shm")
    if _has_symlink(wal) or _has_symlink(shm):
        return {**result, "status": "unsafe_path", "issues": ["unsafe_sidecar"]}
    if wal.exists() != shm.exists():
        return {**result, "status": "unverified", "issues": ["incomplete_wal_pair"]}
    try:
        with path.open("rb") as stream:
            header = stream.read(20)
        if (header[:16] == b"SQLite format 3\x00"
                and len(header) >= 20 and header[18] == 2 and not wal.exists()):
            return {**result, "status": "unverified", "issues": ["wal_snapshot_required"]}
        info = inspect_memory_database(path)
        compatible = info.get("compatible") is True
        return {
            **result, "status": "compatible" if compatible else "incompatible",
            "exists": True, "schema_kind": str(info.get("kind") or "unknown"),
            "schema_compatible": compatible, "size_bytes": path.stat().st_size,
            "issues": sorted({_code(v) for v in info.get("issues") or []}),
        }
    except (OSError, ValueError) as exc:
        return {**result, "status": "unverified", "issues": [_code(type(exc).__name__)]}


def _inspect_sources(project: RebuildProject) -> dict[str, Any]:
    present = missing = unsafe = 0
    sources = project.enabled_sources()
    for source in sources:
        path = Path(source.path).expanduser()
        if _has_symlink(path):
            unsafe += 1
        elif path.is_file():
            present += 1
        else:
            missing += 1
    directory = Path(project.source_directory).expanduser() if project.source_directory else None
    location = ("not_configured" if directory is None else
                "unsafe_path" if _has_symlink(directory) else
                "present" if directory.is_dir() else "missing")
    return {
        "source_count": len(sources), "present": present, "missing": missing,
        "unsafe": unsafe, "source_directory": location,
        "source_contents_read": False, "source_approval_verified": False,
        "inventory_present": bool(present and not missing and not unsafe),
    }


def _inspect_staging(target: Path) -> dict[str, Any]:
    root = target.parent.parent / ".rebuild_staging"
    base = {"status": "missing", "candidates": 0, "database": _inspect_db(None),
            "published": False}
    if _has_symlink(root):
        return {**base, "status": "unsafe_path"}
    if not root.exists():
        return base
    if not root.is_dir():
        return {**base, "status": "invalid"}
    try:
        entries = list(root.iterdir())
    except OSError:
        return {**base, "status": "unverified"}
    if len(entries) > MAX_STAGING_ENTRIES:
        return {**base, "status": "bounded_scan_required", "candidates": len(entries)}
    if any(_has_symlink(item) or not item.is_dir() for item in entries):
        return {**base, "status": "unsafe_path", "candidates": len(entries)}
    candidates = [item / "sqlite" / CANONICAL_DATABASE_NAME for item in entries
                  if (item / "sqlite" / CANONICAL_DATABASE_NAME).exists()]
    if not candidates:
        return {**base, "status": "empty", "candidates": 0}
    if len(candidates) != 1:
        return {**base, "status": "ambiguous", "candidates": len(candidates)}
    return {**base, "status": "candidate_inspected", "candidates": 1,
            "database": _inspect_db(candidates[0])}


def _inspect_host_selection(system_root: Path) -> tuple[dict[str, Any], Path | None]:
    diagnostic = resolve_memory_root_diagnostic(system_root)
    selected = Path(str(diagnostic["selected"])).expanduser()
    base = {"selection_source": diagnostic["selection_source"],
            "active_daemon_verified": False, "database": _inspect_db(None)}
    if _has_symlink(selected):
        return {**base, "status": "unsafe_path"}, None
    choices = [selected / "sqlite" / CANONICAL_DATABASE_NAME,
               selected / CANONICAL_DATABASE_NAME]
    matching = [p for p in choices if p.exists()]
    if len(matching) > 1:
        return {**base, "status": "ambiguous"}, None
    db = matching[0] if matching else choices[0]
    return {**base, "status": "host_resolved_only",
            "database": _inspect_db(db)}, db


def inspect_memory_layout(
    project: RebuildProject, *, system_root: str | Path,
    target_database: str | Path | None = None,
) -> dict[str, Any]:
    """No writes, hashes, import, activation, ProjectStore or runtime lifecycle."""
    target = Path(target_database).expanduser() if target_database is not None else canonical_database_path(project.target_root)
    sources = _inspect_sources(project)
    target_info = _inspect_db(target)
    staging = _inspect_staging(target)
    host, host_db = _inspect_host_selection(Path(system_root).expanduser())
    alias = target.resolve() == host_db.resolve() if host_db is not None else None
    blockers: list[str] = []
    if not sources["inventory_present"]:
        blockers.append("sources_not_verified")
    if not target_info["schema_compatible"]:
        blockers.append("target_schema_not_verified")
    if staging["status"] not in {"missing", "empty", "candidate_inspected"}:
        blockers.append("staging_ambiguous_or_unsafe")
    if alias:
        blockers.append("target_aliases_host_selection")
    if not host["database"]["schema_compatible"]:
        blockers.append("host_memory_schema_not_verified")
    return {
        "schema": SCHEMA,
        "roles": {"source": sources, "target": target_info,
                  "staging": staging, "host_selected_memory": host},
        "comparison": {
            "target_matches_host_selected_path": alias,
            "database_content_equal": None, "lineage_equal": None,
            "staging_promoted": False,
        },
        "readiness": {
            "target_schema_compatible": target_info["schema_compatible"],
            "runtime_ready": None, "continuity_ready": None,
            "activation_ready": False, "publishing_authorized": False,
            "blockers": blockers or ["runtime_and_publication_gates_not_verified"],
        },
        "read_only": True, "private_content_read": False,
        "memory_modified": False,
        "truth_boundary": (
            "Source files, schema and selected MEMORY are NOT proof of "
            "active daemon readiness, equivalence, continuity or publication rights."
        ),
    }


__all__ = ["SCHEMA", "inspect_memory_layout"]
