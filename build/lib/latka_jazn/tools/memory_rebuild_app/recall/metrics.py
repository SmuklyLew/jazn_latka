from __future__ import annotations

from dataclasses import dataclass
from math import log2
from typing import Any, Iterable, Sequence
import re
import unicodedata

from .models import RecallBenchmarkCase


def normalize_text(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain).strip()


def hit_text(hit: dict[str, Any]) -> str:
    return normalize_text(f"{hit.get('title') or ''}\n{hit.get('content') or hit.get('content_excerpt') or ''}")


def _source_ok(case: RecallBenchmarkCase, hit: dict[str, Any]) -> bool:
    source_id = str(hit.get("source_id") or "")
    source_kind = str(hit.get("source_kind") or hit.get("source_layer") or "")
    return (
        (not case.expected_source_ids or source_id in case.expected_source_ids)
        and (not case.expected_source_kinds or source_kind in case.expected_source_kinds)
    )


def hit_is_relevant(case: RecallBenchmarkCase, hit: dict[str, Any]) -> bool:
    if not _source_ok(case, hit):
        return False
    record_id = str(hit.get("record_id") or "")
    if case.expected_record_ids and record_id in case.expected_record_ids:
        return True
    text = hit_text(hit)
    expected_any = [normalize_text(item) for item in case.expected_any]
    expected_all = [normalize_text(item) for item in case.expected_all]
    if expected_all and all(item in text for item in expected_all):
        return True
    if expected_any and any(item in text for item in expected_any):
        return True
    return not case.expected_record_ids and not expected_any and not expected_all and not case.expected_abstain


def case_passes_at_k(case: RecallBenchmarkCase, hits: Sequence[dict[str, Any]], k: int) -> bool:
    selected = list(hits[: max(0, k)])
    if case.expected_abstain:
        return len(selected) == 0
    joined = "\n".join(hit_text(hit) for hit in selected)
    expected_any = [normalize_text(item) for item in case.expected_any]
    expected_all = [normalize_text(item) for item in case.expected_all]
    forbidden = [normalize_text(item) for item in case.forbidden_any]
    any_ok = not expected_any or any(item in joined for item in expected_any)
    all_ok = all(item in joined for item in expected_all)
    forbidden_ok = not any(item and item in joined for item in forbidden)
    source_ok = not (case.expected_source_ids or case.expected_source_kinds) or any(_source_ok(case, hit) for hit in selected)
    record_ok = not case.expected_record_ids or any(str(hit.get("record_id") or "") in case.expected_record_ids for hit in selected)
    return any_ok and all_ok and forbidden_ok and source_ok and record_ok and len(selected) >= case.minimum_hits


def reciprocal_rank(case: RecallBenchmarkCase, hits: Sequence[dict[str, Any]]) -> float:
    if case.expected_abstain:
        return 1.0 if not hits else 0.0
    for index, hit in enumerate(hits, 1):
        if hit_is_relevant(case, hit):
            return 1.0 / index
    return 0.0


def ndcg_at_k(case: RecallBenchmarkCase, hits: Sequence[dict[str, Any]], k: int) -> float:
    selected = list(hits[:k])
    if case.expected_abstain:
        return 1.0 if not selected else 0.0
    grades: list[float] = []
    for hit in selected:
        record_id = str(hit.get("record_id") or "")
        if case.relevance_grades:
            grade = float(case.relevance_grades.get(record_id, 0))
        else:
            grade = 1.0 if hit_is_relevant(case, hit) else 0.0
        grades.append(grade)
    dcg = sum(((2.0**grade) - 1.0) / log2(index + 2.0) for index, grade in enumerate(grades))
    if case.relevance_grades:
        ideal_grades = sorted((float(value) for value in case.relevance_grades.values()), reverse=True)[:k]
    else:
        ideal_count = min(k, max(1, len(case.expected_record_ids) or len(case.expected_any) or 1))
        ideal_grades = [1.0] * ideal_count
    idcg = sum(((2.0**grade) - 1.0) / log2(index + 2.0) for index, grade in enumerate(ideal_grades))
    return dcg / idcg if idcg > 0 else 0.0


def provenance_accuracy(case: RecallBenchmarkCase, hits: Sequence[dict[str, Any]]) -> float | None:
    if not (case.expected_source_ids or case.expected_source_kinds):
        return None
    relevant = [hit for hit in hits if hit_is_relevant(case, hit)]
    if not relevant:
        return 0.0
    return sum(1 for hit in relevant if _source_ok(case, hit)) / len(relevant)


def temporal_accuracy(case: RecallBenchmarkCase, hits: Sequence[dict[str, Any]]) -> float | None:
    if not (case.temporal_start or case.temporal_end):
        return None
    relevant = [hit for hit in hits if hit_is_relevant(case, hit)]
    if not relevant:
        return 0.0
    correct = 0
    for hit in relevant:
        start = hit.get("event_time_start")
        end = hit.get("event_time_end")
        lower = str(end or start or "")
        upper = str(start or end or "")
        after_start = not case.temporal_start or (bool(lower) and lower >= case.temporal_start)
        before_end = not case.temporal_end or (bool(upper) and upper <= case.temporal_end)
        if after_start and before_end:
            correct += 1
    return correct / len(relevant)


def sensitive_leakage(case: RecallBenchmarkCase, hits: Sequence[dict[str, Any]]) -> int:
    forbidden = [normalize_text(item) for item in case.forbidden_any if normalize_text(item)]
    if not forbidden:
        return 0
    return sum(1 for hit in hits if any(term in hit_text(hit) for term in forbidden))


@dataclass(frozen=True, slots=True)
class CaseMetrics:
    passed_at_limit: bool
    recall_at_k: dict[int, bool]
    reciprocal_rank: float
    ndcg_at_limit: float
    provenance_accuracy: float | None
    temporal_accuracy: float | None
    abstention_correct: bool | None
    sensitive_leakage_count: int
    hit_count: int


def evaluate_case(case: RecallBenchmarkCase, hits: Sequence[dict[str, Any]], *, ks: Iterable[int] = (1, 3, 5, 10, 20)) -> CaseMetrics:
    selected = list(hits[: case.limit])
    abstention = (not selected) if case.expected_abstain else None
    return CaseMetrics(
        passed_at_limit=case_passes_at_k(case, selected, case.limit),
        recall_at_k={int(k): case_passes_at_k(case, selected, int(k)) for k in ks},
        reciprocal_rank=reciprocal_rank(case, selected),
        ndcg_at_limit=ndcg_at_k(case, selected, case.limit),
        provenance_accuracy=provenance_accuracy(case, selected),
        temporal_accuracy=temporal_accuracy(case, selected),
        abstention_correct=abstention,
        sensitive_leakage_count=sensitive_leakage(case, selected),
        hit_count=len(selected),
    )


__all__ = [
    "CaseMetrics",
    "case_passes_at_k",
    "evaluate_case",
    "hit_is_relevant",
    "hit_text",
    "ndcg_at_k",
    "normalize_text",
    "provenance_accuracy",
    "reciprocal_rank",
    "sensitive_leakage",
    "temporal_accuracy",
]
