from __future__ import annotations

from contextlib import closing
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any, Iterable, Sequence
import argparse
import json
import math
import os
import re
import socket
import sqlite3
import unicodedata
import uuid

from latka_jazn.config import JaznConfig
from latka_jazn.cli_commands.diagnostics import status_payload
from latka_jazn.core.runtime_daemon import start_daemon, stop_daemon
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.db.runtime_sqlite import connect_runtime_readonly
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.chat_export_reader import sha256_file
from latka_jazn.tools.memory_rebuild_app import UnifiedMemoryDatabase
from latka_jazn.tools.memory_rebuild_common import fts_queries
from latka_jazn.tools.release_staging import create_system_smoke_staging
from latka_jazn.tools.sqlite_archive_snapshot import create_sqlite_snapshot
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version


SCHEMA_VERSION = schema_version("private_memory_acceptance")
RECALL_CASES_SCHEMA = "jazn_private_recall_cases/v1"
COUNT_TABLES = (
    "import_sources",
    "conversations",
    "nodes",
    "fts_docs",
    "journal_sources",
    "journal_entries",
    "journal_entry_sources",
    "candidates",
    "experiences",
    "experience_sources",
    "memory_records",
    "memory_evidence",
    "promotion_requests",
    "promotion_decisions",
    "promotion_ledger",
    "sources",
    "source_occurrences",
)


def _normalize(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain).strip()


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * max(0.0, min(1.0, percentile))
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 6)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 6)


def _latency_summary(values: Sequence[float]) -> dict[str, Any]:
    return {
        "sample_count": len(values),
        "p50_ms": round(median(values), 6) if values else None,
        "p95_ms": _percentile(values, 0.95),
        "max_ms": round(max(values), 6) if values else None,
    }


class MeasuredLivingMemoryGateway(LivingMemoryGateway):
    def __init__(self, root: str | Path, *, graph_retrieval_mode: str = "shadow") -> None:
        super().__init__(
            root,
            discovery_cache_seconds=3_600.0,
            graph_retrieval_mode=graph_retrieval_mode,
        )
        self.layer_latency_ms: dict[str, list[float]] = {
            layer: [] for layer in self.SEARCH_ORDER
        }

    def _measure(self, layer: str, call: Any, *args: Any, **kwargs: Any) -> Any:
        started = perf_counter()
        try:
            return call(*args, **kwargs)
        finally:
            self.layer_latency_ms[layer].append((perf_counter() - started) * 1000)

    def _search_memory(self, *args: Any, **kwargs: Any) -> Any:
        return self._measure("memory_jazn", super()._search_memory, *args, **kwargs)

    def _search_experience(self, *args: Any, **kwargs: Any) -> Any:
        return self._measure("experience", super()._search_experience, *args, **kwargs)

    def _search_journal(self, *args: Any, **kwargs: Any) -> Any:
        return self._measure("journal", super()._search_journal, *args, **kwargs)

    def _search_archive(self, *args: Any, **kwargs: Any) -> Any:
        return self._measure("archive_chats", super()._search_archive, *args, **kwargs)


