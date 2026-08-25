from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import os
import sqlite3
import tempfile
import zlib

from .unified_schema import COMPATIBLE_UNIFIED_SCHEMA_VERSIONS, CANONICAL_DATABASE_NAME, quote

FTS_TABLES = ("message_fts", "journal_fts", "experience_fts", "memory_records_fts", "runtime_memory_records_l0_fts")
COUNT_TABLES = (
    "import_sources", "conversations", "nodes", "fts_docs", "assets", "import_conflicts",
    "journal_sources", "journal_entries", "journal_revisions", "candidates", "experiences",
    "candidate_revisions", "candidate_evidence", "memory_records", "memory_evidence",
    "promotion_requests", "promotion_decisions", "promotion_ledger", "sources", "operations",
    "stage4_sources", "music_analyses", "affective_observations", "runtime_memory_sources",
    "runtime_memory_records_l0", "runtime_memory_import_conflicts", "unified_migration_conflicts",
)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def open_read_only(path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA query_only=ON")
    try:
        yield con
    finally:
        con.close()


def _table_names(con: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}


def read_only_stats(path: str | Path) -> dict[str, int]:
    database = Path(path).expanduser().resolve()
    with open_read_only(database) as con:
        names = _table_names(con)
        result: dict[str, int] = {}
        for table in COUNT_TABLES:
            if table in names:
                result[table] = int(con.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()[0])
            else:
                result[table] = 0
        return result


def _snapshot_for_fts_validation(source: Path) -> Path:
    fd, raw = tempfile.mkstemp(prefix="jazn-memory-fts-validation-", suffix=".sqlite3")
    os.close(fd)
    target = Path(raw)
    try:
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30) as src, sqlite3.connect(target) as dst:
            src.backup(dst, pages=512, sleep=0.01)
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _fts_source_sample(con: sqlite3.Connection, table: str) -> str | None:
    if table == "message_fts":
        try:
            doc = con.execute(
                "SELECT conversation_id,node_id FROM fts_docs ORDER BY rowid LIMIT 1"
            ).fetchone()
            if doc is None:
                return None
            payload = con.execute(
                "SELECT payload_codec,payload_blob FROM conversations WHERE conversation_id=?",
                (str(doc[0]),),
            ).fetchone()
            if payload is None or str(payload[0]) != "zlib-json-v1":
                return None
            raw = json.loads(zlib.decompress(payload[1]).decode("utf-8"))
            from latka_jazn.tools.chat_export_reader import build_conversation_graph
            graph = build_conversation_graph(raw)
            node_id = str(doc[1])
            node = next((item for item in graph.nodes if item.node_id == node_id), None)
            return node.text if node is not None and node.text else None
        except (sqlite3.DatabaseError, OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError, zlib.error):
            return None
    queries = {
        "journal_fts": (
            "SELECT e.title||' '||e.summary||' '||e.content FROM journal_fts_docs d "
            "JOIN journal_entries e ON e.entry_id=d.entry_id "
            "WHERE length(trim(e.title||e.summary||e.content))>0 ORDER BY d.rowid LIMIT 1"
        ),
        "experience_fts": (
            "SELECT CASE d.record_type WHEN 'candidate' THEN c.title||' '||c.summary "
            "ELSE e.title||' '||e.summary END FROM experience_fts_docs d "
            "LEFT JOIN candidates c ON d.record_type='candidate' AND c.candidate_id=d.record_id "
            "LEFT JOIN experiences e ON d.record_type<>'candidate' AND e.experience_id=d.record_id "
            "ORDER BY d.rowid LIMIT 1"
        ),
        "memory_records_fts": (
            "SELECT content FROM memory_records WHERE active=1 AND length(trim(content))>0 ORDER BY rowid LIMIT 1"
        ),
        "runtime_memory_records_l0_fts": (
            "SELECT content FROM runtime_memory_records_l0 WHERE active=1 AND length(trim(content))>0 ORDER BY rowid LIMIT 1"
        ),
    }
    query = queries.get(table)
    if not query:
        return None
    try:
        row = con.execute(query).fetchone()
    except sqlite3.DatabaseError:
        return None
    return str(row[0]) if row and row[0] is not None else None


