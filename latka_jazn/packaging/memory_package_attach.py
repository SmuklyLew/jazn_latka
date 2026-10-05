from __future__ import annotations

import errno
import os
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from latka_jazn.bootstrap.chatgpt_recovery import runtime_preflight
from latka_jazn.config import JaznConfig
from latka_jazn.core.package_integrity_manifest import sha256_file
from latka_jazn.core.runtime_daemon import status_daemon
from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.memory.memory_root import resolve_memory_root
from latka_jazn.memory.runtime_memory_install import initialize_transactional_memory_store
from latka_jazn.packaging.split_zip_package import infer_base_zip_name
from latka_jazn.tools.active_extraction_cache import write_active_runtime_marker
from .memory_package_manifest import verify_memory_package_manifest
from .memory_streaming_transport import (
    MemoryStreamingTransportError,
    stream_extract_verified_memory_package,
)
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


@dataclass(frozen=True)
class _VerifiedMemoryPackage:
    zip_name: str
    staging: Path
    manifest: dict[str, Any]
    raw_segments_materialized: bool = False


def _resolve_memory_source(
    runtime_root: Path,
    workspace: Path,
    *,
    parts_dir: Path | None,
    r2_prefix: str | None,
    r2_bucket: str | None,
    r2_endpoint_url: str | None,
    r2_region_name: str,
    r2_client: Any | None,
    report: dict[str, Any],
) -> tuple[Path | None, MemoryAttachResult | None]:
    local_requested = parts_dir is not None
    cloud_requested = bool(str(r2_prefix or "").strip())
    if local_requested == cloud_requested:
        return None, MemoryAttachResult(
            False, "memory_source_invalid", str(runtime_root), report, exit_code=14
        )

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
        resolved_parts_dir = materialized.parts_dir
        report["memory_package_source"] = materialized.report
        report["parts_dir"] = str(resolved_parts_dir)
        return resolved_parts_dir, None

    assert parts_dir is not None
    resolved_parts_dir = Path(parts_dir).expanduser().resolve()
    report["memory_package_source"] = {
        "source_kind": "local_directory",
        "parts_dir": str(resolved_parts_dir),
        "truth_boundary": "Local package bytes still require the complete memory attach verification pipeline.",
    }
    return resolved_parts_dir, None


def _verify_and_extract_memory_package(
    runtime_root: Path,
    parts_dir: Path,
    *,
    base_zip_name: str | None,
    work_dir: Path,
    time_budget_seconds: float | None,
    run_crc: bool,
    force_reextract: bool,
    report: dict[str, Any],
    package_sidecar: Mapping[str, Any] | None = None,
) -> _VerifiedMemoryPackage | MemoryAttachResult:
    if package_sidecar is not None:
        zip_name = str(package_sidecar.get("package_name") or "").strip()
        if not zip_name:
            return MemoryAttachResult(
                False,
                "memory_package_profile_rejected",
                str(runtime_root),
                report,
                exit_code=14,
            )
    else:
        zip_name = _infer_memory_base_zip_name(parts_dir, base_zip_name)

    target_memory = resolve_memory_root(runtime_root, prefer_existing_legacy=False)
    streaming = stream_extract_verified_memory_package(
        runtime_root,
        parts_dir,
        target_memory_root=target_memory,
        base_zip_name=zip_name,
        package_sidecar=package_sidecar,
        time_budget_seconds=time_budget_seconds,
        force_reextract=force_reextract,
    )
    report["streaming_transport"] = streaming
    report["base_zip_name"] = zip_name
    report["package_set"] = streaming.get("package_set")
    report["part_resolution"] = streaming.get("part_resolution")
    report["disk_preflight"] = streaming.get("disk_preflight")
    report["run_crc_requested"] = bool(run_crc)
    report["crc_policy"] = "always_verified_while_streaming"
    report["work_dir"] = str(work_dir)
    if streaming.get("pending") is True:
        return MemoryAttachResult(
            False,
            "memory_extracting_pending",
            str(runtime_root),
            report,
            pending=True,
            exit_code=75,
        )
    if streaming.get("ok") is not True:
        return MemoryAttachResult(
            False,
            "memory_archive_verification_failed",
            str(runtime_root),
            report,
            exit_code=15,
        )

    staging = Path(str(streaming["staging"])).expanduser().resolve()
    only, extras = _memory_only(staging)
    report["memory_only_tree"] = {"ok": only, "extra_paths": extras}
    if not only:
        return MemoryAttachResult(
            False,
            "memory_package_contains_non_memory_files",
            str(runtime_root),
            report,
            exit_code=14,
        )

    raw_segments_materialized = bool(streaming.get("raw_segments_materialized"))
    manifest = verify_memory_package_manifest(
        staging,
        runtime_root=runtime_root,
        require_runtime_match=False,
        installed_raw_segments=raw_segments_materialized,
    )
    report["memory_manifest_verification"] = manifest
    if manifest.get("ok") is not True:
        return MemoryAttachResult(
            False,
            "memory_manifest_verification_failed",
            str(runtime_root),
            report,
            exit_code=15,
        )
    return _VerifiedMemoryPackage(
        zip_name=zip_name,
        staging=staging,
        manifest=manifest,
        raw_segments_materialized=raw_segments_materialized,
    )

