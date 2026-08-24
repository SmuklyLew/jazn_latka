from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon import (
    DEFAULT_DAEMON_HOST,
    DEFAULT_DAEMON_PORT,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_START_TIMEOUT_SECONDS,
    inject_daemon_trusted_time,
    start_daemon,
    status_daemon,
)
from latka_jazn.packaging.split_zip_package import (
    extract_independent_zip_set_resumable,
    extract_joined_zip_resumable,
    infer_base_zip_name,
    join_split_package_to_zip,
    load_package_expectations,
    load_package_set_metadata,
    resolve_renamed_package_parts,
    test_joined_zip,
    verify_extracted_zip_set,
    verify_extracted_zip_tree,
)
from latka_jazn.tools.active_extraction_cache import write_active_runtime_marker
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version, version_number
from latka_jazn.core.version_source import read_runtime_version_from_version_py
from latka_jazn.core.package_integrity_manifest import (
    PACKAGE_INTEGRITY_MANIFEST_NAME,
    sha256_file,
)
from latka_jazn.core.runtime_root import active_runtime_marker_path, workspace_runtime_path
from latka_jazn.core.source_provenance import read_source_provenance
from latka_jazn.tools.package_integrity import verify_package_integrity_manifest

REQUIRED_FILES = ("latka_jazn/version.py", PACKAGE_INTEGRITY_MANIFEST_NAME)
REQUIRED_DIRECTORIES = ("latka_jazn",)
OPTIONAL_RUNTIME_DIRECTORIES = ("memory", "workspace_runtime")
START_FILES = ("run.py", "main.py")
DEFAULT_CHATGPT_ROOT = Path("/mnt/data/jazn_runtime_current_full")
DEFAULT_CHATGPT_PARTS_DIR = Path("/mnt/data")
RECOVERY_SCHEMA_VERSION = schema_version("chatgpt_runtime_recovery", version=PACKAGE_VERSION_FULL)
MEMORY_PACKAGE_MANIFEST_PATH = "memory/MEMORY_PACKAGE_MANIFEST.json"


@dataclass(slots=True)
class RuntimePreflightReport:
    ok: bool
    active_root: str
    structure_ok: bool
    manifest_ok: bool
    provenance_ok: bool
    marker_ok: bool
    start_file: str | None
    version: str | None
    manifest_version: str | None
    marker_path: str | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest_verification: dict[str, Any] | None = None
    source_provenance: dict[str, Any] | None = None
    schema_version: str = RECOVERY_SCHEMA_VERSION
    truth_boundary: str = (
        "Preflight potwierdza folder, start file, manifest i marker. Żywy daemon, "
        "timestamp i SQLite są osobnymi etapami aktywacji."
    )

    @property
    def needs_recovery(self) -> bool:
        return not (self.structure_ok and self.manifest_ok and self.provenance_ok)

    @property
    def needs_marker_refresh(self) -> bool:
        return bool(self.structure_ok and self.manifest_ok and self.provenance_ok and not self.marker_ok)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["needs_recovery"] = self.needs_recovery
        payload["needs_marker_refresh"] = self.needs_marker_refresh
        return payload


