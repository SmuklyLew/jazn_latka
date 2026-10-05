from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import sqlite3
import uuid
from threading import Event
from typing import Any, Callable

from latka_jazn.db.runtime_sqlite import connect_runtime_readonly
from latka_jazn.memory.storage_limits import (
    DEFAULT_MAX_SQLITE_FILE_BYTES,
    DEFAULT_RAW_SEGMENT_MAX_BYTES,
    DEFAULT_RAW_SEGMENT_TARGET_BYTES,
)
from latka_jazn.packaging.memory_package_types import (
    MEMORY_FORMAT_VERSION_V3,
    MEMORY_MANIFEST_SCHEMA_V3,
    MEMORY_PACKAGE_MANIFEST_PATH,
    MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
    SQLITE_HEADER,
    inspect_sqlite_memory_file,
)
from latka_jazn.packaging.memory_raw_segmentation import (
    RawJsonlSegmenter,
    RawMemorySegmentationPolicy,
)

from .errors import PackCancelled, PackIntegrityError
from .models import PackPlan, ProgressEvent, SourceEntry

ProgressCallback = Callable[[ProgressEvent], None]
_CHUNK = 4 * 1024 * 1024
_SAMPLE = 64 * 1024
_MEMORY_RAW_SEGMENT_TARGET_BYTES = DEFAULT_RAW_SEGMENT_TARGET_BYTES
_MEMORY_RAW_SEGMENT_MAX_BYTES = DEFAULT_RAW_SEGMENT_MAX_BYTES
_MEMORY_SQLITE_MAX_BYTES = DEFAULT_MAX_SQLITE_FILE_BYTES
_MEMORY_TRANSPORT_CONTRACT = "jazn_memory_package_transport/v1"


@dataclass(frozen=True, slots=True)
class AttributeState:
    text: bool | str | None = None
    eol: str | None = None


@dataclass(frozen=True, slots=True)
class StagingResult:
    plan: PackPlan
    member_sha256: dict[str, str]
    eol_checked_count: int = 0
    eol_skipped_count: int = 0
    eol_warning_paths: tuple[str, ...] = ()
    staging_mode: str = "source-folder-byte-copy"
    canonical_release_bytes: bool = False
    release_report: dict[str, object] | None = None
    byte_exact_source_copy: bool = True

    def verification_metadata(self) -> dict[str, object]:
        if self.canonical_release_bytes:
            report = dict(self.release_report or {})
            return {
                "staging_mode": self.staging_mode,
                "byte_exact_source_copy": False,
                "canonical_release_bytes": True,
                "eol_policy": "canonical_git_blobs_fail_closed",
                "eol_checked_count": self.eol_checked_count,
                "eol_skipped_count": self.eol_skipped_count,
                "eol_warning_count": 0,
                "eol_warning_sample": [],
                "release_source_commit": report.get("source_commit"),
                "release_source_tree": report.get("source_tree"),
                "release_status": report.get("status"),
            }
        return {
            "staging_mode": self.staging_mode,
            "byte_exact_source_copy": self.byte_exact_source_copy,
            "canonical_release_bytes": False,
            "memory_native_v3": self.staging_mode == "memory-native-v3-staging",
            "eol_policy": "diagnostic_only",
            "eol_checked_count": self.eol_checked_count,
            "eol_skipped_count": self.eol_skipped_count,
            "eol_warning_count": len(self.eol_warning_paths),
            "eol_warning_sample": list(self.eol_warning_paths[:100]),
        }


def _cancel(event: Event | None) -> None:
    if event is not None and event.is_set():
        raise PackCancelled("Operacja została anulowana.")


