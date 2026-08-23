from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, IO, Iterable, Mapping
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile

from latka_jazn.core.package_integrity_manifest import sha256_file
from latka_jazn.db.runtime_sqlite import connect_runtime_readonly
from latka_jazn.memory.storage_limits import (
    DEFAULT_RAW_SEGMENT_MAX_BYTES,
    DEFAULT_RAW_SEGMENT_TARGET_BYTES,
)
from .memory_package_types import (
    MEMORY_FORMAT_VERSION_V3,
    MEMORY_MANIFEST_SCHEMA_V3,
    MEMORY_PACKAGE_MANIFEST_PATH,
    MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
    SQLITE_HEADER,
    TRANSIENT_DATABASE_SUFFIXES,
    inspect_sqlite_memory_file,
)
from .split_zip_package import (
    infer_base_zip_name,
    join_split_package_to_zip,
    load_package_expectations,
    load_package_set_metadata,
    resolve_renamed_package_parts,
    unsafe_zip_member_name,
)


LEGACY_REPACK_SCHEMA = "jazn_memory_legacy_repack/v1"
MEMORY_TRANSPORT_CONTRACT = "jazn_memory_package_transport/v1"
DEFAULT_SQLITE_TRANSPORT_MAX_BYTES = int(
    os.environ.get("JAZN_MEMORY_PACKAGE_SQLITE_MEMBER_MAX_BYTES", str(1024 * 1024 * 1024))
)
_COPY_BLOCK_BYTES = 4 * 1024 * 1024
_MAX_LEGACY_MANIFEST_BYTES = 16 * 1024 * 1024


class LegacyMemoryRepackError(RuntimeError):
    pass


def _safe_memory_path(value: str) -> str:
    text = str(value or "").replace("\\", "/").strip()
    reason = unsafe_zip_member_name(text)
    if reason:
        raise LegacyMemoryRepackError(f"unsafe legacy ZIP member {value!r}: {reason}")
    path = PurePosixPath(text)
    if not text or text.endswith("/") or not path.parts or path.parts[0] != "memory":
        raise LegacyMemoryRepackError(f"legacy package member is outside memory/: {value!r}")
    return path.as_posix()


