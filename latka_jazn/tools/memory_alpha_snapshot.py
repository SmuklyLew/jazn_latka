"""Fail-closed operator snapshot for alpha MEMORY; no activation or restore.

Every SQLite file is backed up through the existing SQLite Backup API.  This
does not prove global atomicity across separate databases and JSON/JSONL files:
the caller must independently quiesce all writers before invoking create.
"""
from __future__ import annotations

from contextlib import closing
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
    started = last = time.monotonic()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
            processed += len(block)
            now = time.monotonic()
            if announce is not None and now - last >= 2:
                rate = processed / max(0.001, now-started)
                eta = (total-processed) / max(1.0, rate)
                announce(f"  [HASH] {processed}/{total} bytes | {rate/1048576:.1f} MiB/s | ETA {eta:.0f}s")
                last = now
    return digest.hexdigest()


def _inventory(source: Path) -> tuple[list[tuple[Path, int, int]], list[str], list[str]]:
    files: list[tuple[Path, int, int]] = []
    seen_casefold: set[str] = set()
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
            folded = relative.casefold()
            if folded in seen_casefold:
                raise AlphaSnapshotError(f"casefold-colliding MEMORY path: {relative}")
            seen_casefold.add(folded)
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
    started = last = time.monotonic()
    with source.open("rb") as inp, destination.open("xb") as out:
        while block := inp.read(4 * 1024 * 1024):
            out.write(block)
            digest.update(block)
            processed += len(block)
            now = time.monotonic()
            if now - last >= 2:
                rate = processed / max(0.001, now-started)
                eta = (total-processed) / max(1.0, rate)
                emit(f"  [COPY] {processed}/{total} bytes | {rate/1048576:.1f} MiB/s | ETA {eta:.0f}s")
                last = now
        out.flush()
        os.fsync(out.fileno())
    expected = digest.hexdigest()
    if _sha(source) != expected or _sha(destination) != expected:
        raise AlphaSnapshotError(f"file changed or copy mismatch: {source.name}")
    return expected


