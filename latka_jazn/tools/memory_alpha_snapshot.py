"""Fail-closed operator snapshot for alpha MEMORY; no activation or restore.

Every SQLite file is backed up through the existing SQLite Backup API.  This
does not prove global atomicity across separate databases and JSON/JSONL files:
the caller must independently quiesce all writers before invoking create.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable
import hashlib
import json
import os
import sqlite3
import stat
import time
import uuid

from latka_jazn.tools.sqlite_archive_snapshot import create_sqlite_snapshot
from latka_jazn.version import PACKAGE_VERSION

SCHEMA = "jazn_memory_alpha_snapshot_evidence/v1"
EVIDENCE = "ALPHA_SNAPSHOT_EVIDENCE.json"
SQLITE_EXTENSIONS = frozenset({".sqlite3", ".sqlite", ".db"})
TRANSIENT_SUFFIXES = ("-wal", "-shm", "-journal", ".runtime-write.lock")
Emit = Callable[[str], None]


class AlphaSnapshotError(RuntimeError):
    """A preflight or integrity gate failed; no snapshot was promoted."""


def _safe_item(path: Path) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400):
        raise AlphaSnapshotError(f"symlink/reparse point refused: {path}")
    return info


def _safe_ancestors(path: Path) -> None:
    for candidate in (path, *path.parents):
        if candidate.exists() or candidate.is_symlink():
            _safe_item(candidate)


def _sha(path: Path, *, announce: Emit | None = None) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    processed = 0
    last = time.monotonic()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
            processed += len(block)
            now = time.monotonic()
            if announce is not None and now - last >= 2:
                announce(f"  [HASH] {processed}/{total} bytes")
                last = now
    return digest.hexdigest()


def _inventory(source: Path) -> tuple[list[tuple[Path, int, int]], list[str], list[str]]:
    files: list[tuple[Path, int, int]] = []
    directories: list[str] = []
    excluded: list[str] = []
    for base, dirnames, filenames in os.walk(source, followlinks=False):
        folder = Path(base)
        for dirname in sorted(dirnames):
            directory = folder / dirname
            _safe_item(directory)
            directories.append(directory.relative_to(source).as_posix())
        for filename in sorted(filenames):
            path = folder / filename
            info = _safe_item(path)
            if not stat.S_ISREG(info.st_mode):
                raise AlphaSnapshotError(f"non-regular file refused: {path}")
            relative = path.relative_to(source).as_posix()
            if relative == EVIDENCE:
                raise AlphaSnapshotError("source already contains alpha snapshot evidence")
            if filename.lower().endswith(TRANSIENT_SUFFIXES):
                if filename.lower().endswith("-journal") and info.st_size:
                    raise AlphaSnapshotError(f"nonempty rollback journal; writer state unknown: {relative}")
                excluded.append(relative)
                continue
            files.append((path.relative_to(source), info.st_size, info.st_mtime_ns))
    if not files:
        raise AlphaSnapshotError("empty MEMORY source")
    return sorted(files, key=lambda item: item[0].as_posix()), sorted(directories), sorted(excluded)


def _copy_file(source: Path, destination: Path, *, emit: Emit) -> str:
    digest = hashlib.sha256()
    total = source.stat().st_size
    processed = 0
    last = time.monotonic()
    with source.open("rb") as inp, destination.open("xb") as out:
        while block := inp.read(4 * 1024 * 1024):
            out.write(block)
            digest.update(block)
            processed += len(block)
            now = time.monotonic()
            if now - last >= 2:
                emit(f"  [COPY] {processed}/{total} bytes")
                last = now
        out.flush()
        os.fsync(out.fileno())
    expected = digest.hexdigest()
    if _sha(source) != expected or _sha(destination) != expected:
        raise AlphaSnapshotError(f"file changed or copy mismatch: {source.name}")
    return expected


def _read_evidence(snapshot: Path) -> dict[str, object]:
    evidence = snapshot / EVIDENCE
    _safe_item(evidence)
    try:
        value = json.loads(evidence.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise AlphaSnapshotError("invalid snapshot evidence") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
        raise AlphaSnapshotError("unsupported snapshot evidence")
    return value


def verify_snapshot(snapshot_root: str | Path, *, emit: Emit = print) -> dict[str, object]:
    """Verify evidence and all databases without modifying or activating the snapshot."""
    given = Path(snapshot_root).expanduser()
    _safe_ancestors(given)
    snapshot = given.resolve(strict=True)
    if not snapshot.is_dir():
        raise AlphaSnapshotError("snapshot root is not a directory")
    evidence = _read_evidence(snapshot)
    records = evidence.get("files")
    if not isinstance(records, list) or not records:
        raise AlphaSnapshotError("missing file inventory")
    expected: set[str] = {EVIDENCE}
    db_count = 0
    for index, entry in enumerate(records, 1):
        if not isinstance(entry, dict):
            raise AlphaSnapshotError("invalid inventory entry")
        relative = entry.get("path")
        if not isinstance(relative, str):
            raise AlphaSnapshotError("invalid file path")
        spec = PurePosixPath(relative)
        if (not relative or spec.is_absolute() or ".." in spec.parts
                or "\\" in relative or ":" in relative or relative in expected):
            raise AlphaSnapshotError(f"duplicate/unsafe snapshot path: {relative}")
        expected.add(relative)
        path = snapshot.joinpath(*spec.parts)
        _safe_ancestors(path)
        if not path.is_file() or not path.resolve().is_relative_to(snapshot):
            raise AlphaSnapshotError(f"missing or external file: {relative}")
        if path.stat().st_size != entry.get("size_bytes"):
            raise AlphaSnapshotError(f"size mismatch: {relative}")
        emit(f"[VERIFY {index}/{len(records)}] {relative}")
        if _sha(path, announce=emit) != entry.get("sha256"):
            raise AlphaSnapshotError(f"SHA256 mismatch: {relative}")
        if path.suffix.lower() in SQLITE_EXTENSIONS:
            db_count += 1
            if entry.get("method") != "sqlite_online_backup_api":
                raise AlphaSnapshotError(f"untrusted SQLite snapshot method: {relative}")
            uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
            with sqlite3.connect(uri, uri=True, timeout=10) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise AlphaSnapshotError(f"SQLite integrity failed: {relative}")
                if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise AlphaSnapshotError(f"SQLite foreign keys failed: {relative}")
    actual: set[str] = set()
    for base, dirs, files in os.walk(snapshot, followlinks=False):
        for name in dirs:
            _safe_item(Path(base) / name)
        for name in files:
            path = Path(base) / name
            _safe_item(path)
            actual.add(path.relative_to(snapshot).as_posix())
    if actual != expected:
        raise AlphaSnapshotError("snapshot contains missing or unlisted files")
    return {
        "ok": True, "schema_version": SCHEMA,
        "file_count": len(records), "sqlite_passed": db_count,
        "writer_quiescence_proven": False,
        "cross_database_atomicity_proven": False,
        "application_restore_tested": False,
        "autobiographical_recall_tested": False,
    }


def create_snapshot(
    source_root: str | Path,
    destination_root: str | Path,
    *,
    writer_confirmation: str,
    emit: Emit = print,
) -> dict[str, object]:
    """Capture an alpha snapshot with explicit operator quiescence attestation.

    The confirmation is not a lock. A separate application/OS protocol must
    actually prevent all writers throughout inventory, capture, and validation.
    """
    if writer_confirmation != "WRITERS_PAUSED":
        raise AlphaSnapshotError("explicit WRITERS_PAUSED confirmation required")
    given_source = Path(source_root).expanduser()
    _safe_ancestors(given_source)
    source = given_source.resolve(strict=True)
    if not source.is_dir():
        raise AlphaSnapshotError("source is not a directory")
    given_dest = Path(destination_root).expanduser().absolute()
    _safe_ancestors(given_dest.parent)
    dest = given_dest.resolve(strict=False)
    if (dest == source or dest.is_relative_to(source) or source.is_relative_to(dest)):
        raise AlphaSnapshotError("source/destination overlap")
    if dest.exists():
        raise AlphaSnapshotError("destination already exists; never overwrite")
    if not dest.parent.is_dir():
        raise AlphaSnapshotError("destination parent must exist")
    files, dirs, excluded = _inventory(source)
    stamp = [(source / rel, size, mtime) for rel, size, mtime in files]
    started = time.monotonic()
    stage = dest.with_name(dest.name + ".incomplete-" + uuid.uuid4().hex)
    stage.mkdir(mode=0o700)
    emit(f"[STAGING] {stage}")
    try:
        for relative in dirs:
            (stage / Path(*PurePosixPath(relative).parts)).mkdir(parents=True, exist_ok=True)
        records: list[dict[str, object]] = []
        for index, (rel, size, mtime) in enumerate(files, 1):
            path = source / rel
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            label = rel.as_posix()
            emit(f"[{index}/{len(files)}] {label}")
            if path.suffix.lower() in SQLITE_EXTENSIONS:
                def progress(done: int, total: int) -> None:
                    emit(f"  [SQLITE] {done}/{total} pages") if done == total else None
                snapshot = create_sqlite_snapshot(
                    path, target, progress=progress, full_integrity_check=True
                )
                digest = snapshot.snapshot_sha256
                method = "sqlite_online_backup_api"
            else:
                digest = _copy_file(path, target, emit=emit)
                method = "verified_copy"
            current = path.stat()
            if current.st_size != size or current.st_mtime_ns != mtime:
                raise AlphaSnapshotError(f"source changed during capture: {label}")
            records.append({
                "path": label, "size_bytes": target.stat().st_size,
                "sha256": digest, "method": method,
            })
            emit(f"  [PASS] {index}/{len(files)}")
        for path, size, mtime in stamp:
            current = path.stat()
            if current.st_size != size or current.st_mtime_ns != mtime:
                raise AlphaSnapshotError(f"source changed during snapshot: {path.name}")
        evidence = {
            "schema_version": SCHEMA,
            "snapshot_id": str(uuid.uuid4()),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "created_with_runtime": PACKAGE_VERSION,
            "writer_quiescence_evidence": "operator_attested_only",
            "cross_database_atomicity_proven": False,
            "excluded_transient_paths": excluded,
            "files": records,
        }
        (stage / EVIDENCE).write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        emit("[VERIFY] Checking complete staging...")
        result = verify_snapshot(stage, emit=emit)
        if dest.exists():
            raise AlphaSnapshotError("destination appeared during capture")
        stage.rename(dest)
        emit(f"[DONE] {dest} | {time.monotonic() - started:.1f}s")
        return {**result, "destination": str(dest), "elapsed_seconds": round(time.monotonic()-started, 3)}
    except Exception:
        emit(f"[INCOMPLETE] Preserved for diagnosis: {stage}")
        raise
