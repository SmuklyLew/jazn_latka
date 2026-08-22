from __future__ import annotations

import errno
import os
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from latka_jazn.bootstrap.chatgpt_recovery import runtime_preflight
from latka_jazn.config import JaznConfig
from latka_jazn.core.package_integrity_manifest import sha256_file
from latka_jazn.core.runtime_daemon import status_daemon
from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.memory.runtime_memory_install import initialize_transactional_memory_store
from latka_jazn.packaging.split_zip_package import (
    extract_independent_zip_set_resumable, extract_joined_zip_resumable, infer_base_zip_name,
    join_split_package_to_zip, load_package_expectations, load_package_set_metadata,
    resolve_renamed_package_parts, test_joined_zip, verify_extracted_zip_set, verify_extracted_zip_tree,
)
from latka_jazn.tools.active_extraction_cache import write_active_runtime_marker
from .memory_package_manifest import verify_memory_package_manifest
from .memory_package_source import MemoryPackageSourceError, materialize_r2_memory_package
from .memory_raw_segmentation import RawJsonlSegmenter
from .memory_package_types import (
    MEMORY_ATTACH_MARKER_PATH, MEMORY_ATTACH_SCHEMA_VERSION, MEMORY_MANIFEST_SCHEMA_V1, MEMORY_MANIFEST_SCHEMA_V3, MemoryAttachResult, TRUTH_BOUNDARY,
    read_json, write_json_atomic,
)


def _safe_remove_tree(path: Path) -> None:
    if path.exists(): shutil.rmtree(path)


def _infer_memory_base_zip_name(parts_dir: Path, base_zip_name: str | None = None) -> str:
    parts_dir = Path(parts_dir).expanduser().resolve()
    if base_zip_name: return infer_base_zip_name(parts_dir, base_zip_name)
    names: set[str] = set()
    for candidate in sorted(parts_dir.glob("*.json")):
        if ".package" not in candidate.name: continue
        payload = read_json(candidate)
        if not payload or str(payload.get("profile") or "").strip().lower() != "memory": continue
        declared = str(payload.get("package_name") or "").strip()
        if declared: names.add(declared)
    if len(names) == 1: return infer_base_zip_name(parts_dir, next(iter(names)))
    if len(names) > 1: raise ValueError("W katalogu jest więcej niż jedna paczka profilu memory; podaj --zip-name.")
    return infer_base_zip_name(parts_dir)


def _memory_only(root: Path) -> tuple[bool, list[str]]:
    extras = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not p.relative_to(root).as_posix().startswith("memory/")]
    return not extras, sorted(extras)


