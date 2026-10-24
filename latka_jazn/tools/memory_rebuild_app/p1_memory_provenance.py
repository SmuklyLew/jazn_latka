"""P1: coherent SQLite snapshots, stable logical diffs and source provenance.

Writes only bounded temporary snapshots/indexes OUTSIDE SYSTEM and MEMORY.
No source SQLite mutations, raw content in reports, or activation claims.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from typing import Any, Iterator

from latka_jazn.db.runtime_sqlite import connect_runtime_readonly
from latka_jazn.memory.database_identity import inspect_memory_database
from .canonical_rebuild import CanonicalMemoryRebuildPipeline, _source_disposition, canonical_database_path
from .models import RebuildProject
from .p1_memory_inspection import (
    _has_symlink, _inspect_db, _inspect_host_selection,
    _inspect_staging, inspect_memory_layout,
)
from .test_profiles import (
    _SEMANTIC_FINGERPRINT_TABLES, _VOLATILE_RECONCILIATION_COLUMNS,
)
from .unified_schema import CANONICAL_DATABASE_NAME, quote

SCHEMA = "jazn_memory_provenance_comparison/v1"
MAX_DATABASE_BYTES = 8 * 1024**3
MAX_SOURCE_BYTES = 8 * 1024**3
MAX_ROWS = 1_000_000
MAX_INDEX_BYTES = 512 * 1024**2
MAX_ROW_BYTES = 16 * 1024**2
OPERATION_SECONDS = 90


def _unsafe_path(path: Path) -> bool:
    return _has_symlink(path) or any(p.is_junction() for p in (path, *path.parents))


def _file_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino


class ComparisonBlocked(ValueError):
    """Expected fail-closed condition carrying only a stable issue code."""


def _within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _staged(target: Path) -> Path | None:
    if _inspect_staging(target)["status"] != "candidate_inspected":
        return None
    root = target.parent.parent / ".rebuild_staging"
    matches = [run / "sqlite" / CANONICAL_DATABASE_NAME for run in root.iterdir()
               if (run / "sqlite" / CANONICAL_DATABASE_NAME).is_file()]
    return matches[0] if len(matches) == 1 and not _has_symlink(matches[0]) else None


def _eligible(path: Path | None, byte_limit: int) -> tuple[bool, str, int]:
    if path is None:
        return False, "role_not_selected", 0
    if _unsafe_path(path):
        return False, "symlink_rejected", 0
    inspected = _inspect_db(path)
    if (inspected["status"] != "compatible"
            or inspected["schema_kind"] != "native_unified"):
        return False, "native_schema_unverified", 0
    size = path.stat().st_size
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.is_file():
            size += sidecar.stat().st_size
    if size > byte_limit:
        return False, "database_size_limit", size
    return True, "native_probe_passed", size


def _backup(src_path: Path, dest: Path, *, byte_limit: int = MAX_DATABASE_BYTES) -> None:
    if _unsafe_path(src_path) or _unsafe_path(dest):
        raise ComparisonBlocked("snapshot_unsafe_path")
    identity = _file_identity(src_path)
    descriptor = os.open(str(dest), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    deadline = time.monotonic() + OPERATION_SECONDS

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise ComparisonBlocked("snapshot_timeout")
        if _total * page_size > byte_limit or dest.stat().st_size > byte_limit:
            raise ComparisonBlocked("snapshot_size_limit")
        if _unsafe_path(src_path) or _file_identity(src_path) != identity:
            raise ComparisonBlocked("source_replaced_during_snapshot")

    # Online backup captures committed WAL data consistently, unlike file copy.
    with closing(connect_runtime_readonly(src_path, timeout_ms=2000)) as source:
        page_size = int(source.execute("PRAGMA page_size").fetchone()[0])
        if int(source.execute("PRAGMA page_count").fetchone()[0]) * page_size > byte_limit:
            raise ComparisonBlocked("snapshot_size_limit")
        with closing(sqlite3.connect(dest, timeout=2.0)) as output:
            source.backup(output, pages=512, sleep=0.02, progress=progress)
            output.commit()
    if _unsafe_path(src_path) or _file_identity(src_path) != identity:
        raise ComparisonBlocked("source_replaced_during_snapshot")
    # Backup from WAL can leave a self-contained SQLite file with WAL header
    # bytes (2,2) but without live -wal/-shm sidecars. Normalize ONLY this
    # isolated temporary snapshot to a rollback journal before strict probing.
    with closing(sqlite3.connect(dest, timeout=2.0)) as normalized:
        row = normalized.execute("PRAGMA journal_mode=DELETE").fetchone()
        if row is None or str(row[0]).lower() != "delete":
            raise ComparisonBlocked("snapshot_journal_normalization_failed")
        normalized.commit()
    # The destination is a role-labelled, isolated snapshot, not a selected
    # canonical source database. Validate its *content* without conflating
    # the filename with native SQLite readiness.
    snapshot_info = inspect_memory_database(dest)
    if not (snapshot_info["kind"] == "native_unified"
            and snapshot_info["compatible"] is True):
        raise ComparisonBlocked("snapshot_validation_failed")


def _read_meta(path: Path) -> dict[str, Any]:
    wanted = ("memory_generation", "source_union_sha256", "restore_run_id",
              "parent_database_sha256", "source_restore_status_json")
    with closing(connect_runtime_readonly(path)) as con:
        tables = {str(row[0]) for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "unified_memory_meta" not in tables:
            raise ComparisonBlocked("unified_metadata_missing")
        fields = {str(row[0]): str(row[1]) for row in con.execute(
            "SELECT key,value FROM unified_memory_meta WHERE key IN ("
            + ",".join("?" for _ in wanted) + ")", wanted
        )}
        identity: dict[str, str] = {}
        if "jazn_database_identity" in tables:
            value = con.execute(
                "SELECT database_uuid,trust_state FROM jazn_database_identity "
                "WHERE singleton=1"
            ).fetchone()
            if value is not None:
                identity = {"uuid": str(value[0]), "trust": str(value[1])}
    manifest: list[dict[str, Any]] | None = None
    raw = fields.get("source_restore_status_json")
    if raw and len(raw) <= 4_000_000:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and all(isinstance(e, dict) for e in parsed):
                manifest = parsed
        except (ValueError, TypeError):
            pass
    return {"fields": fields, "identity": identity, "manifest": manifest}


def audit_claims(meta: dict[str, Any]) -> dict[str, Any]:
    """Validate producer syntax, not authorship; never return claim contents."""
    fields, identity = meta.get("fields", {}), meta.get("identity", {})
    checks: dict[str, bool | None] = {}
    raw_uuid = identity.get("uuid")
    try:
        checks["database_uuid"] = bool(uuid.UUID(raw_uuid)) if raw_uuid else None
    except (ValueError, TypeError, AttributeError):
        checks["database_uuid"] = False
    generation = fields.get("memory_generation")
    checks["memory_generation"] = generation in {"alpha", "beta"} if generation else None
    run = fields.get("restore_run_id")
    checks["restore_run_id"] = bool(re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{12}", run)) if run else None
    for key in ("source_union_sha256", "parent_database_sha256"):
        value = fields.get(key)
        checks[key] = bool(re.fullmatch(r"[0-9a-f]{64}", value)) if value else None
    manifest = meta.get("manifest")
    checks["source_restore_status_json"] = None if manifest is None else bool(
        isinstance(manifest, list) and manifest and all(
            isinstance(item, dict) and all(isinstance(item.get(k), str) for k in
                ("source_id", "sha256", "role", "pipeline", "disposition", "reason"))
            and re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            and (item["disposition"], item["reason"]) == _source_disposition(item["pipeline"])
            for item in manifest
        ) and len({item["source_id"] for item in manifest}) == len(manifest)
    )
    return {"state": "unverified", "syntax_checks": checks,
            "malformed_claims": sorted(key for key, value in checks.items() if value is False),
            "trusted_reference_available": False, "parent_chain_verified": False}


def _lineage(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    first, second = a["fields"], b["fields"]
    keys = ("memory_generation", "source_union_sha256", "restore_run_id")
    matching = {key: first[key] == second[key] for key in keys
                if first.get(key) and second.get(key)}
    x, y = a["identity"], b["identity"]
    uuid_equal = x["uuid"] == y["uuid"] if "uuid" in x and "uuid" in y else None
    if (matching.get("memory_generation") is True
            and matching.get("source_union_sha256") is False):
        state = "conflict"
    elif uuid_equal is True and any(not value for value in matching.values()):
        state = "conflict"
    elif not matching and uuid_equal is None:
        state = "unverified"
    elif any(not value for value in matching.values()) or uuid_equal is False:
        state = "different"
    else:
        state = "matching_claims"
    return {
        "state": state, "claim_matches": matching,
        "database_uuid_equal": uuid_equal,
        "both_trusted_identities": x.get("trust") == y.get("trust") == "trusted",
        "parent_chain_verified": False,
        "verification_state": "conflict" if state == "conflict" else "different" if state == "different" else "unverified",
        "trusted_reference_available": False,
        "matching_claims_are_not_identity_verification": True,
    }


def _attest_sources(project: RebuildProject, meta: dict[str, Any], *, byte_limit: int) -> dict[str, Any]:
    sources = list(project.enabled_sources())
    out: dict[str, Any] = {
        "state": "unverified", "configured": len(sources),
        "matching": 0, "changed": 0, "missing": 0, "unsafe": 0,
        "unattributed": 0, "bytes_hashed": 0,
    }
    manifest = meta["manifest"]
    if not sources or manifest is None:
        return out
    declared: dict[str, str] = {}
    for item in manifest:
        key, sha = item.get("source_id"), item.get("sha256")
        if not isinstance(key, str) or not isinstance(sha, str) or key in declared:
            return out
        declared[key] = sha
    out["unattributed"] = len(set(declared) - {spec.source_id for spec in sources})
    remaining = byte_limit
    deadline = time.monotonic() + OPERATION_SECONDS
    observed_inventory: list[dict[str, Any]] = []
    entries = {item["source_id"]: item for item in manifest}
    producer_contract = audit_claims(meta)["syntax_checks"]["source_restore_status_json"] is True
    for spec in sources:
        path = Path(spec.path).expanduser()
        if _unsafe_path(path):
            out["unsafe"] += 1
            continue
        if not path.is_file():
            out["missing"] += 1
            continue
        stat_before = path.stat()
        size = stat_before.st_size
        if size > remaining:
            return {**out, "state": "source_size_limit"}
        remaining -= size
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (stat_before.st_dev, stat_before.st_ino):
                return {**out, "state": "source_changed_during_hash", "verification_state": "blocked"}
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                if time.monotonic() > deadline or out["bytes_hashed"] + len(chunk) > byte_limit:
                    return {**out, "state": "source_resource_limit", "verification_state": "blocked"}
                digest.update(chunk)
                out["bytes_hashed"] += len(chunk)
        stat_after = path.stat()
        if (stat_before.st_size != stat_after.st_size
                or stat_before.st_mtime_ns != stat_after.st_mtime_ns
                or stat_before.st_ino != stat_after.st_ino or _unsafe_path(path)):
            return {**out, "state": "source_changed_during_hash"}
        observed = digest.hexdigest()
        disposition, reason = _source_disposition(spec.pipeline)
        entry = entries.get(spec.source_id, {})
        attributes_match = not producer_contract or all(entry.get(key) == value for key, value in {
            "role": spec.role, "pipeline": spec.pipeline, "disposition": disposition, "reason": reason,
        }.items())
        observed_inventory.append({"role": spec.role, "pipeline": spec.pipeline,
            "truth_domain": spec.truth_domain, "source_family": spec.source_family,
            "size_bytes": size, "sha256": observed, "disposition": disposition, "disposition_reason": reason})
        if declared.get(spec.source_id) == observed and (
            not spec.sha256 or spec.sha256 == observed
        ) and attributes_match:
            out["matching"] += 1
        else:
            out["changed"] += 1
    out["state"] = (
        "matching" if out["matching"] == len(sources) and out["unattributed"] == 0
        else "different"
    )
    out["verification_state"] = "unverified"
    out["source_bytes_match_claims"] = out["state"] == "matching"
    out["producer_contract_valid"] = producer_contract
    out["source_union_matches_observed"] = None
    if producer_contract and out["state"] == "matching" and meta["fields"].get("source_union_sha256"):
        union = CanonicalMemoryRebuildPipeline._source_union_sha256(observed_inventory)
        out["source_union_matches_observed"] = union == meta["fields"]["source_union_sha256"]
        if not out["source_union_matches_observed"]:
            out["state"] = "conflict"
            out["verification_state"] = "conflict"
    out["trusted_reference_available"] = False
    return out


def _canonical(value: object) -> bytes:
    def typed(item: object) -> object:
        if item is None:
            return ["null"]
        if isinstance(item, bytes):
            return ["blob", item.hex()]
        if isinstance(item, str):
            return ["text", item]
        if isinstance(item, int):
            return ["integer", str(item)]
        if isinstance(item, float):
            return ["real", item.hex()]
        if isinstance(item, list):
            return ["list", [typed(v) for v in item]]
        if isinstance(item, dict):
            return ["mapping", [[k, typed(v)] for k, v in sorted(item.items())]]
        raise ComparisonBlocked("unsupported_sqlite_value")
    return json.dumps(typed(value), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _index_snapshot(
    path: Path, index: sqlite3.Connection, role: str, *, max_rows: int,
    deadline: float,
) -> dict[str, tuple[tuple[str, str, int], ...]]:
    count = 0
    shapes: dict[str, tuple[tuple[str, str, int], ...]] = {}
    with closing(connect_runtime_readonly(path)) as source:
        # Bound native SQLite record decoding before a large BLOB reaches Python.
        source.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_ROW_BYTES)
        source.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        tables = {str(row[0]) for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for table in _SEMANTIC_FINGERPRINT_TABLES:
            if table not in tables:
                continue
            info = list(source.execute(f"PRAGMA table_info({quote(table)})"))
            columns = [str(row[1]) for row in info]
            shapes[table] = tuple((str(row[1]), str(row[2]), int(row[5])) for row in info)
            pk = [str(row[1]) for row in sorted(
                (row for row in info if int(row[5]) > 0), key=lambda row: int(row[5])
            )]
            keys = pk or columns
            contents = [c for c in columns if c not in _VOLATILE_RECONCILIATION_COLUMNS or c in keys]
            positions = [columns.index(c) for c in keys]
            content_pos = [columns.index(c) for c in contents]
            query = f"SELECT {','.join(quote(c) for c in columns)} FROM {quote(table)}"
            batch: list[tuple[str, str, str, str]] = []
            for row in source.execute(query):
                if time.monotonic() > deadline:
                    raise ComparisonBlocked("semantic_comparison_timeout")
                count += 1
                if count > max_rows:
                    raise ComparisonBlocked("semantic_row_limit")
                values = list(row)
                key_bytes = _canonical([values[i] for i in positions])
                content_bytes = _canonical({
                    col: values[i] for col, i in zip(contents, content_pos)
                })
                if len(key_bytes) + len(content_bytes) > MAX_ROW_BYTES:
                    raise ComparisonBlocked("semantic_row_size_limit")
                key_hash = hashlib.sha256(key_bytes).hexdigest()
                content_hash = hashlib.sha256(content_bytes).hexdigest()
                batch.append((role, table, key_hash, content_hash))
                if len(batch) >= 500:
                    _write_batch(index, batch)
                    batch.clear()
            if batch:
                _write_batch(index, batch)
    index.commit()
    return shapes


def _write_batch(index: sqlite3.Connection, batch: list[tuple[str, str, str, str]]) -> None:
    index.executemany(
        "INSERT INTO hashed_rows(role,table_name,key_hash,content_hash,qty) VALUES(?,?,?,?,1) "
        "ON CONFLICT(role,table_name,key_hash,content_hash) DO UPDATE SET qty=qty+1",
        batch,
    )
    _check_index_budget(index)


def _check_index_budget(index: sqlite3.Connection) -> None:
    pages = int(index.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(index.execute("PRAGMA page_size").fetchone()[0])
    if pages * page_size > MAX_INDEX_BYTES:
        raise ComparisonBlocked("semantic_index_size_limit")


def _key_groups(index: sqlite3.Connection, role: str, table: str, *, deadline: float) -> Iterator[tuple[str, str]]:
    cursor = index.execute(
        "SELECT key_hash,content_hash,qty FROM hashed_rows WHERE role=? AND table_name=? "
        "ORDER BY key_hash,content_hash", (role, table),
    )
    previous: str | None = None
    digest = hashlib.sha256()
    for key, content, qty in cursor:
        if time.monotonic() > deadline:
            raise ComparisonBlocked("semantic_comparison_timeout")
        key = str(key)
        if previous is not None and key != previous:
            yield previous, digest.hexdigest()
            digest = hashlib.sha256()
        previous = key
        digest.update(f"{content}:{qty}\n".encode("ascii"))
    if previous is not None:
        yield previous, digest.hexdigest()


def _diff(index: sqlite3.Connection, table: str, *, deadline: float) -> dict[str, int]:
    left = iter(_key_groups(index, "a", table, deadline=deadline))
    right = iter(_key_groups(index, "b", table, deadline=deadline))
    l, r = next(left, None), next(right, None)
    added = removed = changed = 0
    while l is not None or r is not None:
        if r is None or (l is not None and l[0] < r[0]):
            removed += 1
            l = next(left, None)
        elif l is None or r[0] < l[0]:
            added += 1
            r = next(right, None)
        else:
            if l[1] != r[1]:
                changed += 1
            l, r = next(left, None), next(right, None)
    return {"added": added, "removed": removed, "changed": changed}


def _fingerprint(index: sqlite3.Connection, role: str, tables: list[str], *, deadline: float) -> str:
    sha = hashlib.sha256()
    for table in sorted(tables):
        sha.update(("table:" + table + "\n").encode("utf-8"))
        for key, digest in _key_groups(index, role, table, deadline=deadline):
            sha.update((key + ":" + digest + "\n").encode("ascii"))
    return sha.hexdigest()


def compare_snapshots(
    first: Path, second: Path, *, index: sqlite3.Connection, max_rows: int = MAX_ROWS,
) -> dict[str, Any]:
    """Stable row-key diff of two independent, frozen SQLite snapshots."""
    if max_rows < 1:
        raise ComparisonBlocked("invalid_row_limit")
    if MAX_ROW_BYTES < 1 or MAX_INDEX_BYTES < 1 or OPERATION_SECONDS <= 0:
        raise ComparisonBlocked("invalid_resource_limit")
    deadline = time.monotonic() + OPERATION_SECONDS
    _check_index_budget(index)
    try:
        shapes_a = _index_snapshot(first, index, "a", max_rows=max_rows, deadline=deadline)
        shapes_b = _index_snapshot(second, index, "b", max_rows=max_rows, deadline=deadline)
    except sqlite3.DataError as exc:
        raise ComparisonBlocked("semantic_row_size_limit") from exc
    except sqlite3.OperationalError as exc:
        if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
            raise ComparisonBlocked("semantic_comparison_timeout") from exc
        raise
    if shapes_a != shapes_b:
        return {"state": "incompatible", "fingerprint_equal": None,
                "table_diffs": [], "issue": "table_shapes_differ"}
    rows = []
    for table in sorted(shapes_a):
        if time.monotonic() > deadline:
            raise ComparisonBlocked("semantic_comparison_timeout")
        delta = _diff(index, table, deadline=deadline)
        if any(delta.values()):
            rows.append({"table": table, **delta})
    equal = _fingerprint(index, "a", sorted(shapes_a), deadline=deadline) == _fingerprint(
        index, "b", sorted(shapes_b), deadline=deadline,
    )
    if time.monotonic() > deadline:
        raise ComparisonBlocked("semantic_comparison_timeout")
    if equal == bool(rows):
        raise ComparisonBlocked("fingerprint_and_diff_disagree")
    return {"state": "equal" if equal else "different", "fingerprint_equal": equal,
            "table_diffs": rows, "tables_compared": len(shapes_a),
            "fingerprint_contract": "p1_stable_keys_v1"}


def compare_memory_provenance(
    project: RebuildProject, *, system_root: str | Path,
    target_database: str | Path | None = None,
    temp_root: str | Path | None = None,
    max_database_bytes: int = MAX_DATABASE_BYTES,
    max_source_bytes: int = MAX_SOURCE_BYTES,
    max_rows: int = MAX_ROWS,
) -> dict[str, Any]:
    """Produce an observation, never authorization; no cross-DB atomic snapshot."""
    system = Path(system_root).expanduser()
    target = Path(target_database).expanduser() if target_database else canonical_database_path(project.target_root)
    layout = inspect_memory_layout(project, system_root=system, target_database=target)
    host_state, host_path = _inspect_host_selection(system)
    roles = {"target": target, "staging": _staged(target),
             "host_selected_memory": host_path if host_state["status"] == "host_resolved_only" else None}
    report: dict[str, Any] = {
        "schema": SCHEMA, "layout": layout,
        "roles": {}, "comparisons": {}, "source_provenance": {"state": "unverified"},
        "private_bytes_read_for_hashes": False, "private_content_returned": False,
        "temporary_sensitive_snapshots": False, "temporary_snapshots_cleaned": False,
        "source_databases_writable": False, "cross_database_snapshot_atomic": False,
        "active_runtime_verified": False, "activation_ready": False,
        "publishing_authorized": False,
    }
    accepted: dict[str, Path] = {}
    total = 0
    for role, path in roles.items():
        try:
            ok, issue, size = _eligible(path, max_database_bytes)
        except (OSError, ValueError, sqlite3.Error) as exc:
            ok, issue, size = False, type(exc).__name__.lower(), 0
        report["roles"][role] = {"state": "eligible" if ok else "unverified", "issue": issue}
        if ok and path is not None:
            accepted[role] = path
            total += size
    if "target" not in accepted:
        report["issue"] = "target_native_unverified"
        return report
    base = Path(temp_root).expanduser() if temp_root else Path(tempfile.gettempdir())
    protected = [system, target.parent, Path(project.target_root)]
    if host_path is not None:
        selected_root = host_path.parent.parent if host_path.parent.name == "sqlite" else host_path.parent
        protected.append(selected_root)
    if project.source_directory:
        protected.append(Path(project.source_directory).expanduser())
    if (_has_symlink(base) or not base.is_dir()
            or any(_within(base, p) for p in protected)):
        report["issue"] = "unsafe_snapshot_root"
        return report
    if shutil.disk_usage(base).free < total + 64 * 1024**2:
        report["issue"] = "insufficient_snapshot_space"
        return report
    try:
        with tempfile.TemporaryDirectory(prefix="jazn-memory-compare-", dir=base) as folder:
            location = Path(folder)
            report["temporary_sensitive_snapshots"] = True
            snapshots: dict[str, Path] = {}
            for role, path in accepted.items():
                dest = location / (role + ".sqlite3")
                _backup(path, dest)
                snapshots[role] = dest
            meta = {role: _read_meta(path) for role, path in snapshots.items()}
            report["private_bytes_read_for_hashes"] = True
            report["source_provenance"] = _attest_sources(
                project, meta["target"], byte_limit=max_source_bytes,
            )
            with closing(sqlite3.connect(location / "hashed-index.sqlite3")) as index:
                index.execute(
                    "CREATE TABLE hashed_rows(role TEXT, table_name TEXT, key_hash TEXT, "
                    "content_hash TEXT, qty INTEGER NOT NULL, "
                    "PRIMARY KEY(role,table_name,key_hash,content_hash)) WITHOUT ROWID"
                )
                for role in ("staging", "host_selected_memory"):
                    key = "target_vs_" + role
                    if role not in snapshots:
                        report["comparisons"][key] = {
                            "state": "unverified", "issue": "role_unavailable",
                        }
                        continue
                    if accepted["target"].resolve() == accepted[role].resolve():
                        report["comparisons"][key] = {
                            "state": "same_path_not_independent", "lineage": {"state": "unverified"},
                        }
                        continue
                    index.execute("DELETE FROM hashed_rows")
                    details = compare_snapshots(
                        snapshots["target"], snapshots[role], index=index, max_rows=max_rows,
                    )
                    report["comparisons"][key] = {
                        **details, "lineage": _lineage(meta["target"], meta[role]),
                    }
        report["temporary_snapshots_cleaned"] = True
    except (ComparisonBlocked, OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        report["issue"] = str(exc) if isinstance(exc, ComparisonBlocked) else type(exc).__name__.lower()
        report["comparisons"] = {}
        report["source_provenance"] = {"state": "unverified"}
    return report


__all__ = ["SCHEMA", "ComparisonBlocked", "compare_memory_provenance", "compare_snapshots"]