def _materialize_raw_segments(
    staging: Path,
    manifest: dict[str, Any],
    report: dict[str, Any],
) -> None:
    if manifest.get("manifest_schema") != MEMORY_MANIFEST_SCHEMA_V3:
        return
    manifest_payload = read_json(staging / "memory" / "MEMORY_PACKAGE_MANIFEST.json") or {}
    raw_descriptors = manifest_payload.get("raw_segments")
    materialized: list[dict[str, Any]] = []
    if isinstance(raw_descriptors, list):
        for descriptor in raw_descriptors:
            if not isinstance(descriptor, dict):
                continue
            target = RawJsonlSegmenter.materialize_descriptor(
                staging,
                descriptor,
                remove_segments=True,
            )
            materialized.append(
                {
                    "source_path": descriptor.get("source_path"),
                    "materialized_path": str(target),
                    "source_size_bytes": descriptor.get("source_size_bytes"),
                    "source_sha256": descriptor.get("source_sha256"),
                    "segments_removed_after_verified_materialization": True,
                }
            )
    report["raw_segment_materialization"] = {
        "ok": True,
        "count": len(materialized),
        "items": materialized,
        "truth_boundary": (
            "Logical JSONL segmentation exists only in the verified sandbox transport. "
            "Attach reconstructs the original local memory file byte-for-byte before activation."
        ),
    }


def _install_memory_tree(
    runtime_root: Path,
    workspace: Path,
    source_memory: Path,
    report: dict[str, Any],
) -> tuple[Path, bool]:
    transaction_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    target_memory = resolve_memory_root(runtime_root, prefer_existing_legacy=False)
    target_memory.parent.mkdir(parents=True, exist_ok=True)
    backup_memory = (
        target_memory.parent
        / ".memory-backups"
        / transaction_id
        / target_memory.name
    )
    failed_memory = target_memory.parent / ".memory-failed" / transaction_id
    previous_memory = resolve_memory_root(runtime_root, prefer_existing_legacy=True)
    had_previous = previous_memory.exists()
    installed_new = False
    report["memory_root"] = str(target_memory)
    report["previous_memory_root"] = str(previous_memory) if had_previous else None
    report["memory_install_strategy"] = "same_filesystem_atomic_replace_no_copy_fallback"
    report["workspace"] = str(workspace)
    try:
        if had_previous:
            backup_memory.parent.mkdir(parents=True, exist_ok=False)
            try:
                os.replace(previous_memory, backup_memory)
            except OSError as move_exc:
                if move_exc.errno == errno.EXDEV:
                    raise OSError(
                        errno.EXDEV,
                        "existing MEMORY and rollback directory are on different filesystems; "
                        "copy fallback is disabled",
                    ) from move_exc
                raise
        try:
            os.replace(source_memory, target_memory)
        except OSError as move_exc:
            if move_exc.errno == errno.EXDEV:
                raise OSError(
                    errno.EXDEV,
                    "MEMORY staging must share the target filesystem; copy fallback is disabled",
                ) from move_exc
            raise
        installed_new = True
        transactional = initialize_transactional_memory_store(runtime_root)
        report["transactional_memory_initialization"] = transactional
        if transactional.get("ok") is not True:
            raise RuntimeError("transactional_memory_initialization_failed")
    except Exception:
        if target_memory.exists():
            if installed_new:
                failed_memory.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target_memory, failed_memory)
                report["failed_memory_preserved_at"] = str(failed_memory)
            else:
                shutil.rmtree(target_memory, ignore_errors=True)
        if had_previous and backup_memory.exists():
            previous_memory.parent.mkdir(parents=True, exist_ok=True)
            os.replace(backup_memory, previous_memory)
        raise
    return backup_memory, had_previous

