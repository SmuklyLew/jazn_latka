#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jaźń / Łatka — generator paczek v8.5 with independent memory contract v3.

The verified v8.5 UI/system packaging core remains byte-for-byte available in
``_jazn_pack_generator_core.py``. This facade layers only the independent
memory-package v2 transport contract on top, keeping the system release path
stable while allowing memory to have its own lifecycle.
"""
from __future__ import annotations

import atexit
import contextvars
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

from latka_jazn.packaging.memory_raw_segmentation import (
    RawJsonlSegmenter,
    RawMemorySegmentationPolicy,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
try:
    from tools import _jazn_pack_generator_core as _core  # noqa: E402
    from tools._jazn_pack_generator_core import *  # type: ignore[import-not-found]  # noqa: F403,E402
except ImportError:
    _TOOL_DIR = Path(__file__).resolve().parent
    if str(_TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(_TOOL_DIR))
    import _jazn_pack_generator_core as _core  # type: ignore[no-redef]  # noqa: E402
    from _jazn_pack_generator_core import *  # type: ignore[import-not-found]  # noqa: F403,E402

GENERATOR_VERSION = "8.5"
SETTINGS_SCHEMA = "jazn_pack_generator_settings/v8.5"
MEMORY_MANIFEST_SCHEMA = "jazn_memory_package_manifest/v3"
MEMORY_FORMAT_VERSION = 3
MEMORY_RAW_SEGMENT_TARGET_BYTES = int(os.environ.get("JAZN_MEMORY_PACKAGE_RAW_SEGMENT_BYTES", str(256 * 1024 * 1024)))
MEMORY_RAW_SEGMENT_MAX_BYTES = int(os.environ.get("JAZN_MEMORY_PACKAGE_RAW_MEMBER_MAX_BYTES", str(480 * 1024 * 1024)))
MEMORY_RUNTIME_COMPATIBILITY_CONTRACT = "jazn_memory_runtime/v1"
SQLITE_HEADER = b"SQLite format 3\x00"

_core.GENERATOR_VERSION = GENERATOR_VERSION
_core.SETTINGS_SCHEMA = SETTINGS_SCHEMA
_core.MEMORY_MANIFEST_SCHEMA = MEMORY_MANIFEST_SCHEMA
_core.APP_THEME = _core.Theme(name="latka-cyan-v8.5")
__doc__ = _core.__doc__

_ORIG_COMMON_FORBIDDEN_REASON = _core.common_forbidden_reason
_ORIG_BUILD_PLAN = _core.build_plan
_ORIG_SIDECAR_PAYLOAD = _core.sidecar_payload
_ORIG_RUN_PACK_WITH_PLANS = _core.run_pack_with_plans

# Private compatibility helper used by the public entrypoint.
_paint = _core._paint

_COMBINED_BUILD: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "jazn_pack_generator_memory_v2_combined_build", default=False
)
_TEMP_COLLECTOR: contextvars.ContextVar[list[Path] | None] = contextvars.ContextVar(
    "jazn_pack_generator_memory_v2_temp_collector", default=None
)
_PLAN_TEMP_PATHS: dict[int, list[Path]] = {}
_ALL_TEMP_PATHS: set[Path] = set()


def _register_temp(path: Path) -> None:
    _ALL_TEMP_PATHS.add(path)
    collector = _TEMP_COLLECTOR.get()
    if collector is not None:
        collector.append(path)


def _cleanup_path(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    _ALL_TEMP_PATHS.discard(path)


def _bind_plan_temps(plan: Any, paths: Iterable[Path]) -> None:
    rows = [Path(path) for path in paths]
    if rows:
        _PLAN_TEMP_PATHS.setdefault(id(plan), []).extend(rows)


def _cleanup_plan(plan: Any) -> None:
    for path in _PLAN_TEMP_PATHS.pop(id(plan), []):
        _cleanup_path(path)


def cleanup_plans(plans: Iterable[Any]) -> None:
    for plan in plans:
        _cleanup_plan(plan)


def _plan_cleanup(self: Any) -> None:
    _cleanup_plan(self)


setattr(_core.PackPlan, "cleanup", _plan_cleanup)


def _cleanup_registered_temp_dirs() -> None:
    for path in list(_ALL_TEMP_PATHS):
        _cleanup_path(path)


atexit.register(_cleanup_registered_temp_dirs)


def common_forbidden_reason(relative: str) -> str | None:
    relative = _core.normalize_rel(relative)
    parts = [part.lower() for part in PurePosixPath(relative).parts]
    if any(part in _core.COMMON_FORBIDDEN_DIR_NAMES for part in parts[:-1]):
        return "immutable_repository_or_environment_directory"
    return _ORIG_COMMON_FORBIDDEN_REASON(relative)


def _new_memory_snapshot_root() -> Path:
    path = Path(tempfile.mkdtemp(prefix="jazn-memory-package-v3-"))
    _register_temp(path)
    return path


def _is_sqlite_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def _memory_database_role(relative: str) -> str:
    lowered = relative.lower()
    name = PurePosixPath(relative).name.lower()
    if "normalization_sidecar" in lowered:
        return "normalization_sidecar"
    if "conversation_archive" in lowered:
        return "conversation_archive"
    if "memory_tier" in lowered or "transactional" in lowered:
        return "memory_tier"
    if "runtime_write" in lowered or name.startswith("runtime_memory"):
        return "runtime_memory"
    if "audit" in lowered:
        return "memory_audit"
    return "sqlite_memory"


def _sqlite_schema_sha256(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_schema "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name,tbl_name"
    ).fetchall()
    raw = json.dumps(
        [list(row) for row in rows], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _inspect_sqlite_snapshot(path: Path, relative: str) -> dict[str, Any]:
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30.0) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        integrity = [
            str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()
        ]
        foreign = [
            tuple(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
        ]
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        schema_sha256 = _sqlite_schema_sha256(connection)
        table_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_schema WHERE type='table'"
            ).fetchone()[0]
        )
    if integrity != ["ok"] or foreign:
        raise _core.PackError(
            f"SQLite snapshot validation failed for {relative}: "
            f"integrity={integrity[:3]}, foreign_key_errors={len(foreign)}"
        )
    return {
        "path": relative,
        "role": _memory_database_role(relative),
        "snapshot_method": "sqlite_online_backup_api",
        "user_version": user_version,
        "application_id": application_id,
        "schema_sha256": schema_sha256,
        "table_count": table_count,
        "integrity_check": "ok",
        "foreign_key_error_count": 0,
    }


def _snapshot_sqlite_entry(
    root: Path,
    relative: str,
    snapshot_root: Path,
) -> tuple[Any, dict[str, Any]]:
    source = (root / Path(*PurePosixPath(relative).parts)).resolve()
    target = snapshot_root / Path(*PurePosixPath(relative).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".snapshot-{uuid.uuid4().hex}.tmp")
    source_uri = source.as_uri() + "?mode=ro"
    source_connection = sqlite3.connect(source_uri, uri=True, timeout=30.0)
    target_connection = sqlite3.connect(temporary, timeout=30.0)
    try:
        source_connection.execute("PRAGMA busy_timeout=30000")
        source_connection.backup(target_connection, pages=2048, sleep=0.01)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()
    os.replace(temporary, target)
    database = _inspect_sqlite_snapshot(target, relative)
    stat_result = target.stat()
    entry = _core.PlanEntry(
        relative=relative,
        source=target,
        size_bytes=stat_result.st_size,
        sha256=_core.sha256_file(target),
        classification="memory_sqlite_snapshot",
        mtime_ns=stat_result.st_mtime_ns,
    )
    database["size_bytes"] = entry.size_bytes
    database["sha256"] = entry.sha256
    return entry, database


def build_memory_plan(
    root: Path,
    version: Any,
    candidates: Sequence[str],
    excluded: list[tuple[str, str]],
    scan_method: str,
    *,
    independent_contract: bool | None = None,
) -> Any:
    if independent_contract is None:
        independent_contract = not _COMBINED_BUILD.get()
    candidates = [path for path in candidates if path != _core.MEMORY_PACKAGE_MANIFEST]
    entries: list[Any] = []
    databases: list[dict[str, Any]] = []
    raw_segments: list[dict[str, Any]] = []
    snapshot_root: Path | None = None
    snapshot_id = str(uuid.uuid4())
    created_at_utc = _core.utc_now()
    total = len(candidates)
    try:
        for index, relative in enumerate(candidates, start=1):
            source = root / Path(*PurePosixPath(relative).parts)
            if _is_sqlite_file(source):
                if snapshot_root is None:
                    snapshot_root = _new_memory_snapshot_root()
                entry, database = _snapshot_sqlite_entry(root, relative, snapshot_root)
                entries.append(entry)
                databases.append(database)
            elif (
                independent_contract
                and relative.lower().endswith(".jsonl")
                and source.stat().st_size > MEMORY_RAW_SEGMENT_TARGET_BYTES
            ):
                if snapshot_root is None:
                    snapshot_root = _new_memory_snapshot_root()
                segmenter = RawJsonlSegmenter(
                    RawMemorySegmentationPolicy(
                        target_segment_bytes=MEMORY_RAW_SEGMENT_TARGET_BYTES,
                        max_segment_bytes=MEMORY_RAW_SEGMENT_MAX_BYTES,
                    )
                )
                segmented = segmenter.segment(
                    source, source_relative=relative, staging_root=snapshot_root
                )
                raw_segments.append(segmented.to_dict())
                for segment in segmented.segments:
                    segment_source = snapshot_root / Path(*PurePosixPath(segment.package_path).parts)
                    stat_result = segment_source.stat()
                    entries.append(
                        _core.PlanEntry(
                            relative=segment.package_path,
                            source=segment_source,
                            size_bytes=stat_result.st_size,
                            sha256=segment.sha256,
                            classification="memory_raw_segment",
                            mtime_ns=stat_result.st_mtime_ns,
                        )
                    )
            else:
                entries.append(_core.hash_source_entry(root, relative, "memory_file"))
            if index % 20 == 0 or index == total:
                _core.print_progress(index, total, "Hash memory")

        files = [
            {
                "path": item.relative,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "classification": item.classification,
            }
            for item in sorted(entries, key=lambda item: item.relative)
        ]
        if independent_contract:
            payload = {
                "schema_version": MEMORY_MANIFEST_SCHEMA,
                "memory_format_version": MEMORY_FORMAT_VERSION,
                "snapshot_id": snapshot_id,
                "created_at_utc": created_at_utc,
                "generated_at_utc": created_at_utc,
                "created_with_runtime": version.full_version,
                "compatibility": {
                    "contract": MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
                    "runtime_version_is_provenance_only": True,
                    "memory_format_version": MEMORY_FORMAT_VERSION,
                    "manifest_schema": MEMORY_MANIFEST_SCHEMA,
                },
                "file_count": len(files),
                "files": files,
                "databases": sorted(
                    databases, key=lambda item: str(item.get("path") or "")
                ),
                "raw_segments": sorted(
                    raw_segments, key=lambda item: str(item.get("source_path") or "")
                ),
                "package_member_limit_bytes": MEMORY_RAW_SEGMENT_MAX_BYTES,
                "excluded_files": [
                    path for path, _ in excluded if path.startswith("memory/")
                ],
                "truth_boundary": (
                    "This manifest protects a point-in-time memory snapshot. "
                    "created_with_runtime is provenance only; runtime compatibility is "
                    "decided by the memory compatibility contract and verified database "
                    "schemas. Transient WAL/SHM, nested archives, backups and caches are "
                    "excluded. L2/L3 truth status is not changed by packaging."
                ),
            }
            manifest_builder = "independent_memory_contract_v3+sqlite_online_backup+raw_jsonl_segmentation"
        else:
            payload = {
                "schema_version": "jazn_memory_package_manifest/v1",
                "runtime_version": version.full_version,
                "generated_at_utc": created_at_utc,
                "file_count": len(files),
                "files": files,
                "excluded_files": [
                    path for path, _ in excluded if path.startswith("memory/")
                ],
                "truth_boundary": (
                    "Combined-package compatibility manifest. Memory is bound only to "
                    "the system in this same archive; standalone memory transport uses "
                    "jazn_memory_package_manifest/v2. SQLite bytes are point-in-time snapshots."
                ),
            }
            manifest_builder = "combined_memory_manifest_v1_compat+sqlite_online_backup"

        entries.append(
            _core.virtual_entry(
                _core.MEMORY_PACKAGE_MANIFEST,
                _core.serialize_json(payload),
                "memory_package_manifest",
            )
        )
        entries.sort(key=lambda item: item.relative)
        plan = _core.PackPlan(
            root=root,
            profile="memory",
            version=version,
            entries=entries,
            excluded=excluded,
            scan_method=scan_method,
            manifest_builder=manifest_builder,
            generated_at_utc=created_at_utc,
        )
        if snapshot_root is not None and _TEMP_COLLECTOR.get() is None:
            _bind_plan_temps(plan, [snapshot_root])
        return plan
    except Exception:
        if snapshot_root is not None:
            _cleanup_path(snapshot_root)
        raise


def build_plan(
    root: Path,
    profile: str,
    custom_excludes: Sequence[str],
    *,
    base_excludes: Sequence[str] | None = None,
    manual_excludes_enabled: bool = True,
    synchronize_release_metadata: bool = False,
) -> Any:
    collected: list[Path] = []
    collector_token = _TEMP_COLLECTOR.set(collected)
    combined_token = _COMBINED_BUILD.set(profile == "combined")
    try:
        plan = _ORIG_BUILD_PLAN(
            root,
            profile,
            custom_excludes,
            base_excludes=base_excludes,
            manual_excludes_enabled=manual_excludes_enabled,
            synchronize_release_metadata=synchronize_release_metadata,
        )
    except Exception:
        for path in collected:
            _cleanup_path(path)
        raise
    finally:
        _COMBINED_BUILD.reset(combined_token)
        _TEMP_COLLECTOR.reset(collector_token)
    _bind_plan_temps(plan, collected)
    if profile == "combined" and plan.manifest_builder.endswith("+memory"):
        plan.manifest_builder = (
            plan.manifest_builder[: -len("+memory")] + "+memory-v1-compat-snapshot"
        )
    return plan


def sidecar_payload(
    base_zip_name: str,
    plan: Any,
    archive_format: str,
    part_size: int,
    compression_level: int,
    outputs: Sequence[Any],
    logical_zip_sha256: str | None,
    verification: dict[str, Any],
) -> dict[str, Any]:
    payload = _ORIG_SIDECAR_PAYLOAD(
        base_zip_name,
        plan,
        archive_format,
        part_size,
        compression_level,
        outputs,
        logical_zip_sha256,
        verification,
    )
    payload["generator"] = Path(__file__).name
    payload["generator_version"] = GENERATOR_VERSION
    if plan.profile == "memory":
        payload.update(
            {
                "package_version": f"memory-format-v{MEMORY_FORMAT_VERSION}",
                "memory_manifest_schema": MEMORY_MANIFEST_SCHEMA,
                "memory_format_version": MEMORY_FORMAT_VERSION,
                "memory_compatibility_contract": MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
                "created_with_runtime": plan.version.full_version,
                "runtime_version_is_provenance_only": True,
            }
        )
    return payload


def run_pack_with_plans(options: Any, plans: Sequence[Any]) -> list[Any]:
    try:
        return _ORIG_RUN_PACK_WITH_PLANS(options, plans)
    finally:
        cleanup_plans(plans)


def show_plan_interactive(state: Any) -> None:
    plans = _core.build_preview_plans(state)
    try:
        if state.ui_mode == "kursorowy":
            _core.cursor_message_page(
                "KANONICZNY PLAN", _core.plan_summary(plans), kind="info"
            )
        else:
            for plan in plans:
                _core.print_plan(plan, show_files=False)
    finally:
        cleanup_plans(plans)


def pack_from_interactive(state: Any) -> None:
    plans = _core.build_preview_plans(state)
    if state.ui_mode == "kursorowy":
        if not _core.cursor_confirm(
            "URUCHOMIĆ PAKOWANIE?",
            _core.plan_summary(plans),
            yes_label="Pakuj",
            no_label="Anuluj",
        ):
            cleanup_plans(plans)
            _core.cursor_message_page(
                "PAKOWANIE ANULOWANE",
                "Nie utworzono ani nie nadpisano żadnej paczki.",
                kind="warn",
            )
            return
    else:
        for plan in plans:
            _core.print_plan(plan)
        if input("Rozpocząć pakowanie? [t/N]: ").strip().lower() not in {
            "t",
            "tak",
            "y",
            "yes",
        }:
            cleanup_plans(plans)
            return
    preview_hashes = {plan.profile: plan.plan_sha256() for plan in plans}
    results = run_pack_with_plans(state.to_options(), plans)
    for result in results:
        if result.plan.plan_sha256() != preview_hashes[result.profile]:
            raise _core.PackError(
                f"Hash planu zmienił się dla profilu {result.profile}."
            )
    lines: list[str] = []
    for result in results:
        lines.extend(
            [
                f"Paczka: {result.package_name}",
                f"Profil: {result.profile}",
                f"Format: {result.archive_format}",
                f"Pliki planu: {result.plan.file_count}",
                f"Woluminy: {len(result.outputs)}",
                f"Plan SHA-256: {result.plan.plan_sha256()}",
                f"Set SHA-256: {result.package_set_sha256}",
                "Pliki wynikowe:",
            ]
        )
        lines.extend(f"  ✓ {path}" for path in result.committed_paths)
        lines.extend(_core.compatibility_summary(result))
        lines.append("")
    if state.ui_mode == "kursorowy":
        _core.cursor_message_page(
            "PAKOWANIE ZAKOŃCZONE POPRAWNIE",
            lines,
            kind="ok",
            subtitle="Wynik pozostaje widoczny do naciśnięcia Enter lub Esc",
        )
    else:
        _core.print_results(results)


_core.common_forbidden_reason = common_forbidden_reason
_core.build_memory_plan = build_memory_plan
_core.build_plan = build_plan
_core.sidecar_payload = sidecar_payload
_core.run_pack_with_plans = run_pack_with_plans
_core.show_plan_interactive = show_plan_interactive
_core.pack_from_interactive = pack_from_interactive
setattr(_core, "cleanup_plans", cleanup_plans)

globals().update(
    {
        "GENERATOR_VERSION": GENERATOR_VERSION,
        "SETTINGS_SCHEMA": SETTINGS_SCHEMA,
        "MEMORY_MANIFEST_SCHEMA": MEMORY_MANIFEST_SCHEMA,
        "MEMORY_FORMAT_VERSION": MEMORY_FORMAT_VERSION,
        "MEMORY_RUNTIME_COMPATIBILITY_CONTRACT": MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
        "common_forbidden_reason": common_forbidden_reason,
        "build_memory_plan": build_memory_plan,
        "build_plan": build_plan,
        "sidecar_payload": sidecar_payload,
        "run_pack_with_plans": run_pack_with_plans,
        "show_plan_interactive": show_plan_interactive,
        "pack_from_interactive": pack_from_interactive,
        "cleanup_plans": cleanup_plans,
    }
)


def main(argv: Sequence[str] | None = None) -> int:
    return int(_core.main(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(_core._paint("\nPrzerwano przez użytkownika.", _core.ANSI_YELLOW, stream=sys.stderr), file=sys.stderr)
        raise SystemExit(130)
    except _core.PackError as exc:
        print(_core._paint(f"BŁĄD: {exc}", _core.ANSI_RED, _core.ANSI_BOLD, stream=sys.stderr), file=sys.stderr)
        raise SystemExit(2)