def _fts_smoke_queries(con: sqlite3.Connection, table: str) -> dict[str, Any]:
    rows = int(con.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()[0])
    if rows == 0:
        return {"ok": True, "row_count": 0, "query": None, "matches": 0, "status": "empty"}
    text = _fts_source_sample(con, table)
    if not text:
        return {"ok": False, "row_count": rows, "query": None, "matches": 0, "status": "source_text_missing"}
    token = None
    for part in text.replace("\n", " ").split():
        candidate = "".join(ch for ch in part if ch.isalnum() or ch == "_")
        if len(candidate) >= 3:
            token = candidate
            break
    if not token:
        return {"ok": False, "row_count": rows, "query": None, "matches": 0, "status": "no_query_token"}
    query = token.replace('"', '""')
    matches = int(con.execute(
        f"SELECT COUNT(*) FROM {quote(table)} WHERE {quote(table)} MATCH ?", (f'"{query}"',)
    ).fetchone()[0])
    return {
        "ok": matches > 0, "row_count": rows, "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "query": None, "matches": matches, "status": "passed" if matches > 0 else "no_match",
    }


def validate_fts(path: str | Path) -> dict[str, Any]:
    database = Path(path).expanduser().resolve()
    with open_read_only(database) as con:
        names = _table_names(con)
        required = {"message_fts", "journal_fts", "experience_fts", "memory_records_fts"}
        if "runtime_memory_records_l0" in names:
            required.add("runtime_memory_records_l0_fts")
        missing_required = sorted(required - names)
        smoke = {table: _fts_smoke_queries(con, table) for table in sorted(required & names)}
    snapshot = _snapshot_for_fts_validation(database)
    integrity: dict[str, dict[str, Any]] = {}
    try:
        with sqlite3.connect(snapshot, timeout=30) as con:
            names = _table_names(con)
            for table in sorted(required & names):
                try:
                    # FTS5 integrity-check is itself a special INSERT command.  It is
                    # deliberately executed only on the disposable backup snapshot.
                    con.execute(f"INSERT INTO {quote(table)}({quote(table)}) VALUES('integrity-check')")
                    integrity[table] = {"ok": True, "status": "passed"}
                except sqlite3.DatabaseError as exc:
                    integrity[table] = {"ok": False, "status": "failed", "error": str(exc)}
    finally:
        snapshot.unlink(missing_ok=True)
    ok = (
        not missing_required
        and all(item.get("ok") for item in integrity.values())
        and all(item.get("ok") for item in smoke.values())
    )
    return {
        "ok": ok,
        "required_tables": sorted(required),
        "missing_required_tables": missing_required,
        "integrity": integrity,
        "smoke": smoke,
        "target_modified": False,
    }


