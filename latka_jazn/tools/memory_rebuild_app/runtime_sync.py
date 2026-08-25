from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid

from .read_only_validation import sha256_file, validate_existing_database
from .source_detection import probe_source, iter_jsonl_objects
from .unified_memory import UnifiedMemoryDatabase

RUNTIME_L0_SCHEMA_VERSION = "memory_rebuild_runtime_l0/v16.0"
GENERIC_RUNTIME_KINDS = {
    "episodic", "semantic", "affective", "procedural",
    "provenance_ledger", "runtime_events",
}

RUNTIME_L0_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS runtime_memory_sources(
  source_id TEXT PRIMARY KEY,
  source_kind TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  source_locator TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  imported_at_utc TEXT NOT NULL,
  records_seen INTEGER NOT NULL DEFAULT 0,
  inserted INTEGER NOT NULL DEFAULT 0,
  revised INTEGER NOT NULL DEFAULT 0,
  duplicates INTEGER NOT NULL DEFAULT 0,
  conflicts INTEGER NOT NULL DEFAULT 0,
  UNIQUE(source_kind,source_sha256)
);
CREATE TABLE IF NOT EXISTS runtime_memory_records_l0(
  record_id TEXT PRIMARY KEY,
  source_kind TEXT NOT NULL,
  source_record_key TEXT NOT NULL,
  revision INTEGER NOT NULL,
  source_id TEXT NOT NULL,
  event_time TEXT,
  content TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  imported_at_utc TEXT NOT NULL,
  active INTEGER NOT NULL CHECK(active IN (0,1)),
  UNIQUE(source_kind,source_record_key,revision),
  FOREIGN KEY(source_id) REFERENCES runtime_memory_sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_runtime_memory_l0_kind_active
  ON runtime_memory_records_l0(source_kind,active,event_time);
CREATE TABLE IF NOT EXISTS runtime_memory_import_conflicts(
  conflict_id TEXT PRIMARY KEY,
  source_kind TEXT NOT NULL,
  source_record_key TEXT NOT NULL,
  source_id TEXT NOT NULL,
  existing_record_id TEXT,
  incoming_sha256 TEXT NOT NULL,
  existing_sha256 TEXT,
  reason TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('unresolved','resolved_revision','resolved_duplicate')),
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at_utc TEXT NOT NULL,
  FOREIGN KEY(source_id) REFERENCES runtime_memory_sources(source_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS runtime_memory_records_l0_fts USING fts5(
  content,
  source_kind UNINDEXED,
  source_record_key UNINDEXED,
  content='runtime_memory_records_l0',
  content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS runtime_memory_l0_fts_insert AFTER INSERT ON runtime_memory_records_l0 BEGIN
  INSERT INTO runtime_memory_records_l0_fts(rowid,content,source_kind,source_record_key)
  VALUES(new.rowid,new.content,new.source_kind,new.source_record_key);
END;
CREATE TRIGGER IF NOT EXISTS runtime_memory_l0_fts_delete AFTER DELETE ON runtime_memory_records_l0 BEGIN
  INSERT INTO runtime_memory_records_l0_fts(runtime_memory_records_l0_fts,rowid,content,source_kind,source_record_key)
  VALUES('delete',old.rowid,old.content,old.source_kind,old.source_record_key);
END;
CREATE TRIGGER IF NOT EXISTS runtime_memory_l0_fts_update AFTER UPDATE OF content,source_kind,source_record_key ON runtime_memory_records_l0 BEGIN
  INSERT INTO runtime_memory_records_l0_fts(runtime_memory_records_l0_fts,rowid,content,source_kind,source_record_key)
  VALUES('delete',old.rowid,old.content,old.source_kind,old.source_record_key);
  INSERT INTO runtime_memory_records_l0_fts(rowid,content,source_kind,source_record_key)
  VALUES(new.rowid,new.content,new.source_kind,new.source_record_key);
END;
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iter_json_records(path: Path) -> Iterator[dict[str, Any]]:
    suffix = path.suffix.casefold()
    if suffix in {".jsonl", ".ndjson"}:
        yield from iter_jsonl_objects(path)
        return
    if suffix != ".json":
        raise ValueError(f"runtime layered source must be JSON/JSONL: {path}")
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError(
            f"large JSON is not stream-safe ({path.stat().st_size} bytes); use JSONL/NDJSON or an explicit importer"
        )
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("records") or payload.get("entries") or payload.get("events") or []
        if not isinstance(rows, list):
            rows = [payload]
    else:
        raise ValueError("JSON runtime source must be an object or list")
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"runtime JSON record #{index} is not an object")
        yield row


def _record_key(raw: dict[str, Any], content_sha: str) -> str:
    for key in (
        "id", "record_id", "memory_id", "event_id", "episode_id", "fact_id",
        "entry_id", "ledger_id", "operation_id", "turn_id", "trace_id",
    ):
        value = str(raw.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    return f"content:{content_sha}"


def _event_time(raw: dict[str, Any]) -> str | None:
    for key in ("event_time", "timestamp", "created_at_utc", "updated_at_utc", "time", "datetime"):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return None


def _content(raw: dict[str, Any], kind: str) -> str:
    preferred = {
        "episodic": ("content", "summary", "event", "description", "text"),
        "semantic": ("statement", "fact", "content", "summary", "text"),
        "affective": ("reflection", "content", "summary", "text"),
        "procedural": ("procedure", "instruction", "content", "summary", "text"),
        "provenance_ledger": ("description", "details", "content", "summary"),
        "runtime_events": ("message", "event", "details", "content", "summary"),
    }.get(kind, ("content", "summary", "text"))
    pieces: list[str] = []
    for key in preferred:
        value = raw.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, str):
            pieces.append(value.strip())
        else:
            pieces.append(_canonical(value))
    if pieces:
        return "\n".join(item for item in pieces if item)
    return _canonical(raw)


def ensure_runtime_l0_schema(con: sqlite3.Connection) -> None:
    con.executescript(RUNTIME_L0_SQL)
    con.execute(
        "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('runtime_l0_schema_version',?)",
        (RUNTIME_L0_SCHEMA_VERSION,),
    )


def _source_locator(path: Path, runtime_root: Path) -> str:
    try:
        return path.resolve().relative_to(runtime_root.resolve()).as_posix()
    except ValueError:
        return path.name


def import_runtime_l0_source(database: Path, path: Path, kind: str, *, runtime_root: Path) -> dict[str, Any]:
    if kind not in GENERIC_RUNTIME_KINDS:
        raise ValueError(f"unsupported generic runtime kind: {kind}")
    source_sha = sha256_file(path)
    source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"runtime-source:{kind}:{source_sha}"))
    now = _utc_now()
    inserted = revised = duplicates = conflicts = seen = 0
    con = sqlite3.connect(database, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        ensure_runtime_l0_schema(con)
        existing_source = con.execute(
            "SELECT source_id,records_seen,inserted,revised,duplicates,conflicts FROM runtime_memory_sources WHERE source_kind=? AND source_sha256=?",
            (kind, source_sha),
        ).fetchone()
        if existing_source is not None:
            return {
                "ok": True, "status": "identical_source_duplicate", "kind": kind,
                "source_id": str(existing_source[0]), "source_sha256": source_sha,
                "records_seen": int(existing_source[1]), "inserted": 0, "revised": 0,
                "duplicates": int(existing_source[4]), "conflicts": int(existing_source[5]),
            }
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            """INSERT INTO runtime_memory_sources(
               source_id,source_kind,source_sha256,source_locator,size_bytes,imported_at_utc,
               records_seen,inserted,revised,duplicates,conflicts) VALUES(?,?,?,?,?,?,0,0,0,0,0)""",
            (source_id, kind, source_sha, _source_locator(path, runtime_root), path.stat().st_size, now),
        )
        for raw in _iter_json_records(path):
            seen += 1
            raw_json = _canonical(raw)
            content = _content(raw, kind)
            content_sha = _sha_text(raw_json)
            key = _record_key(raw, content_sha)
            active = con.execute(
                """SELECT record_id,revision,content_sha256 FROM runtime_memory_records_l0
                   WHERE source_kind=? AND source_record_key=? AND active=1 ORDER BY revision DESC LIMIT 1""",
                (kind, key),
            ).fetchone()
            if active is not None and str(active["content_sha256"]) == content_sha:
                duplicates += 1
                con.execute(
                    """INSERT INTO runtime_memory_import_conflicts(
                       conflict_id,source_kind,source_record_key,source_id,existing_record_id,incoming_sha256,
                       existing_sha256,reason,status,details_json,created_at_utc)
                       VALUES(?,?,?,?,?,?,?,?,?,'{}',?)""",
                    (str(uuid.uuid4()), kind, key, source_id, str(active["record_id"]), content_sha,
                     content_sha, "identical_duplicate", "resolved_duplicate", now),
                )
                continue
            revision = int(active["revision"]) + 1 if active is not None else 1
            if active is not None:
                con.execute("UPDATE runtime_memory_records_l0 SET active=0 WHERE record_id=?", (active["record_id"],))
                revised += 1
            record_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"runtime-l0:{kind}:{key}:{revision}:{content_sha}"))
            try:
                con.execute(
                    """INSERT INTO runtime_memory_records_l0(
                       record_id,source_kind,source_record_key,revision,source_id,event_time,content,
                       content_sha256,raw_json,imported_at_utc,active) VALUES(?,?,?,?,?,?,?,?,?,?,1)""",
                    (record_id, kind, key, revision, source_id, _event_time(raw), content,
                     content_sha, raw_json, now),
                )
                inserted += 1
                if active is not None:
                    con.execute(
                        """INSERT INTO runtime_memory_import_conflicts(
                           conflict_id,source_kind,source_record_key,source_id,existing_record_id,incoming_sha256,
                           existing_sha256,reason,status,details_json,created_at_utc)
                           VALUES(?,?,?,?,?,?,?,?,?,'{}',?)""",
                        (str(uuid.uuid4()), kind, key, source_id, str(active["record_id"]), content_sha,
                         str(active["content_sha256"]), "explicit_new_revision", "resolved_revision", now),
                    )
            except sqlite3.IntegrityError as exc:
                conflicts += 1
                con.execute(
                    """INSERT INTO runtime_memory_import_conflicts(
                       conflict_id,source_kind,source_record_key,source_id,existing_record_id,incoming_sha256,
                       existing_sha256,reason,status,details_json,created_at_utc)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), kind, key, source_id, str(active["record_id"]) if active else None,
                     content_sha, str(active["content_sha256"]) if active else None,
                     "constraint_conflict", "unresolved", _canonical({"sqlite_error": str(exc)}), now),
                )
        con.execute(
            """UPDATE runtime_memory_sources SET records_seen=?,inserted=?,revised=?,duplicates=?,conflicts=?
               WHERE source_id=?""",
            (seen, inserted, revised, duplicates, conflicts, source_id),
        )
        if conflicts:
            con.rollback()
            return {
                "ok": False, "status": "unresolved_conflicts", "kind": kind,
                "source_id": source_id, "source_sha256": source_sha, "records_seen": seen,
                "inserted": inserted, "revised": revised, "duplicates": duplicates, "conflicts": conflicts,
            }
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "ok": True, "status": "imported", "kind": kind, "source_id": source_id,
        "source_sha256": source_sha, "records_seen": seen, "inserted": inserted,
        "revised": revised, "duplicates": duplicates, "conflicts": conflicts,
        "automatic_l2": False, "automatic_l3": False,
    }


def discover_runtime_sources(runtime_root: Path) -> list[tuple[Path, str]]:
    root = runtime_root.expanduser().resolve()
    result: list[tuple[Path, str]] = []
    raw_journal = root / "memory" / "raw" / "dziennik.json"
    if raw_journal.is_file():
        result.append((raw_journal, "journal"))
    layered = root / "memory" / "layered"
    if layered.is_dir():
        for path in sorted(
            (item for item in layered.rglob("*") if item.is_file() and item.suffix.casefold() in {".json", ".jsonl", ".ndjson"}),
            key=lambda item: item.as_posix().casefold(),
        ):
            result.append((path, probe_source(path).kind))
    return result


def _copy_sqlite_snapshot(source: Path, target: Path) -> None:
    """Create a transactionally consistent staging copy from a read-only source."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    uri = f"file:{source.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as src, sqlite3.connect(target, timeout=30) as dst:
        src.backup(dst, pages=256, sleep=0.02)


def _sync_runtime_in_place(db: Path, root: Path, sources: list[tuple[Path, str]], *, full_validation: bool) -> dict[str, Any]:
    store = UnifiedMemoryDatabase(db)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    by_kind: dict[str, int] = {}
    for path, kind in sources:
        by_kind[kind] = by_kind.get(kind, 0) + 1
        try:
            if kind == "journal":
                result = store.import_source(path, dry_run=False, full_validation=False).to_dict()
            elif kind in GENERIC_RUNTIME_KINDS:
                result = import_runtime_l0_source(db, path, kind, runtime_root=root)
            else:
                result = {
                    "ok": True, "status": "skipped_reference", "kind": kind,
                    "source": _source_locator(path, root),
                    "reason": "schema-aware detector did not select a safe runtime importer",
                }
            results.append({"source": _source_locator(path, root), "kind": kind, "result": result})
            if result.get("ok") is False:
                errors.append({"source": _source_locator(path, root), "kind": kind, "error": result})
                break
        except Exception as exc:
            errors.append({
                "source": _source_locator(path, root), "kind": kind,
                "error_type": type(exc).__name__, "error": str(exc),
            })
            break
    validation = validate_existing_database(db, full=full_validation, include_fts=True)
    return {
        "ok": not errors and bool(validation.get("ok")),
        "source_count": len(sources),
        "source_kind_counts": dict(sorted(by_kind.items())),
        "results": results,
        "errors": errors,
        "validation": validation,
    }


def sync_runtime(database: str | Path, runtime_root: str | Path, *, full_validation: bool = True) -> dict[str, Any]:
    """Atomically sync runtime L0 sources into an existing unified database.

    All mutating work happens on a SQLite backup snapshot in the same directory as
    the target.  The canonical database is replaced with ``os.replace`` only after
    every source import and read-only validation succeeds.  Any failure discards
    staging and leaves the original database byte-for-byte untouched.
    """
    db = Path(database).expanduser().resolve()
    root = Path(runtime_root).expanduser().resolve()
    if not db.is_file():
        raise FileNotFoundError(f"sync-runtime requires existing unified DB: {db}")
    sources = discover_runtime_sources(root)
    if not sources:
        raise FileNotFoundError(f"no runtime memory sources found under {root}")
    before_sha = sha256_file(db)
    staging = db.with_name(f".{db.name}.sync-runtime-{uuid.uuid4().hex}.staging.sqlite3")
    try:
        _copy_sqlite_snapshot(db, staging)
        result = _sync_runtime_in_place(staging, root, sources, full_validation=full_validation)
        if not result.get("ok"):
            return {
                **result,
                "ok": False,
                "status": "staging_rejected",
                "database": str(db),
                "runtime_root_private": str(root),
                "target_modified": False,
                "target_sha256_before": before_sha,
                "target_sha256_after": sha256_file(db),
                "automatic_l2": False,
                "automatic_l3": False,
            }
        os.replace(staging, db)
        return {
            **result,
            "ok": True,
            "status": "published",
            "database": str(db),
            "runtime_root_private": str(root),
            "target_modified": True,
            "target_sha256_before": before_sha,
            "target_sha256_after": sha256_file(db),
            "automatic_l2": False,
            "automatic_l3": False,
        }
    finally:
        if staging.exists():
            staging.unlink()


__all__ = [
    "GENERIC_RUNTIME_KINDS", "RUNTIME_L0_SCHEMA_VERSION", "RUNTIME_L0_SQL",
    "discover_runtime_sources", "ensure_runtime_l0_schema", "import_runtime_l0_source", "sync_runtime",
]