def _load_sidecar(parts_dir: Path, base_zip_name: str) -> dict[str, Any]:
    path = parts_dir / f"{base_zip_name}.package.json"
    if not path.is_file():
        raise LegacyMemoryRepackError(f"legacy package sidecar missing: {path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyMemoryRepackError(f"invalid legacy package sidecar: {exc}") from exc
    if not isinstance(payload, dict):
        raise LegacyMemoryRepackError("legacy package sidecar must be a JSON object")
    if str(payload.get("schema_version") or "") not in {"jazn_package_set/v1", "jazn_package_set/v2"}:
        raise LegacyMemoryRepackError("legacy package sidecar schema is unsupported")
    if str(payload.get("profile") or "").strip().lower() != "memory":
        raise LegacyMemoryRepackError("legacy package sidecar is not profile=memory")
    return payload


def _expected_entries(sidecar: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = sidecar.get("entries")
    if not isinstance(rows, list) or not rows:
        raise LegacyMemoryRepackError("legacy package sidecar has no entry inventory")
    result: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            raise LegacyMemoryRepackError("legacy package entry inventory is invalid")
        relative = _safe_memory_path(str(item.get("path") or ""))
        if relative in result:
            raise LegacyMemoryRepackError(f"duplicate legacy package entry: {relative}")
        result[relative] = dict(item)
    return result


def _verify_expected_stream(
    relative: str,
    expected: Mapping[str, Any],
    *,
    size: int,
    sha256: str,
) -> None:
    expected_size = int(expected.get("size_bytes", -1))
    expected_sha = str(expected.get("sha256") or "").strip().lower()
    if size != expected_size:
        raise LegacyMemoryRepackError(
            f"legacy member size mismatch: {relative}: {size}!={expected_size}"
        )
    if not expected_sha or sha256 != expected_sha:
        raise LegacyMemoryRepackError(f"legacy member SHA-256 mismatch: {relative}")


def _zip_info_safe(info: zipfile.ZipInfo) -> str | None:
    if info.is_dir():
        return None
    relative = _safe_memory_path(info.filename)
    unix_type = (int(info.external_attr) >> 16) & 0o170000
    if unix_type == stat.S_IFLNK:
        raise LegacyMemoryRepackError(f"legacy ZIP symbolic link rejected: {relative}")
    return relative


def _zip_member_is_sqlite(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bool:
    if int(info.file_size) < len(SQLITE_HEADER):
        return False
    with archive.open(info, "r") as source:
        return source.read(len(SQLITE_HEADER)) == SQLITE_HEADER


def _inventory_archives(
    archive_paths: Iterable[Path], expected: Mapping[str, Mapping[str, Any]]
) -> list[tuple[Path, str, int]]:
    inventory: list[tuple[Path, str, int]] = []
    seen: set[str] = set()
    for archive_path in archive_paths:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for index, info in enumerate(archive.infolist()):
                relative = _zip_info_safe(info)
                if relative is None:
                    continue
                if relative in seen:
                    raise LegacyMemoryRepackError(f"duplicate ZIP member across legacy volumes: {relative}")
                seen.add(relative)
                if relative not in expected:
                    raise LegacyMemoryRepackError(f"legacy ZIP member missing from sidecar inventory: {relative}")
                if int(info.file_size) != int(expected[relative].get("size_bytes", -1)):
                    raise LegacyMemoryRepackError(f"legacy central-directory size mismatch: {relative}")
                inventory.append((archive_path, relative, index))
    missing = sorted(set(expected) - seen)
    if missing:
        raise LegacyMemoryRepackError(f"legacy sidecar entries missing from ZIP: {missing[:10]}")
    return inventory


def _member_plan(
    inventory: list[tuple[Path, str, int]],
    *,
    raw_target_bytes: int,
    raw_max_bytes: int,
    sqlite_max_bytes: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for archive_path, relative, info_index in inventory:
        with zipfile.ZipFile(archive_path, "r") as archive:
            info = archive.infolist()[info_index]
            if relative == MEMORY_PACKAGE_MANIFEST_PATH:
                action = "replace_transport_manifest"
            elif relative.lower().endswith(TRANSIENT_DATABASE_SUFFIXES):
                action = "reject_transient_database"
            elif _zip_member_is_sqlite(archive, info):
                action = "sqlite_online_backup_snapshot"
            elif relative.lower().endswith(".jsonl") and int(info.file_size) > raw_target_bytes:
                action = "jsonl_exact_line_segmentation"
            else:
                action = "copy_verified"
            if action == "sqlite_online_backup_snapshot":
                limit = sqlite_max_bytes
            elif action == "jsonl_exact_line_segmentation":
                limit = raw_max_bytes
            else:
                limit = max(raw_max_bytes, sqlite_max_bytes)
            rows.append(
                {
                    "path": relative,
                    "source_size_bytes": int(info.file_size),
                    "compressed_size_bytes": int(info.compress_size),
                    "action": action,
                    "target_member_limit_bytes": limit,
                }
            )
    return {
        "entry_count": len(rows),
        "segmented_jsonl_count": sum(row["action"] == "jsonl_exact_line_segmentation" for row in rows),
        "sqlite_snapshot_count": sum(row["action"] == "sqlite_online_backup_snapshot" for row in rows),
        "rejected_transient_database_count": sum(row["action"] == "reject_transient_database" for row in rows),
        "largest_source_members": sorted(rows, key=lambda row: int(row["source_size_bytes"]), reverse=True)[:20],
    }


def _zip_member_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def _volume_name(base_zip_name: str, part_no: int) -> str:
    if part_no == 1:
        return base_zip_name
    return f"{base_zip_name[:-4]}.part{part_no:03d}.zip"


def _package_set_hash(outputs: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(outputs, key=lambda row: int(row["part_no"])):
        digest.update(
            f"{item['part_no']}\0{item['filename']}\0{item['size_bytes']}\0{item['sha256']}\n".encode("utf-8")
        )
    return digest.hexdigest()


class _IndependentVolumeWriter:
    def __init__(self, root: Path, base_zip_name: str, *, compression_level: int) -> None:
        self.root = root
        self.base_zip_name = base_zip_name
        self.compression_level = compression_level
        self.outputs: list[dict[str, Any]] = []

    def write_stream(self, relative: str, source: IO[bytes]) -> tuple[dict[str, Any], dict[str, Any]]:
        part_no = len(self.outputs) + 1
        filename = _volume_name(self.base_zip_name, part_no)
        path = self.root / filename
        digest = hashlib.sha256()
        size = 0
        with zipfile.ZipFile(
            path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=self.compression_level,
            allowZip64=True,
            strict_timestamps=False,
        ) as archive:
            with archive.open(_zip_member_info(relative), "w", force_zip64=True) as target:
                while True:
                    chunk = source.read(_COPY_BLOCK_BYTES)
                    if not chunk:
                        break
                    target.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        output = {
            "part_no": part_no,
            "filename": filename,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "is_complete_zip": True,
        }
        self.outputs.append(output)
        entry = {
            "path": relative,
            "size_bytes": size,
            "sha256": digest.hexdigest(),
            "classification": "memory_file",
        }
        return output, entry

    def write_bytes(self, relative: str, payload: bytes, *, classification: str) -> dict[str, Any]:
        from io import BytesIO

        _output, entry = self.write_stream(relative, BytesIO(payload))
        entry["classification"] = classification
        return entry

    def write_file(self, relative: str, source: Path, *, classification: str) -> dict[str, Any]:
        with source.open("rb") as handle:
            _output, entry = self.write_stream(relative, handle)
        entry["classification"] = classification
        return entry

    def open_segment(self, relative: str) -> tuple[zipfile.ZipFile, IO[bytes], Path, int]:
        part_no = len(self.outputs) + 1
        filename = _volume_name(self.base_zip_name, part_no)
        path = self.root / filename
        archive = zipfile.ZipFile(
            path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=self.compression_level,
            allowZip64=True,
            strict_timestamps=False,
        )
        target = archive.open(_zip_member_info(relative), "w", force_zip64=True)
        return archive, target, path, part_no

    def close_segment(self, archive: zipfile.ZipFile, target: IO[bytes], path: Path, part_no: int) -> dict[str, Any]:
        target.close()
        archive.close()
        output = {
            "part_no": part_no,
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "is_complete_zip": True,
        }
        self.outputs.append(output)
        return output


def _segment_jsonl_member(
    source: IO[bytes],
    *,
    relative: str,
    writer: _IndependentVolumeWriter,
    target_bytes: int,
    max_bytes: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], int, str]:
    source_hash = hashlib.sha256()
    source_size = 0
    source_lines = 0
    segment_rows: list[dict[str, Any]] = []
    current_archive: zipfile.ZipFile | None = None
    current_target: IO[bytes] | None = None
    current_path: Path | None = None
    current_part_no = 0
    current_hash = hashlib.sha256()
    current_size = 0
    current_lines = 0
    current_first_line = 0
    segment_index = 0

    def close_current() -> None:
        nonlocal current_archive, current_target, current_path, current_part_no
        nonlocal current_hash, current_size, current_lines, current_first_line
        if current_archive is None or current_target is None or current_path is None:
            return
        package_path = f"{relative}.segments/segment-{segment_index:06d}.jsonl"
        writer.close_segment(current_archive, current_target, current_path, current_part_no)
        segment_rows.append(
            {
                "package_path": package_path,
                "segment_index": segment_index,
                "line_count": current_lines,
                "size_bytes": current_size,
                "sha256": current_hash.hexdigest(),
                "first_line_number": current_first_line,
                "last_line_number": current_first_line + current_lines - 1,
            }
        )
        current_archive = None
        current_target = None
        current_path = None
        current_part_no = 0
        current_hash = hashlib.sha256()
        current_size = 0
        current_lines = 0
        current_first_line = 0

    try:
        while True:
            line = source.readline(max_bytes + 1)
            if not line:
                break
            if len(line) > max_bytes:
                raise LegacyMemoryRepackError(
                    f"single JSONL line exceeds hard segment limit for {relative}: {len(line)}>{max_bytes}"
                )
            if current_target is not None and current_size + len(line) > target_bytes:
                close_current()
            if current_target is None:
                segment_index += 1
                current_first_line = source_lines + 1
                package_path = f"{relative}.segments/segment-{segment_index:06d}.jsonl"
                current_archive, current_target, current_path, current_part_no = writer.open_segment(package_path)
            current_target.write(line)
            current_hash.update(line)
            current_size += len(line)
            current_lines += 1
            source_hash.update(line)
            source_size += len(line)
            source_lines += 1
            if current_size > max_bytes:
                raise LegacyMemoryRepackError(f"segment exceeded hard size limit for {relative}")
        close_current()
    except Exception:
        if current_target is not None:
            try:
                current_target.close()
            except Exception:
                pass
        if current_archive is not None:
            try:
                current_archive.close()
            except Exception:
                pass
        raise
    descriptor = {
        "format": "jsonl_exact_line_segments/v1",
        "source_path": relative,
        "source_size_bytes": source_size,
        "source_sha256": source_hash.hexdigest(),
        "source_line_count": source_lines,
        "segments": segment_rows,
    }
    entries = [
        {
            "path": row["package_path"],
            "size_bytes": row["size_bytes"],
            "sha256": row["sha256"],
            "classification": "memory_raw_segment",
        }
        for row in segment_rows
    ]
    return entries, descriptor, source_size, source_hash.hexdigest()


def _extract_verified_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    expected: Mapping[str, Any],
    destination: Path,
) -> None:
    digest = hashlib.sha256()
    size = 0
    with archive.open(info, "r") as source, destination.open("wb") as target:
        while True:
            chunk = source.read(_COPY_BLOCK_BYTES)
            if not chunk:
                break
            target.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        target.flush()
        os.fsync(target.fileno())
    _verify_expected_stream(info.filename, expected, size=size, sha256=digest.hexdigest())


def _sqlite_online_backup(source: Path, destination: Path) -> dict[str, Any]:
    source_connection = connect_runtime_readonly(source, timeout_ms=30_000)
    target_connection = sqlite3.connect(destination, timeout=30.0)
    try:
        source_connection.execute("PRAGMA busy_timeout=30000")
        source_connection.backup(target_connection, pages=2048, sleep=0.01)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()
    report = inspect_sqlite_memory_file(destination)
    if report.get("ok") is not True:
        raise LegacyMemoryRepackError(f"SQLite snapshot validation failed: {source.name}")
    return report


def _legacy_manifest_bytes(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    expected: Mapping[str, Any],
) -> dict[str, Any] | None:
    if int(info.file_size) > _MAX_LEGACY_MANIFEST_BYTES:
        raise LegacyMemoryRepackError("legacy memory manifest exceeds safe metadata limit")
    payload = archive.read(info)
    _verify_expected_stream(
        info.filename,
        expected,
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def repack_legacy_memory_package(
    parts_dir: Path,
    *,
    output_dir: Path,
    base_zip_name: str | None = None,
    output_zip_name: str | None = None,
    work_dir: Path | None = None,
    raw_target_bytes: int = DEFAULT_RAW_SEGMENT_TARGET_BYTES,
    raw_max_bytes: int = DEFAULT_RAW_SEGMENT_MAX_BYTES,
    sqlite_max_bytes: int = DEFAULT_SQLITE_TRANSPORT_MAX_BYTES,
    compression_level: int = 6,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    parts_dir = Path(parts_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if raw_target_bytes < 1024 * 1024 or raw_max_bytes < raw_target_bytes:
        raise LegacyMemoryRepackError("invalid JSONL segmentation limits")
    if sqlite_max_bytes < 1024 * 1024:
        raise LegacyMemoryRepackError("invalid SQLite transport limit")
    package_member_limit = max(raw_max_bytes, sqlite_max_bytes)
    base = infer_base_zip_name(parts_dir, base_zip_name)
    package_set = load_package_set_metadata(parts_dir, base)
    if package_set.get("source") != "package.json" or str(package_set.get("profile") or "") != "memory":
        raise LegacyMemoryRepackError("source must be a sidecar-declared profile=memory package")
    sidecar = _load_sidecar(parts_dir, base)
    expected_entries = _expected_entries(sidecar)
    output_name = str(output_zip_name or f"{base[:-4]}-v3.zip").strip()
    if (
        not output_name.lower().endswith(".zip")
        or Path(output_name).name != output_name
        or "/" in output_name
        or "\\" in output_name
        or output_name in {".", ".."}
    ):
        raise LegacyMemoryRepackError("output ZIP name must be a simple .zip filename")

    workspace = Path(work_dir).expanduser().resolve() if work_dir else Path(
        tempfile.mkdtemp(prefix="jazn-memory-legacy-repack-")
    )
    owns_workspace = work_dir is None
    canonical = workspace / "canonical_parts"
    source_area = workspace / "source"
    source_area.mkdir(parents=True, exist_ok=True)
    if canonical.exists():
        shutil.rmtree(canonical)
    expectations, expected_full_sha256, _source = load_package_expectations(parts_dir, base)
    resolution = resolve_renamed_package_parts(parts_dir, expectations, canonical_dir=canonical, skip_part_hash=False)
    archive_format = str(package_set.get("archive_format") or "").lower()
    if archive_format == "binary":
        source_zip = join_split_package_to_zip(canonical, base, zip_out=source_area / base, force=True)
        if expected_full_sha256 and sha256_file(source_zip).lower() != expected_full_sha256.lower():
            raise LegacyMemoryRepackError("legacy logical ZIP SHA-256 mismatch after verified join")
        archive_paths = [source_zip]
    elif archive_format == "independent":
        archive_paths = [canonical / item.filename for item in expectations]
    else:
        raise LegacyMemoryRepackError(f"unsupported legacy archive format: {archive_format}")

    inventory = _inventory_archives(archive_paths, expected_entries)
    plan = _member_plan(
        inventory,
        raw_target_bytes=raw_target_bytes,
        raw_max_bytes=raw_max_bytes,
        sqlite_max_bytes=sqlite_max_bytes,
    )
    report: dict[str, Any] = {
        "schema_version": LEGACY_REPACK_SCHEMA,
        "ok": True,
        "state": "legacy_memory_repack_planned" if dry_run else "legacy_memory_repacked",
        "source_parts_dir": str(parts_dir),
        "source_package_name": base,
        "source_archive_format": archive_format,
        "source_package_version": sidecar.get("package_version"),
        "part_resolution": resolution,
        "output_dir": str(output_dir),
        "output_package_name": output_name,
        "raw_segment_target_bytes": raw_target_bytes,
        "raw_segment_max_bytes": raw_max_bytes,
        "sqlite_snapshot_max_bytes": sqlite_max_bytes,
        "package_member_limit_bytes": package_member_limit,
        "plan": plan,
        "dry_run": dry_run,
        "truth_boundary": (
            (
                "Legacy repack dry-run verifies package-set metadata, package-part hashes and ZIP central-directory inventory; "
                "it does not claim full source-member SHA verification until the actual repack streams each member. "
            )
            if dry_run
            else (
                "Legacy repack verifies source package-part hashes and every streamed source member against the legacy sidecar. "
                "Oversized JSONL is transformed only as exact line-preserving transport segments; SQLite is copied through "
                "the SQLite Online Backup API. The output remains an inactive profile=memory transport package."
            )
        ),
    }
    if dry_run:
        if owns_workspace:
            shutil.rmtree(workspace, ignore_errors=True)
        return report
    if plan["rejected_transient_database_count"]:
        raise LegacyMemoryRepackError("legacy package contains WAL/SHM/transient database files")

    output_dir.mkdir(parents=True, exist_ok=True)
    stage = output_dir / f".{output_name}.repack-{uuid.uuid4().hex}"
    stage.mkdir(parents=True, exist_ok=False)
    writer = _IndependentVolumeWriter(stage, output_name, compression_level=compression_level)
    new_entries: list[dict[str, Any]] = []
    databases: list[dict[str, Any]] = []
    raw_segments: list[dict[str, Any]] = []
    legacy_memory_manifest: dict[str, Any] | None = None
    try:
        for archive_path in archive_paths:
            with zipfile.ZipFile(archive_path, "r") as archive:
                for info in archive.infolist():
                    relative = _zip_info_safe(info)
                    if relative is None:
                        continue
                    expected = expected_entries[relative]
                    if relative == MEMORY_PACKAGE_MANIFEST_PATH:
                        legacy_memory_manifest = _legacy_manifest_bytes(archive, info, expected)
                        continue
                    if relative.lower().endswith(TRANSIENT_DATABASE_SUFFIXES):
                        raise LegacyMemoryRepackError(f"transient database member rejected: {relative}")
                    if _zip_member_is_sqlite(archive, info):
                        with tempfile.TemporaryDirectory(dir=workspace, prefix="sqlite-") as td:
                            temp = Path(td)
                            legacy_db = temp / "legacy.sqlite3"
                            snapshot = temp / "snapshot.sqlite3"
                            _extract_verified_member(archive, info, expected, legacy_db)
                            db_report = _sqlite_online_backup(legacy_db, snapshot)
                            if snapshot.stat().st_size > sqlite_max_bytes:
                                raise LegacyMemoryRepackError(
                                    f"SQLite snapshot exceeds transport limit for {relative}: "
                                    f"{snapshot.stat().st_size}>{sqlite_max_bytes}; shard/roll before packaging"
                                )
                            entry = writer.write_file(relative, snapshot, classification="memory_sqlite_snapshot")
                            new_entries.append(entry)
                            databases.append(
                                {
                                    "path": relative,
                                    "snapshot_method": "sqlite_online_backup_api",
                                    "size_bytes": entry["size_bytes"],
                                    "sha256": entry["sha256"],
                                    "user_version": db_report.get("user_version"),
                                    "application_id": db_report.get("application_id"),
                                    "database_identity": db_report.get("database_identity"),
                                    "table_count": db_report.get("table_count"),
                                }
                            )
                        continue
                    if relative.lower().endswith(".jsonl") and int(info.file_size) > raw_target_bytes:
                        with archive.open(info, "r") as source:
                            segment_entries, descriptor, source_size, source_sha = _segment_jsonl_member(
                                source,
                                relative=relative,
                                writer=writer,
                                target_bytes=raw_target_bytes,
                                max_bytes=raw_max_bytes,
                            )
                        _verify_expected_stream(relative, expected, size=source_size, sha256=source_sha)
                        new_entries.extend(segment_entries)
                        raw_segments.append(descriptor)
                        continue
                    if int(info.file_size) > package_member_limit:
                        raise LegacyMemoryRepackError(
                            f"non-segmentable member exceeds package limit: {relative}: {info.file_size}>{package_member_limit}"
                        )
                    with archive.open(info, "r") as source:
                        _output, entry = writer.write_stream(relative, source)
                    _verify_expected_stream(
                        relative,
                        expected,
                        size=int(entry["size_bytes"]),
                        sha256=str(entry["sha256"]),
                    )
                    entry["classification"] = str(expected.get("classification") or "memory_file")
                    new_entries.append(entry)

        created_at = datetime.now(timezone.utc).isoformat()
        created_with_runtime = str(
            (legacy_memory_manifest or {}).get("runtime_version")
            or sidecar.get("package_version")
            or "legacy-memory-package"
        )
        manifest = {
            "schema_version": MEMORY_MANIFEST_SCHEMA_V3,
            "memory_format_version": MEMORY_FORMAT_VERSION_V3,
            "snapshot_id": str(uuid.uuid4()),
            "created_at_utc": created_at,
            "generated_at_utc": created_at,
            "created_with_runtime": created_with_runtime,
            "compatibility": {
                "contract": MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
                "runtime_version_is_provenance_only": True,
                "memory_format_version": MEMORY_FORMAT_VERSION_V3,
                "manifest_schema": MEMORY_MANIFEST_SCHEMA_V3,
            },
            "file_count": len(new_entries),
            "files": sorted(new_entries, key=lambda item: str(item["path"])),
            "databases": sorted(databases, key=lambda item: str(item["path"])),
            "raw_segments": sorted(raw_segments, key=lambda item: str(item["source_path"])),
            "package_member_limit_bytes": package_member_limit,
            "raw_segment_member_limit_bytes": raw_max_bytes,
            "sqlite_snapshot_member_limit_bytes": sqlite_max_bytes,
            "transport_contract": MEMORY_TRANSPORT_CONTRACT,
            "legacy_source": {
                "package_name": base,
                "package_version": sidecar.get("package_version"),
                "logical_zip_sha256": sidecar.get("logical_zip_sha256"),
                "package_set_sha256": sidecar.get("package_set_sha256"),
                "manifest_schema": (legacy_memory_manifest or {}).get("schema_version"),
            },
            "truth_boundary": (
                "This v3 package was migrated from a verified legacy memory transport. Source member bytes were "
                "checked against the legacy sidecar before transformation. JSONL segmentation is byte-exact and "
                "SQLite output is a complete Online Backup API snapshot. Runtime version is provenance only."
            ),
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        manifest_entry = writer.write_bytes(
            MEMORY_PACKAGE_MANIFEST_PATH, manifest_bytes, classification="memory_package_manifest"
        )
        sidecar_entries = sorted(new_entries + [manifest_entry], key=lambda item: str(item["path"]))
        output_sidecar = {
            "schema_version": "jazn_package_set/v2",
            "generator": "memory_package_legacy_repack.py",
            "generator_version": "1.0",
            "created_at_utc": created_at,
            "source_root": str(parts_dir),
            "package_name": output_name,
            "profile": "memory",
            "archive_format": "independent",
            "package_version": "memory-format-v3",
            "part_size_bytes": raw_target_bytes,
            "compression": "ZIP_DEFLATED",
            "compression_level": compression_level,
            "scan_method": "verified_legacy_package_stream_repack",
            "manifest_builder": "memory_v3_legacy_repack+sqlite_online_backup+raw_jsonl_segmentation",
            "plan_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "entry_count": len(sidecar_entries),
            "source_total_size_bytes": sum(int(item["size_bytes"]) for item in sidecar_entries),
            "logical_zip_sha256": None,
            "package_set_sha256": _package_set_hash(writer.outputs),
            "outputs": writer.outputs,
            "entries": sidecar_entries,
            "excluded_count": 0,
            "excluded_sample": [],
            "verification": {
                "ok": True,
                "source_parts_sha_verified": True,
                "source_entry_sha_verified": True,
                "sqlite_online_backup_verified": True,
                "raw_jsonl_segmented_exactly": True,
            },
            "memory_manifest_schema": MEMORY_MANIFEST_SCHEMA_V3,
            "memory_format_version": MEMORY_FORMAT_VERSION_V3,
            "memory_compatibility_contract": MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
            "created_with_runtime": created_with_runtime,
            "runtime_version_is_provenance_only": True,
            "memory_transport_contract": MEMORY_TRANSPORT_CONTRACT,
            "cloud_attach_compatible": True,
            "cloud_object_layout": {
                "kind": "flat_package_set",
                "provider": "s3_compatible",
                "required_objects": [item["filename"] for item in writer.outputs],
                "sidecar": f"{output_name}.package.json",
            },
        }
        sidecar_path = stage / f"{output_name}.package.json"
        sidecar_path.write_text(
            json.dumps(output_sidecar, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (stage / f"{output_name}.parts.sha256").write_text(
            "".join(f"{item['sha256']}  {item['filename']}\n" for item in writer.outputs),
            encoding="utf-8",
        )

        final_paths: list[str] = []
        for source in sorted(stage.iterdir()):
            destination = output_dir / source.name
            if destination.exists() and not force:
                raise FileExistsError(destination)
            if destination.exists():
                destination.unlink()
            os.replace(source, destination)
            final_paths.append(str(destination))
        stage.rmdir()
        report.update(
            {
                "output_count": len(writer.outputs),
                "output_files": final_paths,
                "memory_manifest": manifest,
                "package_sidecar": output_sidecar,
            }
        )
        return report
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    finally:
        if owns_workspace:
            shutil.rmtree(workspace, ignore_errors=True)


__all__ = [
    "DEFAULT_SQLITE_TRANSPORT_MAX_BYTES",
    "LEGACY_REPACK_SCHEMA",
    "LegacyMemoryRepackError",
    "repack_legacy_memory_package",
]