def _check_shard_manifests(
    snapshot: Path, *, normalize_active: bool = False, source_preflight: bool = False
) -> list[dict[str, object]]:
    """Check shard references against actual backed-up database files.

    Source preflight validates the declared physical main-file size BEFORE
    staging exists. The active shard SHA is advisory (writers may update it
    independently from the manifest); sealed shard SHA is authoritative.
    An SQLite backup can produce a different file size/hash by applying WAL.
    Rebase only active metadata in the isolated staging tree, with evidence.
    """
    normalized: list[dict[str, object]] = []
    base = snapshot / "sqlite" / "runtime_write_v1"
    for name in ("runtime_audit_shards.json", "runtime_memory_shards.json"):
        manifest = base / name
        if not manifest.exists():
            continue
        _safe_item(manifest)
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            shards = data["shards"]
            active_id = data["active_write_shard"]
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            raise AlphaSnapshotError(f"invalid shard manifest: {name}") from exc
        if not isinstance(shards, list) or not shards:
            raise AlphaSnapshotError(f"invalid shard list: {name}")
        ids: set[str] = set()
        active_count = 0
        changed = False
        for shard in shards:
            if not isinstance(shard, dict):
                raise AlphaSnapshotError(f"invalid shard entry: {name}")
            ident = shard.get("shard_id")
            role = shard.get("role")
            relative = shard.get("path")
            if not isinstance(ident, str) or not ident or ident in ids:
                raise AlphaSnapshotError(f"duplicate/invalid shard id: {name}")
            ids.add(ident)
            if role not in ("sealed", "active_write"):
                raise AlphaSnapshotError(f"invalid shard role: {name}")
            if role == "active_write":
                active_count += 1
                if ident != active_id:
                    raise AlphaSnapshotError(f"active shard identity mismatch: {name}")
            if not isinstance(relative, str):
                raise AlphaSnapshotError(f"invalid shard path: {name}")
            spec = PurePosixPath(relative.replace("\\", "/"))
            if (spec.is_absolute() or ".." in spec.parts or
                    ":" in relative or spec.suffix.lower() not in SQLITE_EXTENSIONS or
                    not relative.startswith(("sqlite/", "sqlite\\"))):
                raise AlphaSnapshotError(f"unsafe shard reference: {relative}")
            path = snapshot.joinpath(*spec.parts)
            _safe_ancestors(path)
            if not path.is_file() or not path.resolve().is_relative_to(snapshot):
                raise AlphaSnapshotError(f"missing shard reference: {relative}")
            size = path.stat().st_size
            expected_hash = shard.get("sha256")
            if role == "sealed" and not expected_hash:
                raise AlphaSnapshotError(f"sealed shard missing SHA256: {relative}")
            if expected_hash is not None and (
                not isinstance(expected_hash, str) or
                len(expected_hash) != 64 or
                any(ch not in "0123456789abcdefABCDEF" for ch in expected_hash)
            ):
                raise AlphaSnapshotError(f"invalid shard SHA256: {relative}")
            if role == "sealed" and _sha(path).lower() != expected_hash.lower():
                raise AlphaSnapshotError(f"shard SHA256 mismatch: {relative}")
            if role == "active_write" and normalize_active and expected_hash:
                cloned_hash = _sha(path)
                if cloned_hash.lower() != expected_hash.lower():
                    normalized.append({
                        "manifest": name, "shard_id": ident,
                        "field": "sha256", "source_value": expected_hash,
                        "snapshot_value": cloned_hash,
                    })
                    shard["sha256"] = cloned_hash
                    changed = True
            elif role == "active_write" and not source_preflight and expected_hash:
                if _sha(path).lower() != expected_hash.lower():
                    raise AlphaSnapshotError(f"shard SHA256 mismatch: {relative}")
            if shard.get("size_bytes") != size:
                if role != "active_write" or not normalize_active:
                    raise AlphaSnapshotError(f"shard size mismatch: {relative}")
                normalized.append({
                    "manifest": name, "shard_id": ident,
                    "field": "size_bytes", "source_value": shard.get("size_bytes"),
                    "snapshot_value": size,
                })
                shard["size_bytes"] = size
                changed = True
        if active_count != 1 or active_id not in ids:
            raise AlphaSnapshotError(f"missing/duplicate active shard: {name}")
        if changed:
            with manifest.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
    return normalized


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
            with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
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
    _check_shard_manifests(snapshot)
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
    # Mandatory before any staging directory is created: an inconsistent
    # source manifest is never silently "repaired" by the SQLite backup.
    _check_shard_manifests(source, source_preflight=True)
    stamp = [(source / rel, size, mtime) for rel, size, mtime in files]
    # WAL and SHM are transient, but changes to them during the capture are a
    # strong signal that the operator did not actually quiesce every writer.
    for relative in excluded:
        path = source.joinpath(*PurePosixPath(relative).parts)
        info = _safe_item(path)
        stamp.append((path, info.st_size, info.st_mtime_ns))
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
            _safe_item(path)
            if not path.resolve().is_relative_to(source):
                raise AlphaSnapshotError(f"source path escaped MEMORY: {label}")
            emit(f"[{index}/{len(files)}] {label}")
            if path.suffix.lower() in SQLITE_EXTENSIONS:
                last_sqlite_progress = [0.0]

                def progress(done: int, total: int) -> None:
                    now = time.monotonic()
                    if done == total or now - last_sqlite_progress[0] >= 1:
                        emit(f"  [SQLITE] {done}/{total} pages | elapsed {now-started:.1f}s")
                        last_sqlite_progress[0] = now
                snapshot = create_sqlite_snapshot(
                    path, target, progress=progress, full_integrity_check=True
                )
                digest = snapshot.snapshot_sha256
                method = "sqlite_online_backup_api"
            else:
                digest = _copy_file(path, target, emit=emit)
                method = "verified_copy"
            _safe_item(path)
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
        # Online SQLite backup may checkpoint WAL into the cloned main file.
        # Rebase only ACTIVE shard sizes in staging; sealed SHA stays immutable.
        normalized = _check_shard_manifests(stage, normalize_active=True)
        by_path = {entry["path"]: entry for entry in records}
        for name in ("runtime_audit_shards.json", "runtime_memory_shards.json"):
            rel = "sqlite/runtime_write_v1/" + name
            if rel in by_path:
                item = by_path[rel]
                updated_path = stage / rel
                updated_sha = _sha(updated_path)
                if updated_sha != item["sha256"]:
                    item["source_sha256"] = item["sha256"]
                    item["sha256"] = updated_sha
                    item["size_bytes"] = updated_path.stat().st_size
        evidence = {
            "schema_version": SCHEMA,
            "normalized_active_shards": normalized,
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