def validate_existing_database(path: str | Path, *, full: bool = True, include_fts: bool = True) -> dict[str, Any]:
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        return {
            "ok": False,
            "database": str(database),
            "reason": "database_missing",
            "target_modified": False,
            "stats": {name: 0 for name in COUNT_TABLES},
        }
    try:
        with open_read_only(database) as con:
            pragma = "integrity_check" if full else "quick_check"
            integrity = [str(row[0]) for row in con.execute(f"PRAGMA {pragma}")]
            foreign_keys = [tuple(row) for row in con.execute("PRAGMA foreign_key_check")]
            names = _table_names(con)
            if "unified_memory_meta" in names:
                meta = {str(row[0]): str(row[1]) for row in con.execute("SELECT key,value FROM unified_memory_meta")}
            else:
                meta = {}
            stats = {}
            for table in COUNT_TABLES:
                stats[table] = int(con.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()[0]) if table in names else 0
    except sqlite3.DatabaseError as exc:
        return {
            "ok": False,
            "database": str(database),
            "reason": "sqlite_error",
            "error": str(exc),
            "target_modified": False,
            "stats": {name: 0 for name in COUNT_TABLES},
        }
    schema = meta.get("schema_version")
    layout = meta.get("layout")
    fts = validate_fts(database) if include_fts else {"ok": True, "status": "skipped", "target_modified": False}
    sibling_databases = []
    for candidate in database.parent.glob("*.sqlite3"):
        if candidate.resolve() != database and candidate.name in {
            "archive_chats.sqlite3", "journal.sqlite3", "experience.sqlite3", "import_catalog.sqlite3"
        }:
            sibling_databases.append(candidate.name)
    ok = (
        integrity == ["ok"]
        and not foreign_keys
        and schema in COMPATIBLE_UNIFIED_SCHEMA_VERSIONS
        and layout == "single_physical_database"
        and not sibling_databases
        and bool(fts.get("ok"))
    )
    return {
        "ok": ok,
        "database": str(database),
        "canonical_database_name": CANONICAL_DATABASE_NAME,
        "single_physical_database": not sibling_databases,
        "legacy_sibling_databases": sibling_databases,
        "schema_version": schema,
        "validation_mode": pragma,
        "integrity": integrity,
        "foreign_key_error_count": len(foreign_keys),
        "foreign_key_errors": foreign_keys[:100],
        "size_bytes": database.stat().st_size,
        "sha256": sha256_file(database),
        "stats": stats,
        "fts": fts,
        "target_modified": False,
    }