def _load_recall_cases(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid recall cases: {type(exc).__name__}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != RECALL_CASES_SCHEMA:
        raise ValueError("unsupported private recall cases schema")
    cases = payload.get("recall_cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("private recall cases are empty")
    for case in cases:
        if not isinstance(case, dict) or not str(case.get("query") or "").strip():
            raise ValueError("private recall case has no query")
    return payload


def _hit_text(hit: dict[str, Any]) -> str:
    return _normalize(f"{hit.get('title') or ''}\n{hit.get('content_excerpt') or ''}")


def _terms(case: dict[str, Any], key: str) -> list[str]:
    value = case.get(key)
    return [str(item) for item in value] if isinstance(value, list) else []


def _case_at_k(case: dict[str, Any], hits: list[dict[str, Any]], k: int) -> bool:
    joined = "\n".join(_hit_text(hit) for hit in hits[:k])
    expected_any = [_normalize(item) for item in _terms(case, "expected_any")]
    expected_all = [_normalize(item) for item in _terms(case, "expected_all")]
    forbidden = [_normalize(item) for item in _terms(case, "forbidden_any")]
    any_ok = not expected_any or any(item in joined for item in expected_any)
    all_ok = all(item in joined for item in expected_all)
    forbidden_ok = not any(item in joined for item in forbidden)
    minimum = max(0, int(case.get("minimum_hits") or 1))
    return any_ok and all_ok and forbidden_ok and len(hits[:k]) >= minimum


def _evaluate_recall(
    database: Path,
    payload: dict[str, Any],
    *,
    graph_retrieval_mode: str = "shadow",
) -> dict[str, Any]:
    gateway = MeasuredLivingMemoryGateway(
        database,
        graph_retrieval_mode=graph_retrieval_mode,
    )
    planner = MemorySearchPlanner(database.parent)
    cases: list[dict[str, Any]] = payload["recall_cases"]
    ks = (1, 3, 5, 10, 20)
    successes = {k: 0 for k in ks}
    total_latency: list[float] = []
    case_reports: list[dict[str, Any]] = []
    returned_rows = 0
    returned_tokens = 0
    wrong_archive_candidates = 0
    archive_candidates = 0
    superseded_returned = 0
    graph_changed_positions = 0
    graph_selected_lanes: dict[str, int] = {}

    for case in cases:
        query = str(case["query"])
        limit = max(1, min(50, int(case.get("limit") or 20)))
        plan = planner.plan(query)
        started = perf_counter()
        result = gateway.search(plan, limit=limit)
        total_latency.append((perf_counter() - started) * 1000)
        hits = [item for item in result.get("hits") or [] if isinstance(item, dict)]
        graph_telemetry = result.get("graph_retrieval")
        if isinstance(graph_telemetry, dict):
            graph_changed_positions += max(
                0, int(graph_telemetry.get("changed_position_count") or 0)
            )
            lane = str(graph_telemetry.get("selected_lane") or "unknown")
            graph_selected_lanes[lane] = graph_selected_lanes.get(lane, 0) + 1
        returned_rows += len(hits)
        returned_tokens += sum(len(re.findall(r"\w+", str(hit.get("content_excerpt") or ""))) for hit in hits)
        expected = [_normalize(item) for item in _terms(case, "expected_any") + _terms(case, "expected_all")]
        for hit in hits:
            metadata_value = hit.get("metadata")
            metadata: dict[str, Any] = metadata_value if isinstance(metadata_value, dict) else {}
            if str(metadata.get("status") or "").casefold() == "superseded":
                superseded_returned += 1
            if hit.get("source_layer") == "archive_chats" and expected:
                archive_candidates += 1
                if not any(term in _hit_text(hit) for term in expected):
                    wrong_archive_candidates += 1
        for k in ks:
            if _case_at_k(case, hits, k):
                successes[k] += 1
        expected_sources = set(_terms(case, "expected_sources"))
        observed_sources = {str(hit.get("source_layer") or "") for hit in hits}
        joined = "\n".join(_hit_text(hit) for hit in hits[:limit])
        expected_any = [_normalize(item) for item in _terms(case, "expected_any")]
        expected_all = [_normalize(item) for item in _terms(case, "expected_all")]
        forbidden = [_normalize(item) for item in _terms(case, "forbidden_any")]
        case_reports.append({
            "case_id_sha256": _hash_text(str(case.get("id") or "")),
            "query_sha256": _hash_text(query),
            "hit_count": len(hits),
            "passed_at_limit": _case_at_k(case, hits, limit),
            "expected_source_match": not expected_sources or bool(expected_sources & observed_sources),
            "expected_any_count": len(expected_any),
            "expected_any_match_count": sum(1 for item in expected_any if item in joined),
            "expected_all_count": len(expected_all),
            "expected_all_match_count": sum(1 for item in expected_all if item in joined),
            "forbidden_count": len(forbidden),
            "forbidden_match_count": sum(1 for item in forbidden if item in joined),
            "raw_query_persisted": False,
            "raw_expected_terms_persisted": False,
            "raw_results_persisted": False,
        })

    abstention_token = "qzxv" + _hash_text(sha256_file(database))[:28]
    abstention = gateway.search(planner.plan(abstention_token), limit=5)
    chronology_checks: list[bool] = []
    for case in cases[: min(5, len(cases))]:
        query = str(case["query"])
        for mode in ("chronological_earliest", "chronological_latest"):
            plan = planner.plan(query)
            object.__setattr__(plan, "search_mode", mode)
            result = gateway.search(plan, limit=10)
            timestamps = [str(hit.get("timestamp")) for hit in result.get("hits") or [] if hit.get("timestamp")]
            chronology_checks.append(
                timestamps == sorted(timestamps, reverse=mode.endswith("latest"))
            )

    first_case = cases[0]
    first_query = str(first_case["query"])
    first_turn = gateway.search(planner.plan(first_query), limit=10)
    followup = planner.plan(
        "Wróć do tego wspomnienia i doprecyzuj źródło.",
        previous_query=first_query,
    )
    second_turn = gateway.search(followup, limit=10)
    multi_turn_ok = _case_at_k(
        first_case,
        [item for item in second_turn.get("hits") or [] if isinstance(item, dict)],
        10,
    )

    first_fingerprint = _recall_fingerprint(database, cases)
    second_fingerprint = _recall_fingerprint(database, cases)
    evidence_presence = _expected_evidence_presence(database, cases)
    eligible_ids = {
        str(item["case_id_sha256"])
        for item in evidence_presence["cases"]
        if item["evidence_eligible"]
    }
    eligible_case_reports = [
        item for item in case_reports if str(item["case_id_sha256"]) in eligible_ids
    ]
    case_count = len(cases)
    return {
        "ok": all(item["passed_at_limit"] and item["expected_source_match"] for item in case_reports),
        "graph_retrieval": {
            "mode": graph_retrieval_mode,
            "selected_lane_counts": graph_selected_lanes,
            "changed_position_count": graph_changed_positions,
            "fts_fallback_available": True,
            "private_content_persisted": False,
        },
        "case_count": case_count,
        "passed_count": sum(1 for item in case_reports if item["passed_at_limit"]),
        "evidence_eligible_case_count": len(eligible_case_reports),
        "evidence_eligible_passed_count": sum(
            1 for item in eligible_case_reports if item["passed_at_limit"]
        ),
        "evidence_eligible_recall_at_limit": round(
            sum(1 for item in eligible_case_reports if item["passed_at_limit"])
            / len(eligible_case_reports),
            6,
        ) if eligible_case_reports else None,
        "evidence_recall_at_k": {
            str(k): round(successes[k] / case_count, 6) for k in ks
        },
        "wrong_conversation_proxy": {
            "definition": "archive candidates without any case evidence term divided by archive candidates",
            "candidate_count": archive_candidates,
            "wrong_candidate_count": wrong_archive_candidates,
            "rate": round(wrong_archive_candidates / archive_candidates, 6) if archive_candidates else 0.0,
        },
        "temporal_ordering_accuracy": round(sum(chronology_checks) / len(chronology_checks), 6) if chronology_checks else None,
        "superseded_rows_returned": superseded_returned,
        "abstention": {
            "ok": not bool(abstention.get("hits")),
            "hit_count": len(abstention.get("hits") or []),
            "query_sha256": _hash_text(abstention_token),
        },
        "latency": {
            "total_turn": _latency_summary(total_latency),
            "per_layer": {
                layer: _latency_summary(values)
                for layer, values in gateway.layer_latency_ms.items()
            },
        },
        "observable_read_volume": {
            "returned_source_rows": returned_rows,
            "returned_excerpt_tokens": returned_tokens,
            "sqlite_internal_rows_scanned_observable": False,
        },
        "restart_reproducibility": {
            "fresh_gateway_fingerprint_equal": first_fingerprint == second_fingerprint,
            "before_sha256": first_fingerprint,
            "after_sha256": second_fingerprint,
        },
        "multi_turn": {
            "real_private_recall_used": True,
            "turn_count": 2,
            "first_turn_hit_count": len(first_turn.get("hits") or []),
            "referential_followup_passed": multi_turn_ok,
            "manual_naturalness_review_required": True,
        },
        "cases": case_reports,
        "expected_evidence_presence": evidence_presence,
        "private_content_persisted": False,
    }


def _graph_retrieval_ab_report(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_recall = float(baseline["evidence_recall_at_k"].get("20") or 0.0)
    candidate_recall = float(candidate["evidence_recall_at_k"].get("20") or 0.0)
    baseline_wrong = float(baseline["wrong_conversation_proxy"].get("rate") or 0.0)
    candidate_wrong = float(candidate["wrong_conversation_proxy"].get("rate") or 0.0)
    baseline_eligible = baseline.get("evidence_eligible_recall_at_limit")
    candidate_eligible = candidate.get("evidence_eligible_recall_at_limit")
    eligible_non_regression = (
        baseline_eligible is None
        or (
            candidate_eligible is not None
            and float(candidate_eligible) >= float(baseline_eligible)
        )
    )
    quality_gate_passed = bool(
        candidate.get("ok")
        and candidate_recall >= baseline_recall
        and candidate_wrong <= baseline_wrong
        and eligible_non_regression
    )
    return {
        "status": "measured",
        "baseline_mode": "shadow",
        "candidate_mode": "active_test_lane",
        "baseline": {
            "ok": bool(baseline.get("ok")),
            "recall_at_20": baseline_recall,
            "evidence_eligible_recall_at_limit": baseline_eligible,
            "wrong_conversation_proxy_rate": baseline_wrong,
            "latency": baseline.get("latency"),
        },
        "candidate": {
            "ok": bool(candidate.get("ok")),
            "recall_at_20": candidate_recall,
            "evidence_eligible_recall_at_limit": candidate_eligible,
            "wrong_conversation_proxy_rate": candidate_wrong,
            "latency": candidate.get("latency"),
            "changed_position_count": (
                candidate.get("graph_retrieval") or {}
            ).get("changed_position_count", 0),
        },
        "delta": {
            "recall_at_20": round(candidate_recall - baseline_recall, 6),
            "wrong_conversation_proxy_rate": round(candidate_wrong - baseline_wrong, 6),
        },
        "quality_gate_passed": quality_gate_passed,
        "approved_for_activation": False,
        "automatic_activation_performed": False,
        "manual_activation_required": True,
        "fts_fallback_available": True,
        "private_content_persisted": False,
        "truth_boundary": (
            "A/B measurement can reject a candidate but never activates it. "
            "Activation requires a separate explicit decision after review."
        ),
    }


def _expected_evidence_presence(database: Path, cases: list[dict[str, Any]]) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    with closing(connect_runtime_readonly(database, timeout_ms=30_000)) as con:
        tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for case in cases:
            expected_any = _terms(case, "expected_any")
            expected_all = _terms(case, "expected_all")
            expected = expected_any + expected_all
            found = 0
            archive_found = 0
            journal_found = 0
            present_terms: set[str] = set()
            for term in expected:
                exact_query = fts_queries(term)[0]
                archive_count = 0
                journal_count = 0
                if {"message_fts", "conversations"}.issubset(tables):
                    try:
                        archive_count += int(con.execute(
                            "SELECT COUNT(*) FROM message_fts WHERE message_fts MATCH ?",
                            (exact_query,),
                        ).fetchone()[0])
                    except sqlite3.Error:
                        archive_count += 0
                    archive_count += int(con.execute(
                        "SELECT COUNT(*) FROM conversations WHERE title LIKE ?",
                        (f"%{term}%",),
                    ).fetchone()[0])
                if "journal_entries" in tables:
                    journal_count += int(con.execute(
                        "SELECT COUNT(*) FROM journal_entries WHERE title LIKE ? OR summary LIKE ? OR content LIKE ?",
                        (f"%{term}%", f"%{term}%", f"%{term}%"),
                    ).fetchone()[0])
                if archive_count or journal_count:
                    found += 1
                    present_terms.add(term)
                if archive_count:
                    archive_found += 1
                if journal_count:
                    journal_found += 1
            reports.append({
                "case_id_sha256": _hash_text(str(case.get("id") or "")),
                "expected_term_count": len(expected),
                "present_term_count": found,
                "archive_present_term_count": archive_found,
                "journal_present_term_count": journal_found,
                "expected_any_count": len(expected_any),
                "expected_any_present_count": sum(1 for term in expected_any if term in present_terms),
                "expected_all_count": len(expected_all),
                "expected_all_present_count": sum(1 for term in expected_all if term in present_terms),
                "evidence_eligible": (
                    (not expected_any or any(term in present_terms for term in expected_any))
                    and all(term in present_terms for term in expected_all)
                ),
            })
    total = sum(item["expected_term_count"] for item in reports)
    present = sum(item["present_term_count"] for item in reports)
    return {
        "expected_term_count": total,
        "present_term_count": present,
        "coverage": round(present / total, 6) if total else 1.0,
        "cases": reports,
        "raw_terms_persisted": False,
    }


def _recall_fingerprint(database: Path, cases: Iterable[dict[str, Any]]) -> str:
    gateway = LivingMemoryGateway(database, discovery_cache_seconds=3_600.0)
    planner = MemorySearchPlanner(database.parent)
    rows: list[dict[str, Any]] = []
    for case in cases:
        result = gateway.search(planner.plan(str(case["query"])), limit=10)
        rows.append({
            "query_sha256": _hash_text(str(case["query"])),
            "hits": [
                {
                    "layer": hit.get("source_layer"),
                    "record_id_sha256": _hash_text(str(hit.get("record_id") or "")),
                    "timestamp": hit.get("timestamp"),
                    "truth_status": hit.get("truth_status"),
                }
                for hit in result.get("hits") or []
            ],
        })
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _hash_text(encoded)


def _database_metrics(database: Path) -> dict[str, Any]:
    with closing(connect_runtime_readonly(database, timeout_ms=30_000)) as con:
        tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {
            table: int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in COUNT_TABLES if table in tables
        }
        duplicates: dict[str, int] = {}
        for table in ("import_sources", "journal_sources", "sources"):
            if table in tables:
                duplicates[table] = int(con.execute(
                    f'SELECT COUNT(*) FROM (SELECT sha256 FROM "{table}" GROUP BY sha256 HAVING COUNT(*)>1)'
                ).fetchone()[0])
        orphan_import_refs = 0
        if {"conversations", "import_sources"}.issubset(tables):
            orphan_import_refs = int(con.execute(
                """SELECT COUNT(*) FROM conversations c
                     WHERE NOT EXISTS(SELECT 1 FROM import_sources i WHERE i.import_id=c.first_seen_import_id)
                        OR NOT EXISTS(SELECT 1 FROM import_sources i WHERE i.import_id=c.last_seen_import_id)"""
            ).fetchone()[0])
        tier_counts = {}
        if "memory_records" in tables:
            tier_counts = {
                str(row[0]): int(row[1])
                for row in con.execute("SELECT tier,COUNT(*) FROM memory_records GROUP BY tier")
            }
        candidate_status = {}
        if "candidates" in tables:
            candidate_status = {
                str(row[0]): int(row[1])
                for row in con.execute("SELECT status,COUNT(*) FROM candidates GROUP BY status")
            }
        auto_commit = 0
        if "promotion_decisions" in tables:
            auto_commit = int(con.execute(
                "SELECT COUNT(*) FROM promotion_decisions WHERE automatic_commit_allowed<>0"
            ).fetchone()[0])
    return {
        "table_counts": counts,
        "duplicate_sha_groups": duplicates,
        "hidden_duplicate_imports_absent": not any(duplicates.values()),
        "orphan_conversation_import_references": orphan_import_refs,
        "tier_counts": tier_counts,
        "candidate_status_counts": candidate_status,
        "promotion_ledger_count": counts.get("promotion_ledger", 0),
        "automatic_promotion_decision_count": auto_commit,
        "automatic_l3_detected": auto_commit > 0,
    }


def _source_identity(path: Path) -> dict[str, Any]:
    if path.is_file():
        return {
            "content_sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "file_count": 1,
        }
    if not path.is_dir():
        return {"content_sha256": None, "size_bytes": 0, "file_count": 0}
    digest = sha256()
    size = 0
    count = 0
    for item in sorted((value for value in path.rglob("*") if value.is_file()), key=lambda value: str(value.relative_to(path)).casefold()):
        item_hash = sha256_file(item)
        relative_hash = _hash_text(item.relative_to(path).as_posix())
        digest.update(f"{relative_hash}:{item_hash}:{item.stat().st_size}\n".encode("ascii"))
        size += item.stat().st_size
        count += 1
    return {"content_sha256": digest.hexdigest(), "size_bytes": size, "file_count": count}


def _source_inventory(manifest_path: Path | None, database: Path) -> dict[str, Any]:
    if manifest_path is None:
        return {
            "status": "not_supplied",
            "ok": True,
            "source_count": 0,
            "private_paths_persisted": False,
        }
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        raise ValueError("private source manifest has no sources")
    reports: list[dict[str, Any]] = []
    source_hashes: set[str] = set()
    for ordinal, item in enumerate(sources, 1):
        if not isinstance(item, dict):
            continue
        source = Path(str(item.get("path") or "")).expanduser().resolve()
        identity = _source_identity(source)
        if identity["content_sha256"]:
            source_hashes.add(str(identity["content_sha256"]))
        reports.append({
            "ordinal": ordinal,
            "path_sha256": _hash_text(str(source)),
            **identity,
            "approved": item.get("approved") is True,
            "latest_export": item.get("latest_export") is True,
        })
    with closing(connect_runtime_readonly(database, timeout_ms=30_000)) as con:
        tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        imported: set[str] = set()
        for table in ("import_sources", "journal_sources", "sources"):
            if table in tables:
                imported.update(str(row[0]) for row in con.execute(f'SELECT sha256 FROM "{table}"'))
    attestations = payload.get("operator_attestation") if isinstance(payload, dict) else None
    attestation_values = list(attestations.values()) if isinstance(attestations, dict) else []
    ordinals = [int(item.get("ordinal") or 0) for item in sources if isinstance(item, dict)]
    expected_ordinals = list(range(1, len(reports) + 1))
    latest_count = sum(1 for item in sources if isinstance(item, dict) and item.get("latest_export") is True)
    provenance_match_count = len(source_hashes & imported)
    manifest_ok = bool(
        reports
        and all(item["content_sha256"] for item in reports)
        and all(item["approved"] for item in reports)
        and bool(attestation_values)
        and all(value is True for value in attestation_values)
        and ordinals == expected_ordinals
        and latest_count == 1
        and provenance_match_count == len(source_hashes)
    )
    return {
        "status": "evaluated",
        "ok": manifest_ok,
        "source_count": len(reports),
        "unique_source_hash_count": len(source_hashes),
        "all_sources_exist": all(item["content_sha256"] for item in reports),
        "approved_source_count": sum(1 for item in reports if item["approved"]),
        "direct_import_hash_match_count": provenance_match_count,
        "database_source_hash_count": len(imported),
        "all_source_hashes_registered": provenance_match_count == len(source_hashes),
        "operator_attestation_complete": bool(attestation_values) and all(
            value is True for value in attestation_values
        ),
        "source_ordinals_contiguous": ordinals == expected_ordinals,
        "latest_export_count": latest_count,
        "sources": reports,
        "private_paths_persisted": False,
        "private_names_persisted": False,
    }


def _prepare_review_snapshot(database: Path, output_root: Path, candidate_limit: int) -> dict[str, Any]:
    snapshot = output_root / "review-staging" / "memory_jazn.sqlite3"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot_report = create_sqlite_snapshot(database, snapshot, full_integrity_check=True)
    store = UnifiedMemoryDatabase(snapshot)
    before = store.stats()
    generated = store.generate_candidates(limit=max(1, min(2_000, candidate_limit)))
    after = store.stats()
    validation = store.validate(full=True)
    return {
        "ok": bool(validation.get("ok")),
        "snapshot_sha256": snapshot_report.snapshot_sha256,
        "snapshot_size_bytes": snapshot_report.snapshot_size_bytes,
        "candidate_count_before": before.get("candidates", 0),
        "candidate_count_after": after.get("candidates", 0),
        "candidate_count_added": max(0, after.get("candidates", 0) - before.get("candidates", 0)),
        "experience_count_before": before.get("experiences", 0),
        "experience_count_after": after.get("experiences", 0),
        "memory_record_count_before": before.get("memory_records", 0),
        "memory_record_count_after": after.get("memory_records", 0),
        "automatic_l2": bool(generated.get("automatic_l2")),
        "automatic_l3": bool(generated.get("automatic_l3")),
        "review_ready_only": True,
        "private_path_persisted": False,
    }


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _daemon_active_state(payload: dict[str, Any]) -> str | None:
    daemon = payload.get("daemon") if isinstance(payload.get("daemon"), dict) else payload
    value = daemon.get("active_state") if isinstance(daemon, dict) else None
    return str(value) if value else None


def run_isolated_daemon_continuity(
    source_runtime_root: Path,
    work_root: Path,
    database: Path,
    cases: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Restart an isolated daemon twice and retain only anonymized continuity evidence."""

    run_root = work_root.expanduser().resolve() / f"run-{uuid.uuid4().hex}"
    runtime_root = run_root / "runtime"
    workspace = run_root / "workspace_runtime"
    staging = create_system_smoke_staging(source_runtime_root, runtime_root)
    workspace.mkdir(parents=True, exist_ok=True)
    _write_json(workspace / "memory_source_registry.json", {
        "schema_version": "jazn_memory_source_registry/v1",
        "sources": [{"path": str(database), "enabled": True, "read_only": True}],
    })
    prior_workspace = os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR")
    prior_sources = os.environ.get("JAZN_MEMORY_SOURCE_ROOTS")
    os.environ["JAZN_RUNTIME_WORKSPACE_DIR"] = str(workspace)
    os.environ.pop("JAZN_MEMORY_SOURCE_ROOTS", None)
    port = _free_loopback_port()
    marker = workspace / "JAZN_ACTIVE_RUNTIME.json"
    config = JaznConfig(root=runtime_root, allow_network=False, network_time_first=False)
    first_start: dict[str, Any] = {}
    second_start: dict[str, Any] = {}
    first_status: dict[str, Any] = {}
    second_status: dict[str, Any] = {}
    first_stop: dict[str, Any] = {}
    second_stop: dict[str, Any] = {}
    try:
        readiness = LivingMemoryGateway(runtime_root).readiness()
        before = _recall_fingerprint(database, cases)
        first_start = start_daemon(
            config,
            host="127.0.0.1",
            port=port,
            marker_output=marker,
            heartbeat_interval=0.2,
            startup_timeout=30.0,
        )
        if first_start.get("ok") is True:
            first_status = status_payload(
                runtime_root,
                daemon_host="127.0.0.1",
                daemon_port=port,
                marker_output=marker,
            )
            first_stop = stop_daemon(
                config,
                host="127.0.0.1",
                port=port,
                marker_output=marker,
                timeout=20.0,
            )
        second_start = start_daemon(
            config,
            host="127.0.0.1",
            port=port,
            marker_output=marker,
            heartbeat_interval=0.2,
            startup_timeout=30.0,
        )
        if second_start.get("ok") is True:
            second_status = status_payload(
                runtime_root,
                daemon_host="127.0.0.1",
                daemon_port=port,
                marker_output=marker,
            )
        after = _recall_fingerprint(database, cases)
    finally:
        try:
            second_stop = stop_daemon(
                config,
                host="127.0.0.1",
                port=port,
                marker_output=marker,
                timeout=20.0,
            )
        finally:
            if prior_workspace is None:
                os.environ.pop("JAZN_RUNTIME_WORKSPACE_DIR", None)
            else:
                os.environ["JAZN_RUNTIME_WORKSPACE_DIR"] = prior_workspace
            if prior_sources is None:
                os.environ.pop("JAZN_MEMORY_SOURCE_ROOTS", None)
            else:
                os.environ["JAZN_MEMORY_SOURCE_ROOTS"] = prior_sources
    first_pid = first_start.get("pid")
    second_pid = second_start.get("pid")
    ok = bool(
        staging.get("ok")
        and readiness.get("status") == "ready_native_unified"
        and readiness.get("selected_source_count") == 1
        and first_start.get("ok") is True
        and second_start.get("ok") is True
        and _daemon_active_state(first_status) == "active_trusted"
        and _daemon_active_state(second_status) == "active_trusted"
        and first_stop.get("stopped") is True
        and second_stop.get("stopped") is True
        and first_pid
        and second_pid
        and first_pid != second_pid
        and before == after
    )
    return {
        "status": "passed" if ok else "failed",
        "ok": ok,
        "staging_verified": staging.get("ok") is True,
        "registry_selected_one_native_unified_source": (
            readiness.get("status") == "ready_native_unified"
            and readiness.get("selected_source_count") == 1
        ),
        "first_active_state": _daemon_active_state(first_status),
        "second_active_state": _daemon_active_state(second_status),
        "first_stop_confirmed": first_stop.get("stopped") is True,
        "second_stop_confirmed": second_stop.get("stopped") is True,
        "daemon_pid_changed": bool(first_pid and second_pid and first_pid != second_pid),
        "recall_fingerprint_equal": before == after,
        "before_sha256": before,
        "after_sha256": after,
        "private_paths_persisted_in_report": False,
        "active_system_runtime_modified": False,
    }


def run_acceptance(
    database: Path,
    recall_cases: Path,
    *,
    source_manifest: Path | None = None,
    output_root: Path | None = None,
    prepare_review_snapshot: bool = False,
    candidate_limit: int = 250,
    source_runtime_root: Path | None = None,
    isolated_restart_root: Path | None = None,
    run_graph_retrieval_ab: bool = False,
) -> dict[str, Any]:
    database = database.expanduser().resolve()
    cases_path = recall_cases.expanduser().resolve()
    probe = probe_unified_memory_database(database, full_integrity=True)
    if not probe.get("memory_search_ready"):
        raise RuntimeError("private unified database failed the native readiness gate")
    cases = _load_recall_cases(cases_path)
    metrics = _database_metrics(database)
    inventory = _source_inventory(source_manifest.expanduser().resolve() if source_manifest else None, database)
    recall = _evaluate_recall(database, cases)
    graph_retrieval_ab = {
        "status": "not_run",
        "approved_for_activation": False,
        "automatic_activation_performed": False,
        "manual_activation_required": True,
        "fts_fallback_available": True,
        "private_content_persisted": False,
    }
    if run_graph_retrieval_ab:
        candidate_recall = _evaluate_recall(
            database,
            cases,
            graph_retrieval_mode="active",
        )
        graph_retrieval_ab = _graph_retrieval_ab_report(recall, candidate_recall)
    review = {
        "status": "not_generated",
        "review_ready_only": True,
        "automatic_l3": False,
    }
    if prepare_review_snapshot:
        if output_root is None:
            raise ValueError("review snapshot requires output_root")
        review = _prepare_review_snapshot(database, output_root, candidate_limit)
        review["status"] = "generated_on_private_snapshot"
    daemon_continuity = {
        "status": "not_run",
        "ok": None,
        "private_paths_persisted_in_report": False,
        "active_system_runtime_modified": False,
    }
    if source_runtime_root is not None or isolated_restart_root is not None:
        if source_runtime_root is None or isolated_restart_root is None:
            raise ValueError("isolated daemon continuity requires both runtime and output roots")
        daemon_continuity = run_isolated_daemon_continuity(
            source_runtime_root.expanduser().resolve(),
            isolated_restart_root.expanduser().resolve(),
            database,
            cases["recall_cases"],
        )
    ok = bool(
        probe.get("memory_search_ready")
        and inventory.get("ok") is True
        and not metrics["automatic_l3_detected"]
        and metrics["hidden_duplicate_imports_absent"]
        and metrics["orphan_conversation_import_references"] == 0
        and recall["ok"]
        and recall["abstention"]["ok"]
        and recall["superseded_rows_returned"] == 0
        and recall["restart_reproducibility"]["fresh_gateway_fingerprint_equal"]
        and review.get("automatic_l3") is not True
        and daemon_continuity.get("ok") is not False
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_version": PACKAGE_VERSION_FULL,
        "ok": ok,
        "database": {
            "path_sha256": _hash_text(str(database)),
            "file_sha256": sha256_file(database),
            "size_bytes": database.stat().st_size,
            "schema_identity": probe.get("schema_identity"),
            "integrity": probe.get("integrity_check"),
            "foreign_key_error_count": probe.get("foreign_key_error_count"),
            "fts_counts": probe.get("fts_counts"),
            "memory_search_ready": probe.get("memory_search_ready"),
        },
        "data": metrics,
        "source_inventory": inventory,
        "recall": recall,
        "graph_retrieval_ab": graph_retrieval_ab,
        "l2_l3_review": review,
        "daemon_restart_continuity": daemon_continuity,
        "system_activation_performed": False,
        "l3_promotion_authorized": False,
        "l3_promotion_performed": False,
        "private_content_persisted": False,
        "private_paths_persisted": False,
        "truth_boundary": (
            "Acceptance validates a local private unified database and persists only hashes, counts, "
            "latencies and pass/fail evidence. It does not authorize L3 promotion, prove subjective "
            "experience or replace manual review of natural multi-turn quality."
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Anonymized private unified-memory acceptance")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--recall-cases", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--prepare-review-snapshot", action="store_true")
    parser.add_argument("--candidate-limit", type=int, default=250)
    parser.add_argument("--source-runtime-root", type=Path)
    parser.add_argument("--isolated-restart-root", type=Path)
    parser.add_argument("--run-graph-retrieval-ab", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = args.output_root.expanduser().resolve() if args.output_root else None
    report = run_acceptance(
        args.database,
        args.recall_cases,
        source_manifest=args.source_manifest,
        output_root=output_root,
        prepare_review_snapshot=args.prepare_review_snapshot,
        candidate_limit=args.candidate_limit,
        source_runtime_root=args.source_runtime_root,
        isolated_restart_root=args.isolated_restart_root,
        run_graph_retrieval_ab=args.run_graph_retrieval_ab,
    )
    if args.output:
        _write_json(args.output.expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MeasuredLivingMemoryGateway",
    "run_acceptance",
    "run_isolated_daemon_continuity",
]