def _finalize_memory_attach(
    runtime_root: Path,
    *,
    runtime_version: str,
    zip_name: str,
    manifest: dict[str, Any],
    backup_memory: Path,
    had_previous: bool,
    report: dict[str, Any],
) -> MemoryAttachResult:
    target_memory = resolve_memory_root(runtime_root, prefer_existing_legacy=False)
    marker = {
        "schema_version": MEMORY_ATTACH_SCHEMA_VERSION,
        "attached_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_root": str(runtime_root),
        "memory_root": str(target_memory),
        "runtime_version": runtime_version,
        "package_name": zip_name,
        "package_profile": "memory",
        "memory_manifest_schema": manifest.get("manifest_schema"),
        "memory_format_version": manifest.get("memory_format_version"),
        "created_with_runtime": manifest.get("created_with_runtime"),
        "runtime_version_is_provenance_only": manifest.get("runtime_version_is_provenance_only"),
        "memory_manifest_sha256": sha256_file(target_memory / "MEMORY_PACKAGE_MANIFEST.json"),
        "previous_memory_backup": str(backup_memory) if had_previous and backup_memory.exists() else None,
        "recovery_recommended": manifest.get("manifest_schema") == MEMORY_MANIFEST_SCHEMA_V1,
        "truth_boundary": TRUTH_BOUNDARY,
    }
    marker_path = runtime_root / MEMORY_ATTACH_MARKER_PATH
    write_json_atomic(marker_path, marker)
    report.update(
        {
            "memory_attach_marker": marker,
            "memory_attach_marker_path": str(marker_path),
            "active_runtime_marker": write_active_runtime_marker(
                runtime_root,
                action="chatgpt_memory_attach_verified",
            ),
        }
    )
    return MemoryAttachResult(
        True,
        "memory_attached_inactive",
        str(runtime_root),
        report,
        exit_code=0,
    )