def promotion_ledger_validation(path: str | Path) -> dict[str, Any]:
    """Verify L2/L3 from persisted structures instead of declaration booleans.

    L2 is not a promotion-to-L3 event in the runtime contract, so the unified DB
    can prove ``automatic_l2 == False`` only when no active short-term records were
    created by the rebuild.  If L2 records exist, their automatic/manual origin is
    not provable from this database alone and the final profile fails closed.

    L3 is provable when every long-term record is linked through
    ``long_term_memory_index`` to a persisted decision and promotion ledger entry,
    and no decision allows automatic commit.
    """
    database = Path(path).expanduser().resolve()
    with open_read_only(database) as con:
        names = _table_names(con)
        required = {
            "memory_records", "short_term_memory_index", "long_term_memory_index",
            "promotion_requests", "promotion_decisions", "promotion_ledger",
        }
        if not required.issubset(names):
            return {
                "ok": False,
                "reason": "promotion_schema_missing",
                "missing_tables": sorted(required - names),
                "automatic_l2": None,
                "automatic_l3": None,
            }
        automatic_decisions = int(con.execute(
            "SELECT COUNT(*) FROM promotion_decisions WHERE automatic_commit_allowed<>0"
        ).fetchone()[0])
        short_term = int(con.execute(
            "SELECT COUNT(*) FROM memory_records WHERE tier='short_term' AND active=1"
        ).fetchone()[0])
        short_index = int(con.execute("SELECT COUNT(*) FROM short_term_memory_index").fetchone()[0])
        orphan_short_term = int(con.execute(
            "SELECT COUNT(*) FROM memory_records m LEFT JOIN short_term_memory_index s ON s.memory_id=m.memory_id "
            "WHERE m.tier='short_term' AND m.active=1 AND s.memory_id IS NULL"
        ).fetchone()[0])
        orphan_short_index = int(con.execute(
            "SELECT COUNT(*) FROM short_term_memory_index s LEFT JOIN memory_records m ON m.memory_id=s.memory_id "
            "WHERE m.memory_id IS NULL OR m.tier<>'short_term'"
        ).fetchone()[0])
        orphan_long_term = int(con.execute(
            "SELECT COUNT(*) FROM memory_records m LEFT JOIN long_term_memory_index l ON l.memory_id=m.memory_id "
            "WHERE m.tier='long_term' AND m.active=1 AND l.memory_id IS NULL"
        ).fetchone()[0])
        orphan_index = int(con.execute(
            "SELECT COUNT(*) FROM long_term_memory_index l LEFT JOIN promotion_decisions d ON d.decision_id=l.promotion_decision_id "
            "WHERE d.decision_id IS NULL"
        ).fetchone()[0])
        missing_ledger = int(con.execute(
            "SELECT COUNT(*) FROM long_term_memory_index l LEFT JOIN promotion_ledger p ON p.decision_id=l.promotion_decision_id "
            "WHERE p.decision_id IS NULL"
        ).fetchone()[0])
        wrong_l3_target = int(con.execute(
            "SELECT COUNT(*) FROM long_term_memory_index l JOIN promotion_decisions d ON d.decision_id=l.promotion_decision_id "
            "WHERE d.target_tier<>'long_term'"
        ).fetchone()[0])
        requests = int(con.execute("SELECT COUNT(*) FROM promotion_requests").fetchone()[0])
        decisions = int(con.execute("SELECT COUNT(*) FROM promotion_decisions").fetchone()[0])
        ledger = int(con.execute("SELECT COUNT(*) FROM promotion_ledger").fetchone()[0])
        long_term = int(con.execute(
            "SELECT COUNT(*) FROM long_term_memory_index WHERE invalidated_at_utc IS NULL"
        ).fetchone()[0])
    l2_structure_ok = orphan_short_term == 0 and orphan_short_index == 0 and short_term == short_index
    # Absence is a proof for rebuild safety.  Presence needs an external L2 decision
    # ledger, which unified v2.4/v2.5 intentionally does not contain.
    automatic_l2: bool | None = False if l2_structure_ok and short_term == 0 else None
    l3_structure_ok = (
        automatic_decisions == 0 and orphan_long_term == 0 and orphan_index == 0
        and missing_ledger == 0 and wrong_l3_target == 0
    )
    automatic_l3: bool | None = False if l3_structure_ok else None
    ok = l2_structure_ok and automatic_l2 is False and l3_structure_ok and automatic_l3 is False
    return {
        "ok": ok,
        "automatic_commit_decisions": automatic_decisions,
        "active_short_term_records": short_term,
        "short_term_index_records": short_index,
        "orphan_short_term_records": orphan_short_term,
        "orphan_short_term_index": orphan_short_index,
        "l2_origin_provable_from_unified_ledger": short_term == 0,
        "orphan_long_term_records": orphan_long_term,
        "orphan_long_term_index": orphan_index,
        "long_term_without_ledger": missing_ledger,
        "long_term_wrong_target_decisions": wrong_l3_target,
        "promotion_requests": requests,
        "promotion_decisions": decisions,
        "promotion_ledger": ledger,
        "active_long_term_records": long_term,
        "automatic_l2": automatic_l2,
        "automatic_l3": automatic_l3,
        "evidence_source": (
            "memory_records+short_term_memory_index+promotion_requests+promotion_decisions+"
            "promotion_ledger+long_term_memory_index"
        ),
        "truth_boundary": (
            "L2 origin is fail-closed: if active short-term records exist, this unified DB alone cannot prove "
            "whether they were created automatically. L3 requires persisted request/decision/ledger lineage."
        ),
    }


def logical_snapshot(path: str | Path, tables: Iterable[str] = COUNT_TABLES) -> dict[str, Any]:
    database = Path(path).expanduser().resolve()
    with open_read_only(database) as con:
        names = _table_names(con)
        result: dict[str, Any] = {}
        for table in tables:
            if table not in names:
                continue
            info = list(con.execute(f"PRAGMA table_info({quote(table)})"))
            columns = [str(row[1]) for row in info]
            pk = [str(row[1]) for row in sorted((row for row in info if int(row[5]) > 0), key=lambda row: int(row[5]))]
            order = pk or columns[:1]
            query = f"SELECT {','.join(quote(c) for c in columns)} FROM {quote(table)}"
            if order:
                query += " ORDER BY " + ",".join(quote(c) for c in order)
            digest = hashlib.sha256()
            count = 0
            for row in con.execute(query):
                digest.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
                digest.update(b"\n")
                count += 1
            result[table] = {"count": count, "sha256": digest.hexdigest(), "primary_key": pk}
        return result