def _emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    if callback is not None:
        callback(event)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_exact(
    source: Path,
    target: Path,
    *,
    expected_size: int,
    archive_path: str,
    callback: ProgressCallback | None,
    cancel_event: Event | None,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    digest = hashlib.sha256()
    written = 0
    with source.open("rb") as src, target.open("wb") as dst:
        while True:
            _cancel(cancel_event)
            chunk = src.read(_CHUNK)
            if not chunk:
                break
            dst.write(chunk)
            digest.update(chunk)
            written += len(chunk)
            _emit(callback, ProgressEvent("staging", "Source folder byte-exact staging", written, expected_size, archive_path))
    after = source.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise PackIntegrityError(f"Źródło zmieniło się podczas stagingu: {archive_path}")
    if written != expected_size or written != before.st_size:
        raise PackIntegrityError(f"Rozmiar źródła zmienił się od skanowania: {archive_path}")
    observed = digest.hexdigest()
    if _sha(target) != observed:
        raise PackIntegrityError(f"Staging nie jest byte-exact dla: {archive_path}")
    shutil.copystat(source, target, follow_symlinks=False)
    return observed


def _parse_rules(root: Path) -> list[tuple[str, list[str]]]:
    path = root / ".gitattributes"
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return []
    rules: list[tuple[str, list[str]]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            tokens = shlex.split(stripped, comments=True, posix=True)
        except ValueError:
            continue
        if len(tokens) >= 2:
            rules.append((tokens[0], tokens[1:]))
    return rules


def attribute_state_for_path(path: PurePosixPath, rules: list[tuple[str, list[str]]]) -> AttributeState:
    text: bool | str | None = None
    eol: str | None = None
    normalized = path.as_posix()
    for pattern, attrs in rules:
        matched = fnmatch.fnmatchcase(path.name if "/" not in pattern else normalized, pattern)
        if not matched:
            continue
        for token in attrs:
            if token == "binary" or token == "-text":
                text = False
            elif token == "text":
                text = True
            elif token == "text=auto":
                text = "auto"
            elif token == "!text":
                text = None
            elif token.startswith("eol=") and token[4:].casefold() in {"lf", "crlf"}:
                eol = token[4:].casefold()
            elif token == "!eol":
                eol = None
    return AttributeState(text=text, eol=eol)


def _eol_conforms(path: Path, expected: str, auto_text: bool) -> bool | None:
    data = path.read_bytes()
    if auto_text:
        sample = data[:_SAMPLE]
        if b"\x00" in sample:
            return None
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if expected == "lf":
        return b"\r" not in data
    if expected == "crlf":
        normalized = data.replace(b"\r\n", b"")
        return b"\r" not in normalized and b"\n" not in normalized
    return True


def _is_sqlite_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def _write_json_durable(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _snapshot_sqlite_memory(source: Path, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    try:
        with closing(connect_runtime_readonly(source, timeout_ms=30_000)) as source_connection:
            with closing(sqlite3.connect(target, timeout=30.0)) as target_connection:
                target_connection.execute("PRAGMA busy_timeout=30000")
                source_connection.backup(
                    target_connection,
                    pages=2048,
                    sleep=0.01,
                )
                target_connection.commit()
                journal_row = target_connection.execute(
                    "PRAGMA journal_mode=DELETE"
                ).fetchone()
                journal_mode = "" if journal_row is None else str(journal_row[0]).casefold()
                if journal_mode != "delete":
                    raise PackIntegrityError(
                        f"SQLite snapshot could not switch to single-file journal mode: {source}"
                    )
                target_connection.commit()
        target.with_name(target.name + "-wal").unlink(missing_ok=True)
        target.with_name(target.name + "-shm").unlink(missing_ok=True)
        report = inspect_sqlite_memory_file(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if report.get("ok") is not True:
        target.unlink(missing_ok=True)
        raise PackIntegrityError(
            f"SQLite Online Backup snapshot failed integrity gates: {source}"
        )
    if target.stat().st_size > _MEMORY_SQLITE_MAX_BYTES:
        target.unlink(missing_ok=True)
        raise PackIntegrityError(
            f"SQLite snapshot exceeds MEMORY package member limit: {source}"
        )
    return {
        "path": str(target),
        "size_bytes": int(report["size_bytes"]),
        "sha256": str(report["sha256"]),
        "quick_check": str(report["quick_check"]),
        "foreign_key_error_count": int(report["foreign_key_error_count"]),
        "user_version": int(report["user_version"]),
        "application_id": int(report["application_id"]),
        "database_identity": report.get("database_identity"),
        "table_count": int(report["table_count"]),
    }


def _materialize_memory_v3_staging(
    plan: PackPlan,
    destination: Path,
    *,
    callback: ProgressCallback | None,
    cancel_event: Event | None,
) -> StagingResult:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    entries: list[SourceEntry] = []
    hashes: dict[str, str] = {}
    files: list[dict[str, object]] = []
    databases: list[dict[str, object]] = []
    raw_segments: list[dict[str, object]] = []

    for entry in plan.entries:
        _cancel(cancel_event)
        relative = entry.archive_path.rstrip("/")
        if relative == MEMORY_PACKAGE_MANIFEST_PATH:
            continue
        target = destination / Path(*PurePosixPath(relative).parts)
        if entry.is_dir:
            target.mkdir(parents=True, exist_ok=True)
            entries.append(replace(entry, source=target))
            continue

        if _is_sqlite_file(entry.source):
            report = _snapshot_sqlite_memory(entry.source, target)
            digest = str(report["sha256"])
            size = int(report["size_bytes"])
            entries.append(SourceEntry(target, relative, size, False))
            hashes[relative] = digest
            files.append(
                {
                    "path": relative,
                    "size_bytes": size,
                    "sha256": digest,
                    "classification": "memory_sqlite_snapshot",
                }
            )
            databases.append(
                {
                    "path": relative,
                    "role": "sqlite_memory",
                    "snapshot_method": "sqlite_online_backup_api",
                    "size_bytes": size,
                    "sha256": digest,
                    "user_version": report["user_version"],
                    "application_id": report["application_id"],
                    "database_identity": report["database_identity"],
                }
            )
            _emit(
                callback,
                ProgressEvent(
                    "staging",
                    "SQLite Online Backup snapshot",
                    size,
                    size,
                    relative,
                ),
            )
            continue

        if (
            relative.lower().endswith(".jsonl")
            and entry.size_bytes > _MEMORY_RAW_SEGMENT_TARGET_BYTES
        ):
            segmenter = RawJsonlSegmenter(
                RawMemorySegmentationPolicy(
                    target_segment_bytes=_MEMORY_RAW_SEGMENT_TARGET_BYTES,
                    max_segment_bytes=_MEMORY_RAW_SEGMENT_MAX_BYTES,
                )
            )
            descriptor = segmenter.segment(
                entry.source,
                source_relative=relative,
                staging_root=destination,
            )
            raw_segments.append(descriptor.to_dict())
            for segment in descriptor.segments:
                segment_source = destination / Path(
                    *PurePosixPath(segment.package_path).parts
                )
                entries.append(
                    SourceEntry(
                        segment_source,
                        segment.package_path,
                        int(segment.size_bytes),
                        False,
                    )
                )
                hashes[segment.package_path] = segment.sha256
                files.append(
                    {
                        "path": segment.package_path,
                        "size_bytes": int(segment.size_bytes),
                        "sha256": segment.sha256,
                        "classification": "memory_raw_segment",
                    }
                )
            _emit(
                callback,
                ProgressEvent(
                    "staging",
                    "Segmentowanie MEMORY JSONL",
                    int(descriptor.source_size_bytes),
                    int(descriptor.source_size_bytes),
                    relative,
                ),
            )
            continue

        digest = _copy_exact(
            entry.source,
            target,
            expected_size=entry.size_bytes,
            archive_path=relative,
            callback=callback,
            cancel_event=cancel_event,
        )
        entries.append(SourceEntry(target, relative, entry.size_bytes, False))
        hashes[relative] = digest
        files.append(
            {
                "path": relative,
                "size_bytes": int(entry.size_bytes),
                "sha256": digest,
                "classification": "memory_file",
            }
        )

    created = datetime.now(timezone.utc).isoformat()
    member_limit = max(_MEMORY_RAW_SEGMENT_MAX_BYTES, _MEMORY_SQLITE_MAX_BYTES)
    manifest: dict[str, object] = {
        "schema_version": MEMORY_MANIFEST_SCHEMA_V3,
        "memory_format_version": MEMORY_FORMAT_VERSION_V3,
        "snapshot_id": str(uuid.uuid4()),
        "created_at_utc": created,
        "generated_at_utc": created,
        "created_with_runtime": plan.package_version,
        "compatibility": {
            "contract": MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
            "runtime_version_is_provenance_only": True,
            "memory_format_version": MEMORY_FORMAT_VERSION_V3,
            "manifest_schema": MEMORY_MANIFEST_SCHEMA_V3,
        },
        "file_count": len(files),
        "files": sorted(files, key=lambda item: str(item["path"])),
        "databases": sorted(databases, key=lambda item: str(item["path"])),
        "raw_segments": sorted(
            raw_segments,
            key=lambda item: str(item.get("source_path") or ""),
        ),
        "package_member_limit_bytes": member_limit,
        "raw_segment_member_limit_bytes": _MEMORY_RAW_SEGMENT_MAX_BYTES,
        "sqlite_snapshot_member_limit_bytes": _MEMORY_SQLITE_MAX_BYTES,
        "transport_contract": _MEMORY_TRANSPORT_CONTRACT,
        "truth_boundary": (
            "MEMORY package bytes are generated from a bounded native-v3 staging tree. "
            "SQLite databases are consistent Online Backup API snapshots; WAL/SHM files "
            "are transport-excluded. Oversized raw JSONL is represented only by exact "
            "bounded segments and is reconstructed while attaching."
        ),
    }
    manifest_path = destination / Path(*PurePosixPath(MEMORY_PACKAGE_MANIFEST_PATH).parts)
    _write_json_durable(manifest_path, manifest)
    manifest_digest = _sha(manifest_path)
    entries.append(
        SourceEntry(
            manifest_path,
            MEMORY_PACKAGE_MANIFEST_PATH,
            manifest_path.stat().st_size,
            False,
        )
    )
    hashes[MEMORY_PACKAGE_MANIFEST_PATH] = manifest_digest

    staged_plan = replace(
        plan,
        entries=tuple(entries),
        source_total_size_bytes=sum(
            item.size_bytes for item in entries if not item.is_dir
        ),
    )
    return StagingResult(
        staged_plan,
        hashes,
        eol_checked_count=0,
        eol_skipped_count=len(files),
        eol_warning_paths=(),
        staging_mode="memory-native-v3-staging",
        canonical_release_bytes=False,
        release_report={
            "memory_manifest_schema": MEMORY_MANIFEST_SCHEMA_V3,
            "memory_format_version": MEMORY_FORMAT_VERSION_V3,
            "sqlite_snapshot_count": len(databases),
            "raw_segment_source_count": len(raw_segments),
        },
        byte_exact_source_copy=False,
    )


def materialize_source_staging(
    plan: PackPlan,
    destination: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> StagingResult:
    if plan.request.content.value == "memory":
        return _materialize_memory_v3_staging(
            plan,
            destination,
            callback=callback,
            cancel_event=cancel_event,
        )
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    source_root = plan.request.source_root.resolve()
    rules = _parse_rules(source_root) if plan.request.content.value != "memory" else []
    entries: list[SourceEntry] = []
    hashes: dict[str, str] = {}
    checked = skipped = 0
    warnings: list[str] = []
    for entry in plan.entries:
        _cancel(cancel_event)
        target = destination / Path(*PurePosixPath(entry.archive_path.rstrip("/")).parts)
        if entry.is_dir:
            target.mkdir(parents=True, exist_ok=True)
            entries.append(replace(entry, source=target))
            continue
        expected: str | None = None
        auto = False
        try:
            relative = entry.source.resolve().relative_to(source_root)
        except ValueError:
            relative = None
        if relative is not None and not entry.archive_path.startswith("memory/") and rules:
            state = attribute_state_for_path(PurePosixPath(relative.as_posix()), rules)
            expected = state.eol if state.text is not False else None
            auto = state.text == "auto"
        if expected:
            result = _eol_conforms(entry.source, expected, auto)
            if result is None:
                skipped += 1
            else:
                checked += 1
                if not result:
                    warnings.append(entry.archive_path)
        else:
            skipped += 1
        hashes[entry.archive_path] = _copy_exact(entry.source, target, expected_size=entry.size_bytes, archive_path=entry.archive_path, callback=callback, cancel_event=cancel_event)
        entries.append(replace(entry, source=target))
    return StagingResult(replace(plan, entries=tuple(entries)), hashes, checked, skipped, tuple(warnings))


def _run_release_staging(source_root: Path, destination: Path) -> dict[str, object]:
    from latka_jazn.tools.release_staging import create_release_staging, create_system_smoke_staging
    if (source_root / ".git").exists():
        return dict(create_release_staging(source_root, destination))
    return dict(create_system_smoke_staging(source_root, destination))


def _canonical_system_entries(destination: Path) -> tuple[list[SourceEntry], dict[str, str]]:
    manifest_path = destination / "PACKAGE_INTEGRITY_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackIntegrityError(f"Nie można odczytać kanonicznego manifestu SYSTEM: {exc}") from exc
    rows = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(rows, list):
        raise PackIntegrityError("Kanoniczny PACKAGE_INTEGRITY_MANIFEST.json nie zawiera listy files.")
    entries: list[SourceEntry] = []
    hashes: dict[str, str] = {}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PackIntegrityError("Niepoprawny wpis files w kanonicznym manifeście SYSTEM.")
        rel = str(row.get("path") or "").replace("\\", "/").strip("/")
        if not rel or rel in seen:
            raise PackIntegrityError(f"Niepoprawny lub zduplikowany path w manifeście SYSTEM: {rel!r}")
        source = destination / Path(*PurePosixPath(rel).parts)
        expected_sha = str(row.get("sha256") or "").lower()
        raw_size = row.get("size_bytes")
        if not isinstance(raw_size, (int, float, str)):
            raise PackIntegrityError(f"Niepoprawny rozmiar w manifeście SYSTEM: {rel!r}")
        try:
            expected_size = int(raw_size)
        except ValueError as exc:
            raise PackIntegrityError(f"Niepoprawny rozmiar w manifeście SYSTEM: {rel!r}") from exc
        if not source.is_file() or source.stat().st_size != expected_size or _sha(source) != expected_sha:
            raise PackIntegrityError(f"Kanoniczny staging nie zgadza się z manifestem dla {rel}")
        seen.add(rel)
        entries.append(SourceEntry(source, rel, expected_size, False))
        hashes[rel] = expected_sha
    if "PACKAGE_INTEGRITY_MANIFEST.json" not in seen:
        digest = _sha(manifest_path)
        entries.append(SourceEntry(manifest_path, "PACKAGE_INTEGRITY_MANIFEST.json", manifest_path.stat().st_size, False))
        hashes["PACKAGE_INTEGRITY_MANIFEST.json"] = digest
    return entries, hashes


def materialize_canonical_staging(
    plan: PackPlan,
    destination: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> StagingResult:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    report = _run_release_staging(plan.request.source_root.resolve(), destination)
    system_entries, hashes = _canonical_system_entries(destination)
    entries = list(system_entries)
    for entry in plan.entries:
        if not entry.archive_path.startswith("memory/"):
            continue
        _cancel(cancel_event)
        target = destination / Path(*PurePosixPath(entry.archive_path.rstrip("/")).parts)
        if entry.is_dir:
            target.mkdir(parents=True, exist_ok=True)
            entries.append(replace(entry, source=target))
            continue
        hashes[entry.archive_path] = _copy_exact(entry.source, target, expected_size=entry.size_bytes, archive_path=entry.archive_path, callback=callback, cancel_event=cancel_event)
        entries.append(replace(entry, source=target))
    staged_plan = replace(plan, entries=tuple(entries), source_total_size_bytes=sum(e.size_bytes for e in entries if not e.is_dir))
    return StagingResult(
        staged_plan,
        hashes,
        eol_checked_count=0,
        eol_skipped_count=len(system_entries),
        staging_mode="canonical-release-staging",
        canonical_release_bytes=True,
        release_report=report,
    )