def attach_memory_package(
    runtime_root: Path,
    *,
    parts_dir: Path | None = None,
    base_zip_name: str | None = None,
    work_dir: Path | None = None,
    time_budget_seconds: float | None = 25.0,
    run_crc: bool = True,
    force_reextract: bool = False,
    package_sidecar: Mapping[str, Any] | None = None,
    r2_prefix: str | None = None,
    r2_bucket: str | None = None,
    r2_endpoint_url: str | None = None,
    r2_region_name: str = "auto",
    r2_client: Any | None = None,
) -> MemoryAttachResult:
    runtime_root = Path(runtime_root).expanduser().resolve()
    workspace = workspace_runtime_path(runtime_root)
    work_dir = Path(work_dir).expanduser().resolve() if work_dir else workspace / "memory_attach"
    report: dict[str, Any] = {
        "runtime_root": str(runtime_root),
        "memory_root": str(resolve_memory_root(runtime_root, prefer_existing_legacy=False)),
        "parts_dir": str(Path(parts_dir).expanduser().resolve()) if parts_dir is not None else None,
        "r2_prefix": r2_prefix,
        "work_dir": str(work_dir),
        "started_at_epoch": time.time(),
    }
    try:
        preflight = runtime_preflight(runtime_root)
        report["runtime_preflight"] = preflight.to_dict()
        if not (preflight.structure_ok and preflight.manifest_ok and preflight.provenance_ok):
            return MemoryAttachResult(
                False,
                "runtime_not_verified",
                str(runtime_root),
                report,
                exit_code=13,
            )
        runtime_version = preflight.version
        if runtime_version is None:
            report["runtime_preflight_version_missing"] = True
            return MemoryAttachResult(
                False,
                "runtime_not_verified",
                str(runtime_root),
                report,
                exit_code=13,
            )

        daemon = status_daemon(JaznConfig(root=runtime_root))
        report["daemon_status_before"] = daemon
        if daemon.get("active_state") in {"active_trusted", "active_degraded"}:
            return MemoryAttachResult(
                False,
                "runtime_active_attach_blocked",
                str(runtime_root),
                report,
                exit_code=12,
            )

        resolved_parts_dir, blocked = _resolve_memory_source(
            runtime_root,
            workspace,
            parts_dir=parts_dir,
            r2_prefix=r2_prefix,
            r2_bucket=r2_bucket,
            r2_endpoint_url=r2_endpoint_url,
            r2_region_name=r2_region_name,
            r2_client=r2_client,
            report=report,
        )
        if blocked is not None:
            return blocked
        assert resolved_parts_dir is not None

        verified = _verify_and_extract_memory_package(
            runtime_root,
            resolved_parts_dir,
            base_zip_name=base_zip_name,
            work_dir=work_dir,
            time_budget_seconds=time_budget_seconds,
            run_crc=run_crc,
            force_reextract=force_reextract,
            report=report,
            package_sidecar=package_sidecar,
        )
        if isinstance(verified, MemoryAttachResult):
            return verified

        if not verified.raw_segments_materialized:
            _materialize_raw_segments(verified.staging, verified.manifest, report)
        else:
            report["raw_segment_materialization"] = {
                "ok": True,
                "mode": "streamed_direct_to_logical_source",
                "segments_materialized_as_install_files": False,
                "truth_boundary": (
                    "v3 transport segments were verified while streaming directly "
                    "into the logical source file; no segment tree was installed."
                ),
            }
        source_memory = verified.staging / "memory"
        if not source_memory.is_dir():
            return MemoryAttachResult(
                False,
                "memory_payload_missing",
                str(runtime_root),
                report,
                exit_code=15,
            )

        backup_memory, had_previous = _install_memory_tree(
            runtime_root,
            workspace,
            source_memory,
            report,
        )
        return _finalize_memory_attach(
            runtime_root,
            runtime_version=runtime_version,
            zip_name=verified.zip_name,
            manifest=verified.manifest,
            backup_memory=backup_memory,
            had_previous=had_previous,
            report=report,
        )
    except MemoryPackageSourceError as exc:
        code, etype, detail = "memory_source_materialization_failed", type(exc).__name__, str(exc)
    except MemoryStreamingTransportError as exc:
        code, etype, detail = "memory_streaming_transport_blocked", type(exc).__name__, str(exc)
    except PermissionError as exc:
        code, etype, detail = "memory_attach_path_unwritable", type(exc).__name__, str(exc)
    except FileNotFoundError as exc:
        code, etype, detail = "memory_package_source_missing", type(exc).__name__, str(exc)
    except ValueError as exc:
        code, etype, detail = "memory_package_contract_invalid", type(exc).__name__, str(exc)
    except sqlite3.Error as exc:
        code, etype, detail = "memory_package_sqlite_validation_failed", type(exc).__name__, str(exc)
    except OSError as exc:
        code, etype, detail = "memory_attach_io_error", type(exc).__name__, str(exc)
    except Exception as exc:
        code, etype, detail = "memory_attach_failed", type(exc).__name__, str(exc)
    report["error"] = {"code": code, "type": etype, "detail": detail}
    return MemoryAttachResult(
        False,
        "memory_attach_blocked",
        str(runtime_root),
        report,
        exit_code=17,
    )