@dataclass(slots=True)
class RecoveryResult:
    ok: bool
    state: str
    active_root: str
    report: dict[str, Any]
    pending: bool = False
    exit_code: int = 0
    schema_version: str = RECOVERY_SCHEMA_VERSION
    truth_boundary: str = (
        "Folder zostaje zainstalowany dopiero po pełnym SHA256/CRC, rozpakowaniu bez uciętych "
        "plików, porównaniu ZIP–filesystem, atomowym przeniesieniu i zapisaniu markera. Stan "
        "active wymaga dodatkowo rzeczywiście osiągalnego Daemona oraz sprawnej pamięci; tryb "
        "bez startu procesu pozostaje installed_inactive."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _part_resolution_cache_valid(cache: dict[str, Any] | None, expected: list[Any], canonical_dir: Path) -> bool:
    if not isinstance(cache, dict) or cache.get("ok") is not True:
        return False
    rows = cache.get("resolved_parts")
    if not isinstance(rows, list) or len(rows) != len(expected):
        return False
    by_no = {int(row.get("part_no", -1)): row for row in rows if isinstance(row, dict)}
    for part in expected:
        row = by_no.get(int(part.part_no))
        if not row or row.get("expected_name") != part.filename:
            return False
        source = Path(str(row.get("source_path") or ""))
        target = canonical_dir / part.filename
        if not source.is_file() or not target.is_file():
            return False
        stat = source.stat()
        if int(row.get("size_bytes", -1)) != stat.st_size or int(row.get("source_mtime_ns", -1)) != stat.st_mtime_ns:
            return False
        if part.size_bytes is not None and target.stat().st_size != part.size_bytes:
            return False
        if part.sha256:
            expected_sha = part.sha256.lower()
            if str(row.get("sha256") or "").lower() != expected_sha:
                return False
            if sha256_file(source).lower() != expected_sha or sha256_file(target).lower() != expected_sha:
                return False
    return True


def _zip_verification_cache_valid(cache: dict[str, Any] | None, zip_path: Path, expected_sha: str | None, run_crc: bool) -> bool:
    if not isinstance(cache, dict) or cache.get("ok") is not True or not zip_path.is_file():
        return False
    stat = zip_path.stat()
    if int(cache.get("size_bytes", -1)) != stat.st_size or int(cache.get("mtime_ns", -1)) != stat.st_mtime_ns:
        return False
    if not expected_sha:
        return False
    normalized_expected = expected_sha.lower()
    if str(cache.get("sha256") or "").lower() != normalized_expected:
        return False
    if sha256_file(zip_path).lower() != normalized_expected:
        return False
    if run_crc and cache.get("crc_tested") is not True:
        return False
    return True


def _runtime_version(root: Path) -> str | None:
    return read_runtime_version_from_version_py(root)


def _find_start_file(root: Path) -> str | None:
    for name in START_FILES:
        if (root / name).is_file():
            return name
    return None


def _candidate_marker_paths(root: Path, explicit: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    if explicit is not None:
        paths.append(Path(explicit).expanduser().resolve())
    paths.extend((root / "JAZN_ACTIVE_RUNTIME.json", active_runtime_marker_path(root)))
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def runtime_preflight(root: Path, *, marker_path: Path | None = None) -> RuntimePreflightReport:
    root = Path(root).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            errors.append(f"missing_file:{name}")
    for name in REQUIRED_DIRECTORIES:
        if not (root / name).is_dir():
            errors.append(f"missing_directory:{name}")
    for name in OPTIONAL_RUNTIME_DIRECTORIES:
        candidate = workspace_runtime_path(root) if name == "workspace_runtime" else root / name
        if not candidate.is_dir():
            warnings.append(f"runtime_directory_missing_will_be_initialized:{name}")
    start_file = _find_start_file(root)
    if not start_file:
        errors.append("missing_start_file:run.py_or_main.py")
    structure_ok = not errors

    version = _runtime_version(root)
    manifest_path = root / PACKAGE_INTEGRITY_MANIFEST_NAME
    manifest = _read_json(manifest_path)
    manifest_version = None
    manifest_ok = False
    manifest_verification: dict[str, Any] | None = None
    manifest_sha256 = sha256_file(manifest_path) if manifest_path.is_file() else None
    if manifest is None:
        if manifest_path.exists():
            errors.append("package_integrity_manifest_invalid_json")
    else:
        manifest_version = str(manifest.get("version") or manifest.get("runtime_version") or "").strip() or None
        manifest_start = str(manifest.get("start_file") or "").strip() or None
        versions_match = bool(
            version and manifest_version and version_number(version) == version_number(manifest_version)
        )
        start_matches = bool(start_file and (not manifest_start or manifest_start == start_file or (root / manifest_start).is_file()))
        manifest_verification = verify_package_integrity_manifest(root)
        manifest_ok = bool(versions_match and start_matches and manifest_verification.get("ok") is True)
        if not versions_match:
            errors.append(f"manifest_version_mismatch:{version!r}!={manifest_version!r}")
        if not start_matches:
            errors.append(f"manifest_start_file_invalid:{manifest_start!r}")
        if manifest_verification.get("ok") is not True:
            error_codes = sorted({
                str(item.get("code") or "unknown")
                for item in manifest_verification.get("errors", [])
                if isinstance(item, dict)
            })
            errors.append(
                "package_integrity_verification_failed:"
                + (",".join(error_codes) if error_codes else "unknown")
            )

    selected_marker: Path | None = None
    marker_ok = False
    for candidate in _candidate_marker_paths(root, marker_path):
        marker = _read_json(candidate)
        if marker is None:
            continue
        if selected_marker is None:
            selected_marker = candidate
        active = str(marker.get("active_root") or marker.get("active_folder") or "").strip()
        candidate_ok = bool(active and Path(active).expanduser().resolve() == root)
        marker_version = str(marker.get("version") or "").strip()
        if candidate_ok and marker_version and version:
            candidate_ok = version_number(marker_version) == version_number(version)
            if not candidate_ok:
                warnings.append(f"marker_version_mismatch:{marker_version!r}!={version!r}")
        marker_manifest_sha = str(marker.get("package_integrity_manifest_sha256") or "").strip()
        legacy_marker_sha = str(marker.get("manifest_current_sha256") or "").strip()
        if candidate_ok and manifest_sha256:
            if marker_manifest_sha != manifest_sha256:
                candidate_ok = False
                if not marker_manifest_sha and legacy_marker_sha == manifest_sha256:
                    warnings.append("marker_legacy_manifest_sha256_requires_refresh")
                else:
                    warnings.append("marker_package_integrity_manifest_sha256_mismatch")
        if candidate_ok:
            selected_marker = candidate
            marker_ok = True
            break
    if not marker_ok:
        warnings.append("active_marker_missing_or_not_trusted")

    source_provenance = read_source_provenance(root, profile="system_smoke").to_dict()
    provenance_ok = source_provenance.get("status") in {
        "clean_checkout_verified",
        "development_dirty_verified",
        "verified_export_without_git_history",
    }
    if not provenance_ok:
        errors.append(
            "source_provenance_not_verified:"
            + str(source_provenance.get("status") or "unknown")
        )

    return RuntimePreflightReport(
        ok=bool(structure_ok and manifest_ok and provenance_ok and marker_ok),
        active_root=str(root),
        structure_ok=structure_ok,
        manifest_ok=manifest_ok,
        provenance_ok=provenance_ok,
        marker_ok=marker_ok,
        start_file=start_file,
        version=version,
        manifest_version=manifest_version,
        marker_path=str(selected_marker) if selected_marker else None,
        errors=errors,
        warnings=warnings,
        manifest_verification=manifest_verification,
        source_provenance=source_provenance,
    )


def _safe_remove_tree(path: Path) -> None:
    path = Path(path)
    if path.exists():
        shutil.rmtree(path)


def _atomic_activate(staging: Path, destination: Path, *, work_dir: Path) -> dict[str, Any]:
    staging = Path(staging).resolve()
    destination = Path(destination).resolve()
    work_dir = Path(work_dir).resolve()
    if staging.parent != destination.parent:
        raise ValueError("Staging i destination muszą być na tym samym filesystemie i w tym samym katalogu nadrzędnym.")
    backup = destination.parent / f".{destination.name}.previous-{int(time.time())}"
    moved_old = False
    try:
        if destination.exists():
            os.replace(destination, backup)
            moved_old = True
        os.replace(staging, destination)
    except Exception:
        if moved_old and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup.exists():
        _safe_remove_tree(backup)
    return {
        "ok": True,
        "destination": str(destination),
        "staging": str(staging),
        "backup_removed": not backup.exists(),
        "work_dir": str(work_dir),
    }


def _sqlite_health(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    bootstrap = _read_json(root / "BOOTSTRAP_JAZN_CURRENT.json") or {}
    rel = str(bootstrap.get("active_database") or "").strip()
    candidates: list[tuple[str, Path]] = []
    if rel:
        declared = (root / rel).resolve()
        try:
            declared.relative_to(root)
        except ValueError:
            return {
                "ok": False,
                "reason": "active_database_escapes_runtime_root",
                "declared_active_database": rel,
            }
        candidates.append(("bootstrap_active_database", declared))
    try:
        config = JaznConfig(root=root)
        candidates.extend(
            (
                ("recovered_memory_database", config.recovered_memory_db_path),
                ("runtime_memory_database", config.memory_db_path_readonly),
                ("conversation_archive_manifest", config.conversation_archive_manifest_path),
            )
        )
    except Exception as exc:
        return {
            "ok": False,
            "reason": "memory_database_resolution_failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    unique: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for source, candidate in candidates:
        resolved = Path(candidate).resolve()
        if resolved not in seen:
            unique.append((source, resolved))
            seen.add(resolved)
    selected = next(((source, path) for source, path in unique if path.is_file()), None)
    if selected is None:
        return {
            "ok": False,
            "reason": "active_database_missing",
            "candidates": [
                {"source": source, "database": str(path), "exists": path.is_file()}
                for source, path in unique
            ],
        }
    source, db_path = selected
    if not db_path.is_file():
        return {"ok": False, "reason": "active_database_missing", "database": str(db_path)}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10.0) as con:
            integrity_rows = con.execute("PRAGMA integrity_check").fetchall()
            foreign_rows = con.execute("PRAGMA foreign_key_check").fetchall()
            tables = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()
        integrity = [str(row[0]) for row in integrity_rows]
        return {
            "ok": integrity == ["ok"] and not foreign_rows,
            "database": str(db_path),
            "database_source": source,
            "integrity_check": integrity,
            "foreign_key_check_count": len(foreign_rows),
            "table_count": int(tables[0]) if tables else 0,
        }
    except Exception as exc:
        return {"ok": False, "database": str(db_path), "reason": f"{type(exc).__name__}: {exc}"}



def _discover_memory_package(parts_dir: Path, explicit_zip_name: str | None = None) -> dict[str, Any]:
    """Discover exactly one sidecar-declared memory package beside the system package."""

    directory = Path(parts_dir).expanduser().resolve()
    candidates: list[dict[str, Any]] = []
    for sidecar_path in sorted(directory.glob("*.package.json")):
        payload = _read_json(sidecar_path)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("profile") or "").strip().lower() != "memory":
            continue
        package_name = str(payload.get("package_name") or "").strip()
        if package_name:
            candidates.append(
                {
                    "package_name": package_name,
                    "sidecar_path": str(sidecar_path),
                    "sidecar": payload,
                }
            )
    if explicit_zip_name:
        wanted = str(explicit_zip_name).strip()
        matches = [item for item in candidates if item["package_name"] == wanted]
        if len(matches) != 1:
            return {
                "ok": False,
                "state": "explicit_memory_package_not_found",
                "requested": wanted,
                "candidate_names": [item["package_name"] for item in candidates],
            }
        return {"ok": True, "state": "memory_package_discovered", **matches[0]}
    if not candidates:
        return {"ok": True, "state": "memory_package_not_present", "package_name": None}
    if len(candidates) > 1:
        return {
            "ok": False,
            "state": "memory_package_ambiguous",
            "candidate_names": [item["package_name"] for item in candidates],
        }
    return {"ok": True, "state": "memory_package_discovered", **candidates[0]}


def _memory_package_requires_v3_repack(sidecar: dict[str, Any]) -> dict[str, Any]:
    """Decide whether legacy transport must be segmented before safe extraction."""

    from latka_jazn.packaging.zip_resource_limits import ZipResourceLimits

    if str(sidecar.get("memory_manifest_schema") or "").strip() == "jazn_memory_package_manifest/v3":
        return {"required": False, "reason": "memory_transport_v3"}
    limits = ZipResourceLimits.from_env()
    entries = [item for item in sidecar.get("entries") or [] if isinstance(item, dict)]
    total = sum(max(0, int(item.get("size_bytes") or 0)) for item in entries)
    oversized = [
        str(item.get("path") or "")
        for item in entries
        if int(item.get("size_bytes") or 0) > limits.max_member_uncompressed_bytes
    ]
    archive_format = str(sidecar.get("archive_format") or "").strip().lower()
    required = bool(
        oversized
        or (archive_format == "binary" and total > limits.max_total_uncompressed_bytes)
    )
    return {
        "required": required,
        "reason": "legacy_transport_exceeds_safe_zip_limits" if required else "legacy_transport_within_safe_zip_limits",
        "archive_format": archive_format,
        "declared_total_uncompressed_bytes": total,
        "oversized_members": oversized[:16],
        "limits": limits.to_dict(),
    }


def _auto_attach_memory_before_daemon(
    *,
    destination: Path,
    parts_dir: Path,
    work_dir: Path,
    memory_zip_name: str | None,
    time_budget_seconds: float | None,
    run_crc: bool,
    force_reextract: bool,
) -> dict[str, Any]:
    """Attach and make memory wake-ready while the runtime daemon is stopped."""

    existing_health = _sqlite_health(destination)
    discovery = _discover_memory_package(parts_dir, memory_zip_name)
    report: dict[str, Any] = {
        "enabled": True,
        "sqlite_before": existing_health,
        "discovery": {key: value for key, value in discovery.items() if key != "sidecar"},
    }
    if discovery.get("ok") is not True:
        report.update({"ok": False, "state": str(discovery.get("state") or "memory_discovery_failed")})
        return report
    if discovery.get("state") == "memory_package_not_present":
        report.update({
            "ok": existing_health.get("ok") is True,
            "state": "existing_memory_kept" if existing_health.get("ok") is True else "memory_package_not_present",
        })
        return report
    from latka_jazn.packaging.memory_package_contract import (
        LegacyMemoryRepackError,
        attach_memory_package,
        repack_legacy_memory_package,
    )
    from latka_jazn.tools.memory_validation import validate_large_memory
    from latka_jazn.memory.memory_recovery_pipeline import MemoryRecoveryPipeline

    if existing_health.get("ok") is True and memory_zip_name is None:
        existing_validation = validate_large_memory(destination, full=False)
        report["existing_memory_validation"] = existing_validation
        if existing_validation.get("ok") is True:
            report.update({"ok": True, "state": "existing_memory_kept", "package_attach_skipped": True})
            return report

    source_dir = Path(parts_dir).expanduser().resolve()
    source_name = str(discovery.get("package_name") or "")
    raw_sidecar = discovery.get("sidecar")
    sidecar = cast(dict[str, Any], raw_sidecar) if isinstance(raw_sidecar, dict) else {}
    repack_decision = _memory_package_requires_v3_repack(sidecar)
    report["repack_decision"] = repack_decision
    if repack_decision.get("required") is True:
        repack_dir = work_dir / "auto_memory_v3"
        repack_work = work_dir / "auto_memory_v3_work"
        existing_repack = _discover_memory_package(repack_dir) if repack_dir.is_dir() else {"ok": True, "state": "memory_package_not_present"}
        raw_existing_sidecar = existing_repack.get("sidecar")
        existing_sidecar = (
            cast(dict[str, Any], raw_existing_sidecar)
            if isinstance(raw_existing_sidecar, dict)
            else {}
        )
        if (
            existing_repack.get("ok") is True
            and existing_repack.get("state") == "memory_package_discovered"
            and str(existing_sidecar.get("memory_manifest_schema") or "").strip()
            == "jazn_memory_package_manifest/v3"
        ):
            report["repack"] = {
                "ok": True,
                "state": "legacy_memory_repack_reused",
                "output_package_name": existing_repack.get("package_name"),
                "output_dir": str(repack_dir),
            }
            source_dir = repack_dir
            source_name = str(existing_repack.get("package_name") or "")
        else:
            try:
                repack = repack_legacy_memory_package(
                    source_dir,
                    output_dir=repack_dir,
                    base_zip_name=source_name,
                    work_dir=repack_work,
                    force=force_reextract,
                )
            except (LegacyMemoryRepackError, FileExistsError) as exc:
                report.update({"ok": False, "state": "memory_legacy_repack_failed", "error": str(exc)})
                return report
            report["repack"] = repack
            if repack.get("ok") is not True:
                report.update({"ok": False, "state": "memory_legacy_repack_failed"})
                return report
            source_dir = repack_dir
            source_name = str(repack.get("output_package_name") or "")

    attach = attach_memory_package(
        destination,
        parts_dir=source_dir,
        base_zip_name=source_name or None,
        work_dir=work_dir / "auto_memory_attach",
        time_budget_seconds=time_budget_seconds,
        run_crc=run_crc,
        force_reextract=force_reextract,
    )
    report["attach"] = attach.to_dict()
    if attach.pending:
        report.update({"ok": False, "pending": True, "state": attach.state})
        return report
    if not attach.ok:
        report.update({"ok": False, "state": attach.state})
        return report

    validation = validate_large_memory(destination, full=False)
    report["validation_before_recovery"] = validation
    if validation.get("ok") is not True:
        recovery = MemoryRecoveryPipeline(destination).run(
            force_recovery=False,
            prepare_l2=False,
            build_l3_manifest=False,
        )
        report["recovery"] = recovery.to_dict()
        if recovery.status not in {"ready", "ready_with_l2", "ready_with_l3", "completed_with_warnings"}:
            report.update({"ok": False, "state": "memory_recovery_not_ready"})
            return report
        validation = validate_large_memory(destination, full=False)
    report["validation_after_recovery"] = validation
    report["sqlite_after"] = _sqlite_health(destination)
    report["ok"] = bool(validation.get("ok") is True and report["sqlite_after"].get("ok") is True)
    report["state"] = "memory_attached_ready" if report["ok"] else "memory_attached_not_ready"
    return report

def _verify_memory_package_manifest(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest_path = root / MEMORY_PACKAGE_MANIFEST_PATH
    if not manifest_path.is_file():
        return {
            "ok": False,
            "status": "not_present",
            "manifest_path": str(manifest_path),
            "errors": [{"code": "memory_package_manifest_missing"}],
        }
    payload = _read_json(manifest_path)
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": "invalid",
            "manifest_path": str(manifest_path),
            "errors": [{"code": "memory_package_manifest_invalid_json"}],
        }
    errors: list[dict[str, Any]] = []
    if payload.get("schema_version") != "jazn_memory_package_manifest/v1":
        errors.append(
            {
                "code": "memory_package_manifest_schema_unsupported",
                "actual": payload.get("schema_version"),
            }
        )
    declared_version = str(payload.get("runtime_version") or "").strip()
    actual_version = _runtime_version(root)
    if not declared_version or not actual_version or version_number(declared_version) != version_number(actual_version):
        errors.append(
            {
                "code": "memory_package_runtime_version_mismatch",
                "declared": declared_version or None,
                "actual": actual_version,
            }
        )
    expected_paths: set[str] = set()
    verified_count = 0
    for item in payload.get("files") or []:
        if not isinstance(item, dict):
            errors.append({"code": "memory_package_file_entry_invalid"})
            continue
        relative = str(item.get("path") or "").replace("\\", "/").strip()
        parts = Path(relative).parts
        if not relative or Path(relative).is_absolute() or ".." in parts or not relative.startswith("memory/"):
            errors.append({"code": "memory_package_path_unsafe", "path": relative})
            continue
        if relative == MEMORY_PACKAGE_MANIFEST_PATH or relative in expected_paths:
            errors.append({"code": "memory_package_path_duplicate_or_self", "path": relative})
            continue
        expected_paths.add(relative)
        target = (root / Path(*relative.split("/"))).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            errors.append({"code": "memory_package_path_escapes_root", "path": relative})
            continue
        if not target.is_file():
            errors.append({"code": "memory_package_file_missing", "path": relative})
            continue
        expected_size = int(item.get("size_bytes", -1))
        expected_sha = str(item.get("sha256") or "").strip().lower()
        actual_size = target.stat().st_size
        actual_sha = sha256_file(target)
        if actual_size != expected_size:
            errors.append(
                {
                    "code": "memory_package_file_size_mismatch",
                    "path": relative,
                    "expected": expected_size,
                    "actual": actual_size,
                }
            )
        if actual_sha != expected_sha:
            errors.append(
                {
                    "code": "memory_package_file_sha256_mismatch",
                    "path": relative,
                    "expected": expected_sha,
                    "actual": actual_sha,
                }
            )
        if actual_size == expected_size and actual_sha == expected_sha:
            verified_count += 1
    memory_root = root / "memory"
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in memory_root.rglob("*")
        if path.is_file() and path.resolve() != manifest_path.resolve()
    } if memory_root.is_dir() else set()
    for extra in sorted(actual_paths - expected_paths):
        errors.append({"code": "memory_package_unlisted_file", "path": extra})
    declared_count = int(payload.get("file_count", -1))
    if declared_count != len(expected_paths):
        errors.append(
            {
                "code": "memory_package_file_count_mismatch",
                "declared": declared_count,
                "actual": len(expected_paths),
            }
        )
    return {
        "ok": not errors,
        "status": "verified" if not errors else "invalid",
        "manifest_path": str(manifest_path),
        "declared_file_count": declared_count,
        "verified_file_count": verified_count,
        "errors": errors,
        "truth_boundary": (
            "Weryfikacja pamięci potwierdza rozmiar i SHA-256 każdego pliku z paczki; "
            "nie zatwierdza treści wspomnień ani promocji L2/L3."
        ),
    }


def _recover_chatgpt_runtime_impl(
    *,
    parts_dir: Path = DEFAULT_CHATGPT_PARTS_DIR,
    destination: Path = DEFAULT_CHATGPT_ROOT,
    base_zip_name: str | None = None,
    work_dir: Path | None = None,
    time_budget_seconds: float | None = 25.0,
    run_crc: bool = True,
    force_reextract: bool = False,
    start_runtime_daemon: bool = True,
    auto_attach_memory: bool = True,
    memory_zip_name: str | None = None,
    daemon_host: str = DEFAULT_DAEMON_HOST,
    daemon_port: int = DEFAULT_DAEMON_PORT,
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    startup_timeout: float = DEFAULT_START_TIMEOUT_SECONDS,
    trusted_time_iso: str | None = None,
    trusted_time_source: str | None = None,
    trusted_time_max_age_seconds: int | None = None,
) -> RecoveryResult:
    parts_dir = Path(parts_dir).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    work_dir = Path(work_dir).expanduser().resolve() if work_dir else destination.parent / f".{destination.name}.recovery"
    work_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "parts_dir": str(parts_dir),
        "destination": str(destination),
        "work_dir": str(work_dir),
        "started_at_epoch": time.time(),
        "auto_attach_memory": bool(auto_attach_memory),
        "memory_zip_name": memory_zip_name,
    }

    preflight = runtime_preflight(destination)
    report["preflight_before"] = preflight.to_dict()
    if preflight.structure_ok and preflight.manifest_ok and preflight.provenance_ok and not force_reextract:
        if auto_attach_memory:
            report["auto_memory"] = _auto_attach_memory_before_daemon(
                destination=destination,
                parts_dir=parts_dir,
                work_dir=work_dir,
                memory_zip_name=memory_zip_name,
                time_budget_seconds=time_budget_seconds,
                run_crc=run_crc,
                force_reextract=force_reextract,
            )
            if report["auto_memory"].get("pending") is True:
                return RecoveryResult(
                    ok=False, pending=True, state="auto_memory_pending",
                    active_root=str(destination), report=report, exit_code=75,
                )
            if report["auto_memory"].get("state") not in {"memory_package_not_present", "existing_memory_kept"} and report["auto_memory"].get("ok") is not True:
                return RecoveryResult(
                    ok=False, state="auto_memory_failed", active_root=str(destination), report=report, exit_code=11
                )
        marker = write_active_runtime_marker(destination, action="chatgpt_recovery_reuse_verified_folder")
        report["marker"] = marker
        config = JaznConfig(root=destination)
        if start_runtime_daemon:
            report["daemon_start"] = start_daemon(
                config,
                host=daemon_host,
                port=daemon_port,
                heartbeat_interval=heartbeat_interval,
                startup_timeout=startup_timeout,
            )
        if trusted_time_iso:
            report["trusted_time_injection"] = inject_daemon_trusted_time(
                config,
                trusted_time_iso=trusted_time_iso,
                source=trusted_time_source or "chatgpt_loader_time",
                max_age_seconds=trusted_time_max_age_seconds,
                host=daemon_host,
                port=daemon_port,
                timeout=min(max(startup_timeout, 1.0), 10.0),
            )
        report["daemon_status"] = status_daemon(config, host=daemon_host, port=daemon_port)
        report["sqlite"] = _sqlite_health(destination)
        report["preflight_after"] = runtime_preflight(destination).to_dict()
        installation_ok = bool(report["preflight_after"]["ok"])
        daemon_gate_ok = bool(
            not start_runtime_daemon
            or report["daemon_status"].get("active_state") in {"active_trusted", "active_degraded"}
        )
        daemon_active = report["daemon_status"].get("active_state") in {"active_trusted", "active_degraded"}
        memory_ok = report["sqlite"].get("ok") is True
        memory_absent = report["sqlite"].get("reason") == "active_database_missing"
        memory_gate_ok = bool(memory_ok or (not start_runtime_daemon and memory_absent))
        ok = bool(installation_ok and daemon_gate_ok and memory_gate_ok)
        report["installation_ok"] = installation_ok
        report["activation_ok"] = bool(installation_ok and daemon_active and memory_ok)
        state = "reused" if report["activation_ok"] else "reused_installed_inactive" if ok else "reused_degraded"
        return RecoveryResult(ok=ok, state=state, active_root=str(destination), report=report, exit_code=0 if ok else 4)

    destination_occupied = bool(
        destination.exists()
        and (not destination.is_dir() or any(destination.iterdir()))
    )
    if destination_occupied:
        report["replacement_blocked"] = {
            "ok": False,
            "reason": "destination_not_empty_and_not_verified",
            "destination": str(destination),
            "recovery_hint": (
                "Wskaż nowy, wersjonowany katalog destination. Loader nie zastępuje automatycznie "
                "istniejącego, niezweryfikowanego runtime."
            ),
        }
        return RecoveryResult(
            ok=False,
            state="destination_replacement_blocked",
            active_root=str(destination),
            report=report,
            exit_code=9,
        )

    zip_name = infer_base_zip_name(parts_dir, base_zip_name)
    report["base_zip_name"] = zip_name
    package_set = load_package_set_metadata(parts_dir, zip_name)
    report["package_set"] = package_set
    declared_profile = str(package_set.get("profile") or "unknown").strip().lower()
    package_contract_source = str(package_set.get("source") or "")
    if package_contract_source == "package.json" and declared_profile not in {"system", "memory", "combined"}:
        report["profile_gate"] = {
            "ok": False,
            "reason": "current_package_profile_missing_or_unsupported",
            "declared_profile": declared_profile,
        }
        return RecoveryResult(
            ok=False,
            state="package_profile_rejected",
            active_root=str(destination),
            report=report,
            exit_code=8,
        )
    if declared_profile == "memory":
        report["profile_gate"] = {
            "ok": False,
            "reason": "memory_profile_is_not_a_runtime_root",
            "truth_boundary": (
                "Paczka memory może zostać dołączona wyłącznie do osobno zweryfikowanego systemu; "
                "sama nie zawiera startowego active_root."
            ),
        }
        return RecoveryResult(
            ok=False,
            state="memory_profile_rejected",
            active_root=str(destination),
            report=report,
            exit_code=8,
        )
    expected, expected_full_sha, source = load_package_expectations(parts_dir, zip_name)
    report["expectations_source"] = source
    report["expected_parts_count"] = len(expected)
    report["expected_full_sha256"] = expected_full_sha

    canonical_dir = work_dir / "canonical_parts"
    resolution_cache_path = work_dir / "part-resolution.json"
    cached_aliases = _read_json(resolution_cache_path)
    if _part_resolution_cache_valid(cached_aliases, expected, canonical_dir):
        aliases = dict(cached_aliases or {})
        aliases["cache_reused"] = True
    else:
        aliases = resolve_renamed_package_parts(
            parts_dir,
            expected,
            canonical_dir=canonical_dir,
            skip_part_hash=False,
        )
        aliases["cache_reused"] = False
        _write_json_atomic(resolution_cache_path, aliases)
    report["part_resolution"] = aliases
    for suffix in (".package.json", ".manifest.json", ".parts.sha256", ".sha256"):
        source_sidecar = parts_dir / f"{zip_name}{suffix}"
        if source_sidecar.is_file():
            shutil.copy2(source_sidecar, canonical_dir / source_sidecar.name)
    archive_format = str(package_set.get("archive_format") or "binary")
    zip_out: Path | None = None
    independent_paths: list[Path] = []
    if archive_format == "independent":
        independent_paths = [canonical_dir / part.filename for part in expected]
        zip_report = {
            "ok": True,
            "archive_format": "independent",
            "volumes": [test_joined_zip(path, run_crc=run_crc) for path in independent_paths],
            "cache_reused": False,
        }
    else:
        zip_out = work_dir / zip_name
        zip_cache_path = work_dir / "zip-verification.json"
        zip_cache = _read_json(zip_cache_path)
        if _zip_verification_cache_valid(zip_cache, zip_out, expected_full_sha, run_crc):
            zip_report = dict(zip_cache or {})
            zip_report["cache_reused"] = True
        else:
            zip_out = join_split_package_to_zip(
                canonical_dir,
                zip_name,
                zip_out=zip_out,
                force=True,
                keep_existing=False,
            )
            zip_report = test_joined_zip(zip_out, run_crc=run_crc)
            zip_report.update({
                "sha256": expected_full_sha,
                "mtime_ns": zip_out.stat().st_mtime_ns,
                "cache_reused": False,
            })
            _write_json_atomic(zip_cache_path, zip_report)
    report["zip_test"] = zip_report

    staging = destination.parent / f".{destination.name}.staging"
    if force_reextract and staging.exists():
        _safe_remove_tree(staging)
    if archive_format == "independent":
        extraction = extract_independent_zip_set_resumable(
            independent_paths,
            staging,
            progress_path=work_dir / "extract-progress.json",
            time_budget_seconds=time_budget_seconds,
        )
    else:
        assert zip_out is not None
        extraction = extract_joined_zip_resumable(
            zip_out,
            staging,
            progress_path=work_dir / "extract-progress.json",
            time_budget_seconds=time_budget_seconds,
        )
    report["extraction"] = extraction
    if extraction.get("pending"):
        report["resume_command"] = (
            f"python -X utf8 main.py --recover-chatgpt-runtime --recovery-parts-dir {parts_dir} "
            f"--recovery-destination {destination} --recovery-work-dir {work_dir}"
        )
        return RecoveryResult(
            ok=False,
            pending=True,
            state="extracting_pending",
            active_root=str(destination),
            report=report,
            exit_code=75,
        )

    if archive_format == "independent":
        verification = verify_extracted_zip_set(
            independent_paths,
            staging,
            reject_extra_files=True,
        )
    else:
        if zip_out is None:
            raise ValueError("joined ZIP path missing for non-independent package")
        verification = verify_extracted_zip_tree(
            zip_out,
            staging,
            reject_extra_files=True,
        )
    report["filesystem_verification"] = verification
    if not verification["ok"]:
        return RecoveryResult(ok=False, state="verification_failed", active_root=str(destination), report=report, exit_code=5)

    staging_preflight = runtime_preflight(staging)
    report["staging_preflight"] = staging_preflight.to_dict()
    if not (
        staging_preflight.structure_ok
        and staging_preflight.manifest_ok
        and staging_preflight.provenance_ok
    ):
        return RecoveryResult(ok=False, state="staging_runtime_invalid", active_root=str(destination), report=report, exit_code=6)

    memory_manifest = _verify_memory_package_manifest(staging)
    report["memory_manifest_verification"] = memory_manifest
    memory_files_present = bool(
        (staging / "memory").is_dir()
        and any(path.is_file() for path in (staging / "memory").rglob("*"))
    )
    profile = (
        "combined" if declared_profile == "unknown" and memory_files_present
        else "system" if declared_profile == "unknown"
        else declared_profile
    )
    report["effective_profile"] = profile
    declared_package_version = str(package_set.get("package_version") or "").strip()
    if (
        declared_package_version
        and staging_preflight.version
        and version_number(declared_package_version) != version_number(staging_preflight.version)
    ):
        report["profile_gate"] = {
            "ok": False,
            "reason": "package_sidecar_runtime_version_mismatch",
            "declared": declared_package_version,
            "actual": staging_preflight.version,
        }
        return RecoveryResult(
            ok=False,
            state="package_profile_tree_mismatch",
            active_root=str(destination),
            report=report,
            exit_code=10,
        )
    runtime_state_files = []
    packaged_workspace = staging / "workspace_runtime"
    if packaged_workspace.is_dir():
        runtime_state_files.extend(
            path.relative_to(staging).as_posix()
            for path in packaged_workspace.rglob("*")
            if path.is_file()
        )
    for relative in (
        "RUNTIME_STATE.json",
        "JAZN_ACTIVE_RUNTIME.json",
        "BOOTSTRAP_JAZN_CURRENT.json",
        "ACTIVE_RUNTIME_CACHE_CONTRACT.json",
    ):
        if (staging / relative).is_file():
            runtime_state_files.append(relative)
    if runtime_state_files:
        report["profile_gate"] = {
            "ok": False,
            "reason": "package_contains_mutable_runtime_state",
            "paths": sorted(set(runtime_state_files)),
        }
        return RecoveryResult(
            ok=False,
            state="package_profile_tree_mismatch",
            active_root=str(destination),
            report=report,
            exit_code=10,
        )
    if profile == "system" and memory_files_present:
        report["profile_gate"] = {
            "ok": False,
            "reason": "system_profile_contains_memory",
        }
        return RecoveryResult(
            ok=False,
            state="package_profile_tree_mismatch",
            active_root=str(destination),
            report=report,
            exit_code=10,
        )
    if profile == "combined" and memory_manifest.get("ok") is not True:
        report["profile_gate"] = {
            "ok": False,
            "reason": "combined_profile_memory_verification_failed",
        }
        return RecoveryResult(
            ok=False,
            state="memory_verification_failed",
            active_root=str(destination),
            report=report,
            exit_code=10,
        )

    report["activation"] = _atomic_activate(staging, destination, work_dir=work_dir)
    if auto_attach_memory and profile == "system":
        report["auto_memory"] = _auto_attach_memory_before_daemon(
            destination=destination,
            parts_dir=parts_dir,
            work_dir=work_dir,
            memory_zip_name=memory_zip_name,
            time_budget_seconds=time_budget_seconds,
            run_crc=run_crc,
            force_reextract=force_reextract,
        )
        if report["auto_memory"].get("pending") is True:
            return RecoveryResult(
                ok=False, pending=True, state="auto_memory_pending",
                active_root=str(destination), report=report, exit_code=75,
            )
        if report["auto_memory"].get("state") not in {"memory_package_not_present", "existing_memory_kept"} and report["auto_memory"].get("ok") is not True:
            return RecoveryResult(
                ok=False, state="auto_memory_failed", active_root=str(destination), report=report, exit_code=11
            )
    marker = write_active_runtime_marker(
        destination,
        source_zip=zip_out,
        action="chatgpt_recovery_atomic_activation",
    )
    report["marker"] = marker
    config = JaznConfig(root=destination)
    if start_runtime_daemon:
        report["daemon_start"] = start_daemon(
            config,
            host=daemon_host,
            port=daemon_port,
            heartbeat_interval=heartbeat_interval,
            startup_timeout=startup_timeout,
        )
    if trusted_time_iso:
        report["trusted_time_injection"] = inject_daemon_trusted_time(
            config,
            trusted_time_iso=trusted_time_iso,
            source=trusted_time_source or "chatgpt_loader_time",
            max_age_seconds=trusted_time_max_age_seconds,
            host=daemon_host,
            port=daemon_port,
            timeout=min(max(startup_timeout, 1.0), 10.0),
        )
    report["daemon_status"] = status_daemon(config, host=daemon_host, port=daemon_port)
    report["sqlite"] = _sqlite_health(destination)
    after = runtime_preflight(destination)
    report["preflight_after"] = after.to_dict()
    daemon_ok = not start_runtime_daemon or report["daemon_status"].get("active_state") in {"active_trusted", "active_degraded"}
    memory_ok = report["sqlite"].get("ok") is True
    memory_absent = report["sqlite"].get("reason") == "active_database_missing"
    memory_required = bool(profile == "combined" or memory_files_present)
    memory_gate_ok = bool(
        memory_ok
        or (not start_runtime_daemon and not memory_required and memory_absent)
    )
    installation_ok = bool(after.ok)
    daemon_active = report["daemon_status"].get("active_state") in {"active_trusted", "active_degraded"}
    activation_ok = bool(installation_ok and daemon_active and memory_ok)
    ok = bool(installation_ok and daemon_ok and memory_gate_ok)
    report["installation_ok"] = installation_ok
    report["activation_ok"] = activation_ok
    state = "active" if activation_ok else "installed_inactive" if ok else "activated_degraded"
    return RecoveryResult(ok=ok, state=state, active_root=str(destination), report=report, exit_code=0 if ok else 7)


