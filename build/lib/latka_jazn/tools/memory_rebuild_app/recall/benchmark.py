from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable
import json
import math
import uuid

from latka_jazn.tools.chat_export_reader import sha256_file

from .baseline import FTS5RecallBaseline
from .metrics import evaluate_case
from .models import RecallBenchmarkCase, RecallBenchmarkSuite, load_recall_benchmark


RECALL_REPORT_SCHEMA = "jazn_memory_recall_report/v1"
DEFAULT_KS = (1, 3, 5, 10, 20)


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * max(0.0, min(1.0, percentile))
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def _mean_defined(values: Iterable[float | None]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return mean(numbers) if numbers else None


def _quality_gate(metrics: dict[str, Any], minimums: dict[str, float]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    lower_bounds = {
        "recall_at_20": metrics.get("recall_at_k", {}).get("20"),
        "mrr": metrics.get("mrr"),
        "ndcg": metrics.get("ndcg_at_limit"),
        "abstention_accuracy": metrics.get("abstention_accuracy"),
        "provenance_accuracy": metrics.get("provenance_accuracy"),
        "temporal_accuracy": metrics.get("temporal_accuracy"),
    }
    upper_bounds = {
        "max_sensitive_leakage_rate": metrics.get("sensitive_leakage_rate"),
        "max_false_memory_rate": metrics.get("false_memory_rate"),
    }
    for key, actual in lower_bounds.items():
        if key not in minimums:
            continue
        expected = float(minimums[key])
        passed = actual is not None and float(actual) >= expected
        checks.append({"name": key, "operator": ">=", "expected": expected, "actual": actual, "passed": passed})
    for key, actual in upper_bounds.items():
        if key not in minimums:
            continue
        expected = float(minimums[key])
        passed = actual is not None and float(actual) <= expected
        checks.append({"name": key, "operator": "<=", "expected": expected, "actual": actual, "passed": passed})
    return {
        "configured": bool(checks),
        "passed": bool(checks) and all(bool(item["passed"]) for item in checks),
        "checks": checks,
    }


def _sanitize_case(case: RecallBenchmarkCase, private: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id_sha256": _hash_text(case.case_id),
        "query_sha256": _hash_text(case.query),
        "category": case.category.value,
        "context_turn_count": len(case.context_turns),
        "context_turns_sha256": _hash_text("\n".join(case.context_turns)),
        "passed_at_limit": private["metrics"]["passed_at_limit"],
        "recall_at_k": private["metrics"]["recall_at_k"],
        "reciprocal_rank": private["metrics"]["reciprocal_rank"],
        "ndcg_at_limit": private["metrics"]["ndcg_at_limit"],
        "provenance_accuracy": private["metrics"]["provenance_accuracy"],
        "temporal_accuracy": private["metrics"]["temporal_accuracy"],
        "abstention_correct": private["metrics"]["abstention_correct"],
        "sensitive_leakage_count": private["metrics"]["sensitive_leakage_count"],
        "hit_count": private["metrics"]["hit_count"],
        "latency_ms": private["latency_ms"],
        "raw_query_persisted": False,
        "raw_expected_terms_persisted": False,
        "raw_hits_persisted": False,
    }


def _aggregate(suite: RecallBenchmarkSuite, reports: list[dict[str, Any]]) -> dict[str, Any]:
    case_count = len(reports)
    recall_at_k = {
        str(k): round(sum(1 for item in reports if item["metrics"]["recall_at_k"].get(k)) / case_count, 6)
        for k in DEFAULT_KS
    }
    abstention = [item for item in reports if item["case"]["expected_abstain"]]
    negative_failures = [item for item in abstention if item["metrics"]["hit_count"] > 0]
    sensitive_cases = [item for item in reports if item["case"]["category"] == "sensitive_boundary"]
    sensitive_leaks = sum(int(item["metrics"]["sensitive_leakage_count"]) for item in sensitive_cases)
    provenance = _mean_defined(item["metrics"]["provenance_accuracy"] for item in reports)
    temporal = _mean_defined(item["metrics"]["temporal_accuracy"] for item in reports)
    latencies = [float(item["latency_ms"]) for item in reports]
    p95_latency = _percentile(latencies, 0.95) if latencies else None
    category_stats: dict[str, dict[str, Any]] = {}
    for item in reports:
        category = str(item["case"]["category"])
        bucket = category_stats.setdefault(category, {"case_count": 0, "passed_count": 0})
        bucket["case_count"] += 1
        bucket["passed_count"] += int(bool(item["metrics"]["passed_at_limit"]))
    for bucket in category_stats.values():
        bucket["accuracy"] = round(bucket["passed_count"] / bucket["case_count"], 6)
    return {
        "case_count": case_count,
        "passed_count": sum(1 for item in reports if item["metrics"]["passed_at_limit"]),
        "accuracy_at_case_limit": round(sum(1 for item in reports if item["metrics"]["passed_at_limit"]) / case_count, 6),
        "recall_at_k": recall_at_k,
        "mrr": round(mean(float(item["metrics"]["reciprocal_rank"]) for item in reports), 6),
        "ndcg_at_limit": round(mean(float(item["metrics"]["ndcg_at_limit"]) for item in reports), 6),
        "abstention_accuracy": (
            round(sum(1 for item in abstention if item["metrics"]["abstention_correct"]) / len(abstention), 6)
            if abstention else None
        ),
        "false_memory_rate": round(len(negative_failures) / len(abstention), 6) if abstention else 0.0,
        "provenance_accuracy": round(provenance, 6) if provenance is not None else None,
        "temporal_accuracy": round(temporal, 6) if temporal is not None else None,
        "sensitive_leakage_count": sensitive_leaks,
        "sensitive_leakage_rate": round(sensitive_leaks / len(sensitive_cases), 6) if sensitive_cases else 0.0,
        "category_stats": category_stats,
        "latency": {
            "p50_ms": round(median(latencies), 6) if latencies else None,
            "p95_ms": round(p95_latency, 6) if p95_latency is not None else None,
            "max_ms": round(max(latencies), 6) if latencies else None,
        },
    }


def run_fts5_recall_benchmark(
    database: str | Path,
    benchmark: str | Path,
    *,
    output_root: str | Path,
    run_id: str | None = None,
) -> dict[str, Any]:
    db = Path(database).expanduser().resolve()
    if not db.is_file():
        raise FileNotFoundError(db)
    suite_path = Path(benchmark).expanduser().resolve()
    suite = load_recall_benchmark(suite_path)
    baseline = FTS5RecallBaseline(db)
    resolved_run_id = run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    run_root = Path(output_root).expanduser().resolve() / resolved_run_id
    run_root.mkdir(parents=True, exist_ok=False)

    reports: list[dict[str, Any]] = []
    for case in suite.cases:
        retrieval = baseline.search(case)
        hits = retrieval["hits"]
        metrics = evaluate_case(case, hits, ks=DEFAULT_KS)
        reports.append(
            {
                "case": {
                    "case_id": case.case_id,
                    "query": case.query,
                    "category": case.category.value,
                    "context_turns": list(case.context_turns),
                    "expected_any": list(case.expected_any),
                    "expected_all": list(case.expected_all),
                    "forbidden_any": list(case.forbidden_any),
                    "expected_record_ids": list(case.expected_record_ids),
                    "expected_source_ids": list(case.expected_source_ids),
                    "expected_source_kinds": list(case.expected_source_kinds),
                    "expected_abstain": case.expected_abstain,
                    "temporal_start": case.temporal_start,
                    "temporal_end": case.temporal_end,
                },
                "metrics": asdict(metrics),
                "latency_ms": retrieval["latency_ms"],
                "hits": hits,
            }
        )

    aggregate = _aggregate(suite, reports)
    gate = _quality_gate(aggregate, suite.minimums)
    private_report = {
        "schema_version": RECALL_REPORT_SCHEMA,
        "run_id": resolved_run_id,
        "suite_id": suite.suite_id,
        "suite_schema_version": suite.schema_version,
        "benchmark_path": str(suite_path),
        "benchmark_sha256": sha256_file(suite_path),
        "database_path": str(db),
        "database_sha256": sha256_file(db),
        "baseline_id": baseline.baseline_id,
        "uses_training": False,
        "uses_embeddings": False,
        "metrics": aggregate,
        "quality_gate": gate,
        "cases": reports,
        "truth_boundary": (
            "This report measures retrieval from the tested database. It does not train a model, "
            "promote memory, activate Jaźń, or convert retrieval success into autobiographical truth."
        ),
    }
    sanitized_report = {
        "schema_version": RECALL_REPORT_SCHEMA,
        "run_id": resolved_run_id,
        "suite_id_sha256": _hash_text(suite.suite_id),
        "suite_schema_version": suite.schema_version,
        "benchmark_path_persisted": False,
        "benchmark_sha256": private_report["benchmark_sha256"],
        "database_path_persisted": False,
        "database_sha256": private_report["database_sha256"],
        "baseline_id": baseline.baseline_id,
        "uses_training": False,
        "uses_embeddings": False,
        "metrics": aggregate,
        "quality_gate": gate,
        "cases": [_sanitize_case(case, report) for case, report in zip(suite.cases, reports)],
        "private_content_persisted": False,
        "truth_boundary": private_report["truth_boundary"],
    }
    private_path = run_root / "recall.private.json"
    sanitized_path = run_root / "recall.sanitized.json"
    private_path.write_text(json.dumps(private_report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    sanitized_path.write_text(json.dumps(sanitized_report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {
        "ok": True,
        "benchmark_completed": True,
        "quality_gate_passed": gate["passed"] if gate["configured"] else None,
        "run_id": resolved_run_id,
        "run_root": str(run_root),
        "baseline_id": baseline.baseline_id,
        "uses_training": False,
        "uses_embeddings": False,
        "metrics": aggregate,
        "quality_gate": gate,
        "private_report": str(private_path),
        "sanitized_report": str(sanitized_path),
    }


__all__ = ["DEFAULT_KS", "RECALL_REPORT_SCHEMA", "run_fts5_recall_benchmark"]
