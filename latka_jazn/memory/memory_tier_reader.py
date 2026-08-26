from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any
import re
import sqlite3

from latka_jazn.db.runtime_sqlite import connect_runtime_readonly
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("memory_tier_reader")
_REQUIRED_TABLES = {"memory_store_meta", "memory_records", "memory_evidence"}
_REQUIRED_COLUMNS = {
    "memory_id",
    "tier",
    "kind",
    "content",
    "truth_status",
    "confidence",
    "importance",
    "created_at_utc",
    "updated_at_utc",
    "active",
}


def probe_memory_tier_database_readonly(
    path: str | Path,
    *,
    busy_timeout_ms: int = 10_000,
) -> dict[str, Any]:
    database_path = Path(path).expanduser().resolve()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "database_path": str(database_path),
        "status": "missing",
        "memory_search_ready": False,
        "record_count": 0,
        "active_record_count": 0,
        "evidence_count": 0,
        "integrity_check": None,
        "foreign_key_error_count": None,
        "store_schema_version": None,
        "fts5_available": False,
        "read_only": True,
        "issues": [],
    }
    if not database_path.is_file():
        return report
    try:
        with closing(connect_runtime_readonly(database_path, timeout_ms=busy_timeout_ms)) as con:
            tables = {
                str(row["name"])
                for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            report["fts5_available"] = "memory_records_fts" in tables
            missing_tables = sorted(_REQUIRED_TABLES - tables)
            if missing_tables:
                report["status"] = "invalid_schema"
                report["issues"].append("missing_tables:" + ",".join(missing_tables))
                return report
            columns = {
                str(row["name"])
                for row in con.execute("PRAGMA table_info(memory_records)").fetchall()
            }
            missing_columns = sorted(_REQUIRED_COLUMNS - columns)
            if missing_columns:
                report["status"] = "invalid_schema"
                report["issues"].append("missing_columns:" + ",".join(missing_columns))
                return report
            quick = str(con.execute("PRAGMA quick_check").fetchone()[0])
            fk_rows = list(con.execute("PRAGMA foreign_key_check"))
            meta_row = con.execute(
                "SELECT value FROM memory_store_meta WHERE key='schema_version'"
            ).fetchone()
            report["integrity_check"] = quick
            report["foreign_key_error_count"] = len(fk_rows)
            report["store_schema_version"] = str(meta_row[0]) if meta_row else None
            report["record_count"] = int(con.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0])
            report["active_record_count"] = int(
                con.execute("SELECT COUNT(*) FROM memory_records WHERE active=1").fetchone()[0]
            )
            report["evidence_count"] = int(con.execute("SELECT COUNT(*) FROM memory_evidence").fetchone()[0])
            ready = quick == "ok" and not fk_rows
            report["memory_search_ready"] = ready
            report["status"] = "ready_transactional_tier" if ready else "integrity_failed"
            if quick != "ok":
                report["issues"].append(f"quick_check:{quick}")
            if fk_rows:
                report["issues"].append(f"foreign_key_error_count:{len(fk_rows)}")
            return report
    except (sqlite3.Error, OSError, ValueError) as exc:
        report["status"] = "read_error"
        report["issues"].append(f"{type(exc).__name__}:{exc}")
        return report


def _query_terms(query: str) -> tuple[str, list[str]]:
    normalized = " ".join(str(query or "").lower().split())
    terms = [
        token
        for token in re.findall(r"[0-9a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ_-]{3,}", normalized)
        if token not in {"jak", "czy", "jest", "oraz", "sie", "się", "twoja", "twoje", "pamięć", "pamiec"}
    ]
    return normalized, terms


def _fts_query(terms: list[str]) -> str:
    return " OR ".join(
        f'"{term.replace(chr(34), chr(34) * 2)}"*'
        for term in terms
    )


def _evidence_for(con: sqlite3.Connection, memory_id: str) -> list[dict[str, str]]:
    rows = con.execute(
        """SELECT source_type,source_id FROM memory_evidence
           WHERE memory_id=? ORDER BY evidence_key LIMIT 16""",
        (memory_id,),
    ).fetchall()
    return [
        {"source_type": str(row["source_type"]), "source_id": str(row["source_id"])}
        for row in rows
    ]