def recover_chatgpt_runtime(
    *,
    parts_dir: Path = DEFAULT_CHATGPT_PARTS_DIR,
    destination: Path = DEFAULT_CHATGPT_ROOT,
    base_zip_name: str | None = None,
    work_dir: Path | None = None,
    time_budget_seconds: float | None = 25.0,
    run_crc: bool = True,
    force_reextract: bool = False,
    start_runtime_daemon: bool = True,
    auto_attach_memory: bool = True,
    memory_zip_name: str | None = None,
    daemon_host: str = DEFAULT_DAEMON_HOST,
    daemon_port: int = DEFAULT_DAEMON_PORT,
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    startup_timeout: float = DEFAULT_START_TIMEOUT_SECONDS,
    trusted_time_iso: str | None = None,
    trusted_time_source: str | None = None,
    trusted_time_max_age_seconds: int | None = None,
) -> RecoveryResult:
    """Run the portable loader as a fail-closed, no-traceback host boundary."""

    try:
        return _recover_chatgpt_runtime_impl(
            parts_dir=parts_dir,
            destination=destination,
            base_zip_name=base_zip_name,
            work_dir=work_dir,
            time_budget_seconds=time_budget_seconds,
            run_crc=run_crc,
            force_reextract=force_reextract,
            start_runtime_daemon=start_runtime_daemon,
            auto_attach_memory=auto_attach_memory,
            memory_zip_name=memory_zip_name,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            heartbeat_interval=heartbeat_interval,
            startup_timeout=startup_timeout,
            trusted_time_iso=trusted_time_iso,
            trusted_time_source=trusted_time_source,
            trusted_time_max_age_seconds=trusted_time_max_age_seconds,
        )
    except PermissionError as exc:
        error = exc
        error_code = "runtime_bootstrap_path_unwritable"
        recovery_hint = "Wskaż zapisywalne destination i work-dir albo ustaw JAZN_RUNTIME_WORKSPACE_DIR."
    except FileNotFoundError as exc:
        error = exc
        error_code = "runtime_package_source_missing"
        recovery_hint = "Sprawdź parts-dir, nazwy części i wymagane sidecary paczki."
    except ValueError as exc:
        error = exc
        error_code = "runtime_package_contract_invalid"
        recovery_hint = "Użyj kompletnej paczki wygenerowanej przez bieżący generator Jaźni."
    except OSError as exc:
        error = exc
        error_code = "runtime_bootstrap_io_error"
        recovery_hint = "Sprawdź uprawnienia, wolne miejsce i czy destination/work-dir są dostępne."
    except Exception as exc:
        error = exc
        error_code = "runtime_bootstrap_failed"
        recovery_hint = "Zachowaj raport i zweryfikuj paczkę; runtime nie został uznany za aktywny."
    try:
        active_root = str(Path(destination).expanduser().resolve())
    except (OSError, RuntimeError):
        active_root = str(destination)
    return RecoveryResult(
        ok=False,
        state="bootstrap_blocked",
        active_root=active_root,
        report={
            "parts_dir": str(parts_dir),
            "destination": str(destination),
            "work_dir": str(work_dir) if work_dir is not None else None,
            "error": {
                "code": error_code,
                "type": type(error).__name__,
                "detail": str(error),
            },
            "recovery_hint": recovery_hint,
            "truth_boundary": (
                "Loader zakończył się przed potwierdzoną instalacją lub aktywacją. "
                "Host nie może na tej podstawie mówić głosem uruchomionej Jaźni."
            ),
        },
        exit_code=11,
    )


__all__ = [
    "DEFAULT_CHATGPT_PARTS_DIR",
    "DEFAULT_CHATGPT_ROOT",
    "RecoveryResult",
    "RuntimePreflightReport",
    "recover_chatgpt_runtime",
    "runtime_preflight",
]
