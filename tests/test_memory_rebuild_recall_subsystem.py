from __future__ import annotations

from pathlib import Path
import json

from latka_jazn.tools.memory_rebuild_app.recall import (
    RecallBenchmarkCase,
    RecallCaseCategory,
    evaluate_case,
    run_fts5_recall_benchmark,
)
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase


def _message(mid: str, role: str, text: str, timestamp: float) -> dict:
    return {
        "id": mid,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {},
    }


def _conversation() -> dict:
    return {
        "id": "recall-conv",
        "title": "Latarnia i spacer",
        "create_time": 100.0,
        "update_time": 102.0,
        "current_node": "a",
        "mapping": {
            "u": {
                "id": "u",
                "parent": None,
                "children": ["a"],
                "message": _message("mu", "user", "Na spacerze zobaczyliśmy bursztynową latarnię przy lesie.", 101.0),
            },
            "a": {
                "id": "a",
                "parent": "u",
                "children": [],
                "message": _message("ma", "assistant", "Zapamiętuję źródło rozmowy o bursztynowej latarni.", 102.0),
            },
        },
    }


def test_metrics_measure_relevance_provenance_temporal_abstention_and_leakage() -> None:
    case = RecallBenchmarkCase(
        case_id="c1",
        query="latarnia",
        category=RecallCaseCategory.PROVENANCE,
        expected_any=("bursztynowa latarnia",),
        expected_source_kinds=("chat",),
        forbidden_any=("sekretny-token",),
        temporal_start="2025-01-01T00:00:00+00:00",
        temporal_end="2025-12-31T23:59:59+00:00",
    )
    hits = [
        {
            "record_id": "r1",
            "title": "Spacer",
            "content": "Bursztynowa latarnia była przy lesie.",
            "source_id": "s1",
            "source_kind": "chat",
            "event_time_start": "2025-06-01T10:00:00+00:00",
            "event_time_end": "2025-06-01T10:00:00+00:00",
        }
    ]
    metrics = evaluate_case(case, hits)
    assert metrics.passed_at_limit is True
    assert metrics.reciprocal_rank == 1.0
    assert metrics.provenance_accuracy == 1.0
    assert metrics.temporal_accuracy == 1.0
    assert metrics.sensitive_leakage_count == 0

    negative = RecallBenchmarkCase(
        case_id="neg",
        query="zdarzenie którego nie było",
        category=RecallCaseCategory.NEGATIVE,
        expected_abstain=True,
        minimum_hits=0,
    )
    assert evaluate_case(negative, []).abstention_correct is True
    assert evaluate_case(negative, hits).abstention_correct is False


def test_fts5_baseline_runs_without_training_or_embeddings_and_sanitizes_private_queries(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    source = tmp_path / "conversations.json"
    source.write_text(json.dumps([_conversation()], ensure_ascii=False), encoding="utf-8")
    store = UnifiedMemoryDatabase(database)
    result = store.import_sources([source])
    assert result["ok"], result

    benchmark = tmp_path / "recall.private.json"
    benchmark.write_text(
        json.dumps(
            {
                "schema_version": "jazn_memory_recall_benchmark/v2",
                "suite_id": "synthetic-recall-baseline",
                "minimums": {
                    "recall_at_20": 1.0,
                    "abstention_accuracy": 1.0,
                    "max_false_memory_rate": 0.0,
                    "max_sensitive_leakage_rate": 0.0,
                },
                "cases": [
                    {
                        "id": "direct",
                        "category": "direct",
                        "query": "bursztynowa latarnia",
                        "expected_any": ["bursztynową latarnię"],
                        "minimum_hits": 1,
                        "limit": 20,
                    },
                    {
                        "id": "negative",
                        "category": "negative",
                        "query": "qzxvnieistniejacewspomnienie987654",
                        "expected_abstain": True,
                        "minimum_hits": 0,
                        "limit": 20,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = run_fts5_recall_benchmark(
        database,
        benchmark,
        output_root=tmp_path / "recall-runs",
        run_id="baseline",
    )
    assert report["ok"] is True
    assert report["benchmark_completed"] is True
    assert report["baseline_id"] == "fts5-bm25/v1"
    assert report["uses_training"] is False
    assert report["uses_embeddings"] is False
    assert report["quality_gate_passed"] is True
    assert report["metrics"]["recall_at_k"]["20"] == 1.0
    assert report["metrics"]["abstention_accuracy"] == 1.0
    assert report["metrics"]["false_memory_rate"] == 0.0

    sanitized = Path(report["sanitized_report"]).read_text(encoding="utf-8")
    private = Path(report["private_report"]).read_text(encoding="utf-8")
    assert "bursztynowa latarnia" not in sanitized
    assert "qzxvnieistniejacewspomnienie987654" not in sanitized
    assert "bursztynowa latarnia" in private
    assert '"uses_training": false' in sanitized
    assert '"uses_embeddings": false' in sanitized


def test_sensitive_boundary_reports_leakage_without_calling_it_memory_truth() -> None:
    case = RecallBenchmarkCase(
        case_id="sensitive",
        query="technical source",
        category=RecallCaseCategory.SENSITIVE_BOUNDARY,
        forbidden_any=("credential-secret",),
    )
    hits = [
        {
            "record_id": "tool-1",
            "title": "tool output",
            "content": "credential-secret",
            "source_id": "s",
            "source_kind": "tool",
        }
    ]
    metrics = evaluate_case(case, hits)
    assert metrics.sensitive_leakage_count == 1
    assert metrics.passed_at_limit is False