def search_memory_tier_database_readonly(
    path: str | Path,
    query: str,
    *,
    limit: int = 12,
    candidate_limit: int = 512,
    mode: str = "semantic_query",
    busy_timeout_ms: int = 10_000,
) -> list[dict[str, Any]]:
    """Return bounded, read-only candidates from transactional memory.

    Native unified v3 databases expose ``memory_records_fts``. For semantic
    recall this path delegates candidate selection and ordering directly to
    FTS5 and ``ORDER BY rank``. SQLite documents the hidden ``rank`` column as
    equivalent to the default BM25 auxiliary function and faster for sorted
    queries that may terminate early with ``LIMIT``.

    Historical transactional-tier databases without FTS5 remain supported by
    the bounded recent-candidate fallback; they never trigger an unbounded full
    table scan.
    """
    database_path = Path(path).expanduser().resolve()
    if not database_path.is_file():
        return []
    hard_limit = max(1, min(64, int(limit)))
    window = max(hard_limit, min(2048, int(candidate_limit)))
    normalized_query, terms = _query_terms(query)
    chronological = mode in {"chronological_earliest", "chronological_latest"}
    direction = "ASC" if mode == "chronological_earliest" else "DESC"
    try:
        with closing(connect_runtime_readonly(database_path, timeout_ms=busy_timeout_ms)) as con:
            table_names = {
                str(row["name"])
                for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            use_fts = bool(not chronological and terms and "memory_records_fts" in table_names)
            selected: list[tuple[float, sqlite3.Row, str]] = []

            if use_fts:
                rows = con.execute(
                    """SELECT memory_records.memory_id,memory_records.tier,memory_records.kind,
                              memory_records.content,memory_records.domain,memory_records.mode,
                              memory_records.truth_status,memory_records.confidence,
                              memory_records.importance,memory_records.created_at_utc,
                              memory_records.updated_at_utc,memory_records.tags_json,
                              memory_records_fts.rank AS fts_rank
                       FROM memory_records_fts
                       JOIN memory_records ON memory_records.rowid=memory_records_fts.rowid
                       WHERE memory_records_fts MATCH ? AND memory_records.active=1
                       ORDER BY memory_records_fts.rank,
                                memory_records.importance DESC,
                                memory_records.confidence DESC,
                                memory_records.updated_at_utc DESC
                       LIMIT ?""",
                    (_fts_query(terms), hard_limit),
                ).fetchall()
                for row in rows:
                    raw_rank = float(row["fts_rank"] or 0.0)
                    relevance = 1.0 / (1.0 + abs(raw_rank))
                    selected.append((relevance, row, "memory_records_fts:rank"))
            else:
                rows = con.execute(
                    f"""SELECT memory_id,tier,kind,content,domain,mode,truth_status,confidence,importance,
                               created_at_utc,updated_at_utc,tags_json
                        FROM memory_records
                        WHERE active=1
                        ORDER BY updated_at_utc {direction}
                        LIMIT ?""",
                    (window,),
                ).fetchall()
                ranked: list[tuple[float, sqlite3.Row, str]] = []
                for row in rows:
                    content = str(row["content"] or "")
                    folded = content.lower()
                    if chronological:
                        score = 0.74
                    elif not terms:
                        score = 0.5
                    else:
                        matched = sum(1 for term in terms if term.lower() in folded)
                        if matched == 0:
                            continue
                        coverage = matched / max(1, len(terms))
                        phrase_bonus = 0.12 if normalized_query and normalized_query in folded else 0.0
                        score = min(0.99, 0.48 + 0.42 * coverage + phrase_bonus)
                    ranked.append((score, row, "bounded_table_scan"))
                if not chronological:
                    ranked.sort(
                        key=lambda item: (
                            item[0],
                            float(item[1]["importance"] or 0.0),
                            float(item[1]["confidence"] or 0.0),
                            str(item[1]["updated_at_utc"] or ""),
                        ),
                        reverse=True,
                    )
                selected = ranked[:hard_limit]

            results: list[dict[str, Any]] = []
            for score, row, search_index in selected:
                memory_id = str(row["memory_id"])
                results.append({
                    "memory_id": memory_id,
                    "tier": str(row["tier"]),
                    "kind": str(row["kind"]),
                    "content": str(row["content"]),
                    "domain": str(row["domain"]),
                    "mode": str(row["mode"]),
                    "truth_status": str(row["truth_status"]),
                    "confidence": float(row["confidence"]),
                    "importance": float(row["importance"]),
                    "created_at_utc": str(row["created_at_utc"]),
                    "updated_at_utc": str(row["updated_at_utc"]),
                    "tags_json": str(row["tags_json"] or "[]"),
                    "evidence_sources": _evidence_for(con, memory_id),
                    "relevance": float(score),
                    "source_database": str(database_path),
                    "search_index": search_index,
                    "read_only": True,
                })
            return results
    except (sqlite3.Error, OSError, ValueError):
        return []


__all__ = ["SCHEMA_VERSION", "probe_memory_tier_database_readonly", "search_memory_tier_database_readonly"]