def attach_memory_package(
    runtime_root: Path, *, parts_dir: Path | None = None, base_zip_name: str | None = None,
    work_dir: Path | None = None, time_budget_seconds: float | None = 25.0,
    run_crc: bool = True, force_reextract: bool = False,
    r2_prefix: str | None = None, r2_bucket: str | None = None,
    r2_endpoint_url: str | None = None, r2_region_name: str = "auto",
    r2_client: Any | None = None,
) -> MemoryAttachResult:
    runtime_root = Path(runtime_root).expanduser().resolve()
    workspace = workspace_runtime_path(runtime_root)
    work_dir = Path(work_dir).expanduser().resolve() if work_dir else workspace / "memory_attach"
    report: dict[str, Any] = {
        "runtime_root": str(runtime_root),
        "parts_dir": str(Path(parts_dir).expanduser().resolve()) if parts_dir is not None else None,
        "r2_prefix": r2_prefix,
        "work_dir": str(work_dir),
        "started_at_epoch": time.time(),
    }
    try:
        preflight = runtime_preflight(runtime_root); report["runtime_preflight"] = preflight.to_dict()
        if not (preflight.structure_ok and preflight.manifest_ok and preflight.provenance_ok):
            return MemoryAttachResult(False, "runtime_not_verified", str(runtime_root), report, exit_code=13)
        daemon = status_daemon(JaznConfig(root=runtime_root)); report["daemon_status_before"] = daemon
        if daemon.get("active_state") in {"active_trusted", "active_degraded"}:
            return MemoryAttachResult(False, "runtime_active_attach_blocked", str(runtime_root), report, exit_code=12)
        local_requested = parts_dir is not None
        cloud_requested = bool(str(r2_prefix or "").strip())
        if local_requested == cloud_requested:
            return MemoryAttachResult(False, "memory_source_invalid", str(runtime_root), report, exit_code=14)
        if cloud_requested:
            cloud_stage = workspace / "memory_attach_sources" / "r2" / "current"
            _safe_remove_tree(cloud_stage)
            materialized = materialize_r2_memory_package(
                runtime_root,
                key_prefix=str(r2_prefix),
                bucket=r2_bucket,
                endpoint_url=r2_endpoint_url,
                region_name=r2_region_name,
                work_dir=cloud_stage,
                client=r2_client,
            )
            parts_dir = materialized.parts_dir
            report["memory_package_source"] = materialized.report
            report["parts_dir"] = str(parts_dir)
        else:
            assert parts_dir is not None
            parts_dir = Path(parts_dir).expanduser().resolve()
            report["memory_package_source"] = {
                "source_kind": "local_directory",
                "parts_dir": str(parts_dir),
                "truth_boundary": "Local package bytes still require the complete memory attach verification pipeline.",
            }
        zip_name = _infer_memory_base_zip_name(parts_dir, base_zip_name); report["base_zip_name"] = zip_name
        package_set = load_package_set_metadata(parts_dir, zip_name); report["package_set"] = package_set
        if package_set.get("source") != "package.json" or str(package_set.get("profile") or "").lower() != "memory":
            return MemoryAttachResult(False, "memory_package_profile_rejected", str(runtime_root), report, exit_code=14)
        work_dir.mkdir(parents=True, exist_ok=True)
        expected, expected_full_sha, source = load_package_expectations(parts_dir, zip_name)
        report.update({"expectations_source": source, "expected_full_sha256": expected_full_sha})
        canonical = work_dir / "canonical_parts"
        if force_reextract: _safe_remove_tree(canonical)
        report["part_resolution"] = resolve_renamed_package_parts(parts_dir, expected, canonical_dir=canonical, skip_part_hash=False)
        archive_format = str(package_set.get("archive_format") or "binary").strip().lower()
        independent: list[Path] = []; joined: Path | None = None
        if archive_format == "independent":
            independent = [canonical / part.filename for part in expected]
            volumes = [test_joined_zip(path, run_crc=run_crc) for path in independent]
            zip_report = {"ok": all(row.get("ok") for row in volumes), "archive_format": "independent", "volumes": volumes}
        elif archive_format == "binary":
            joined = join_split_package_to_zip(canonical, zip_name, zip_out=work_dir / zip_name, force=True, keep_existing=False)
            zip_report = test_joined_zip(joined, run_crc=run_crc)
        else: raise ValueError(f"unsupported archive_format:{archive_format}")
        report["zip_test"] = zip_report
        if zip_report.get("ok") is not True: return MemoryAttachResult(False, "memory_archive_verification_failed", str(runtime_root), report, exit_code=15)
        staging = work_dir / "staging"
        if force_reextract: _safe_remove_tree(staging)
        extraction = (
            extract_independent_zip_set_resumable(independent, staging, progress_path=work_dir / "extract-progress.json", time_budget_seconds=time_budget_seconds)
            if archive_format == "independent" else
            extract_joined_zip_resumable(joined, staging, progress_path=work_dir / "extract-progress.json", time_budget_seconds=time_budget_seconds)  # type: ignore[arg-type]
        )
        report["extraction"] = extraction
        if extraction.get("pending"): return MemoryAttachResult(False, "memory_extracting_pending", str(runtime_root), report, pending=True, exit_code=75)
        fs_report = verify_extracted_zip_set(independent, staging, reject_extra_files=True) if archive_format == "independent" else verify_extracted_zip_tree(joined, staging, reject_extra_files=True)  # type: ignore[arg-type]
        report["filesystem_verification"] = fs_report
        if fs_report.get("ok") is not True: return MemoryAttachResult(False, "memory_archive_verification_failed", str(runtime_root), report, exit_code=15)
        only, extras = _memory_only(staging); report["memory_only_tree"] = {"ok": only, "extra_paths": extras}
        if not only: return MemoryAttachResult(False, "memory_package_contains_non_memory_files", str(runtime_root), report, exit_code=14)
        manifest = verify_memory_package_manifest(staging, runtime_root=runtime_root, require_runtime_match=False); report["memory_manifest_verification"] = manifest
        if manifest.get("ok") is not True: return MemoryAttachResult(False, "memory_manifest_verification_failed", str(runtime_root), report, exit_code=15)
        if manifest.get("manifest_schema") == MEMORY_MANIFEST_SCHEMA_V3:
            manifest_payload = read_json(staging / "memory" / "MEMORY_PACKAGE_MANIFEST.json") or {}
            raw_descriptors = manifest_payload.get("raw_segments")
            materialized: list[dict[str, Any]] = []
            if isinstance(raw_descriptors, list):
                for descriptor in raw_descriptors:
                    if not isinstance(descriptor, dict):
                        continue
                    target = RawJsonlSegmenter.materialize_descriptor(
                        staging, descriptor, remove_segments=True
                    )
                    materialized.append({
                        "source_path": descriptor.get("source_path"),
                        "materialized_path": str(target),
                        "source_size_bytes": descriptor.get("source_size_bytes"),
                        "source_sha256": descriptor.get("source_sha256"),
                        "segments_removed_after_verified_materialization": True,
                    })
            report["raw_segment_materialization"] = {
                "ok": True,
                "count": len(materialized),
                "items": materialized,
                "truth_boundary": (
                    "Logical JSONL segmentation exists only in the verified sandbox transport. "
                    "Attach reconstructs the original local memory file byte-for-byte before activation."
                ),
            }
        source_memory = staging / "memory"
        if not source_memory.is_dir(): return MemoryAttachResult(False, "memory_payload_missing", str(runtime_root), report, exit_code=15)
        transaction_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        backup_memory = workspace / "memory_attach_backups" / transaction_id / "memory"; target_memory = runtime_root / "memory"
        had_previous = target_memory.exists(); installed_new = False
        try:
            if had_previous:
                backup_memory.parent.mkdir(parents=True, exist_ok=False); os.replace(target_memory, backup_memory)
            try: os.replace(source_memory, target_memory)
            except OSError as move_exc:
                if move_exc.errno != errno.EXDEV: raise
                shutil.copytree(source_memory, target_memory)
            installed_new = True
            transactional = initialize_transactional_memory_store(runtime_root); report["transactional_memory_initialization"] = transactional
            if transactional.get("ok") is not True: raise RuntimeError("transactional_memory_initialization_failed")
        except Exception:
            if target_memory.exists():
                if installed_new:
                    failed = workspace / "memory_attach_failed" / transaction_id
                    failed.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target_memory, failed)
                    report["failed_memory_preserved_at"] = str(failed)
                else:
                    shutil.rmtree(target_memory, ignore_errors=True)
            if had_previous and backup_memory.exists():
                os.replace(backup_memory, target_memory)
            raise
        marker = {
            "schema_version": MEMORY_ATTACH_SCHEMA_VERSION,
            "attached_at_utc": datetime.now(timezone.utc).isoformat(), "runtime_root": str(runtime_root),
            "runtime_version": preflight.version, "package_name": zip_name, "package_profile": "memory",
            "memory_manifest_schema": manifest.get("manifest_schema"), "memory_format_version": manifest.get("memory_format_version"),
            "created_with_runtime": manifest.get("created_with_runtime"), "runtime_version_is_provenance_only": manifest.get("runtime_version_is_provenance_only"),
            "memory_manifest_sha256": sha256_file(target_memory / "MEMORY_PACKAGE_MANIFEST.json"),
            "previous_memory_backup": str(backup_memory) if had_previous and backup_memory.exists() else None,
            "recovery_recommended": manifest.get("manifest_schema") == MEMORY_MANIFEST_SCHEMA_V1, "truth_boundary": TRUTH_BOUNDARY,
        }
        marker_path = runtime_root / MEMORY_ATTACH_MARKER_PATH; write_json_atomic(marker_path, marker)
        report.update({"memory_attach_marker": marker, "memory_attach_marker_path": str(marker_path), "active_runtime_marker": write_active_runtime_marker(runtime_root, action="chatgpt_memory_attach_verified")})
        return MemoryAttachResult(True, "memory_attached_inactive", str(runtime_root), report, exit_code=0)
    except MemoryPackageSourceError as exc: code, etype, detail = "memory_source_materialization_failed", type(exc).__name__, str(exc)
    except PermissionError as exc: code, etype, detail = "memory_attach_path_unwritable", type(exc).__name__, str(exc)
    except FileNotFoundError as exc: code, etype, detail = "memory_package_source_missing", type(exc).__name__, str(exc)
    except ValueError as exc: code, etype, detail = "memory_package_contract_invalid", type(exc).__name__, str(exc)
    except sqlite3.Error as exc: code, etype, detail = "memory_package_sqlite_validation_failed", type(exc).__name__, str(exc)
    except OSError as exc: code, etype, detail = "memory_attach_io_error", type(exc).__name__, str(exc)
    except Exception as exc: code, etype, detail = "memory_attach_failed", type(exc).__name__, str(exc)
    report["error"] = {"code": code, "type": etype, "detail": detail}
    return MemoryAttachResult(False, "memory_attach_blocked", str(runtime_root), report, exit_code=17)
