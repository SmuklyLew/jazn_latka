from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import json


RECALL_BENCHMARK_SCHEMA = "jazn_memory_recall_benchmark/v2"
LEGACY_PRIVATE_RECALL_SCHEMA = "jazn_private_recall_cases/v1"


class RecallCaseCategory(str, Enum):
    DIRECT = "direct"
    PARAPHRASE = "paraphrase"
    EXPLICIT_RECALL = "explicit_recall"
    IMPLICIT_RECALL = "implicit_recall"
    REFERENTIAL_FOLLOWUP = "referential_followup"
    TEMPORAL = "temporal"
    MULTI_SESSION = "multi_session"
    UPDATE = "update"
    CONFLICT = "conflict"
    NEGATIVE = "negative"
    PROVENANCE = "provenance"
    ROLE_BOUNDARY = "role_boundary"
    SENSITIVE_BOUNDARY = "sensitive_boundary"
    IMPLICIT_CONSTRAINT = "implicit_constraint"


@dataclass(frozen=True, slots=True)
class RecallBenchmarkCase:
    case_id: str
    query: str
    category: RecallCaseCategory = RecallCaseCategory.DIRECT
    expected_any: tuple[str, ...] = ()
    expected_all: tuple[str, ...] = ()
    forbidden_any: tuple[str, ...] = ()
    expected_record_ids: tuple[str, ...] = ()
    expected_source_ids: tuple[str, ...] = ()
    expected_source_kinds: tuple[str, ...] = ()
    expected_abstain: bool = False
    minimum_hits: int = 1
    limit: int = 20
    temporal_start: str | None = None
    temporal_end: str | None = None
    relevance_grades: dict[str, int] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("Recall benchmark case_id cannot be empty")
        if not self.query.strip():
            raise ValueError("Recall benchmark query cannot be empty")
        if self.limit < 1 or self.limit > 500:
            raise ValueError("Recall benchmark limit must be in 1..500")
        if self.minimum_hits < 0:
            raise ValueError("minimum_hits cannot be negative")
        if self.temporal_start and self.temporal_end and self.temporal_start > self.temporal_end:
            raise ValueError("temporal_start cannot be later than temporal_end")
        if self.expected_abstain and (
            self.expected_any
            or self.expected_all
            or self.expected_record_ids
            or self.minimum_hits > 0
        ):
            raise ValueError("abstention cases cannot simultaneously require positive evidence")
        if any(int(value) < 0 for value in self.relevance_grades.values()):
            raise ValueError("relevance grades must be non-negative")

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, legacy: bool = False) -> "RecallBenchmarkCase":
        category_raw = str(payload.get("category") or ("negative" if payload.get("expected_abstain") else "direct"))
        try:
            category = RecallCaseCategory(category_raw)
        except ValueError as exc:
            raise ValueError(f"unsupported Recall case category: {category_raw}") from exc

        def strings(key: str) -> tuple[str, ...]:
            value = payload.get(key)
            if not isinstance(value, list):
                return ()
            return tuple(str(item) for item in value if str(item).strip())

        expected_abstain = bool(payload.get("expected_abstain", False))
        minimum_default = 0 if expected_abstain else 1
        if legacy and not any(payload.get(key) for key in ("expected_any", "expected_all", "expected_record_ids")):
            # v1 negative cases were expressed by minimum_hits=0 plus forbidden terms.
            expected_abstain = int(payload.get("minimum_hits") or 0) == 0
            minimum_default = 0 if expected_abstain else 1
        grades_raw = payload.get("relevance_grades")
        grades = {
            str(key): int(value)
            for key, value in grades_raw.items()
            if isinstance(grades_raw, dict) and str(key).strip()
        } if isinstance(grades_raw, dict) else {}
        return cls(
            case_id=str(payload.get("id") or payload.get("case_id") or "").strip(),
            query=str(payload.get("query") or "").strip(),
            category=category,
            expected_any=strings("expected_any"),
            expected_all=strings("expected_all"),
            forbidden_any=strings("forbidden_any"),
            expected_record_ids=strings("expected_record_ids"),
            expected_source_ids=strings("expected_source_ids"),
            expected_source_kinds=strings("expected_source_kinds") or strings("expected_sources"),
            expected_abstain=expected_abstain,
            minimum_hits=max(0, int(payload.get("minimum_hits", minimum_default))),
            limit=max(1, min(500, int(payload.get("limit") or 20))),
            temporal_start=str(payload.get("temporal_start")) if payload.get("temporal_start") else None,
            temporal_end=str(payload.get("temporal_end")) if payload.get("temporal_end") else None,
            relevance_grades=grades,
            notes=str(payload.get("notes") or ""),
        )


@dataclass(frozen=True, slots=True)
class RecallBenchmarkSuite:
    schema_version: str
    suite_id: str
    cases: tuple[RecallBenchmarkCase, ...]
    minimums: dict[str, float]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.suite_id.strip():
            raise ValueError("Recall benchmark suite_id cannot be empty")
        if not self.cases:
            raise ValueError("Recall benchmark suite cannot be empty")


def load_recall_benchmark(path: str | Path) -> RecallBenchmarkSuite:
    source = Path(path).expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Recall benchmark: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Recall benchmark root must be an object")
    schema = str(payload.get("schema_version") or "")
    if schema not in {RECALL_BENCHMARK_SCHEMA, LEGACY_PRIVATE_RECALL_SCHEMA}:
        raise ValueError(f"unsupported Recall benchmark schema: {schema or '<missing>'}")
    cases_raw = payload.get("cases") if schema == RECALL_BENCHMARK_SCHEMA else payload.get("recall_cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ValueError("Recall benchmark cases are empty")
    cases = tuple(
        RecallBenchmarkCase.from_dict(dict(item), legacy=schema == LEGACY_PRIVATE_RECALL_SCHEMA)
        for item in cases_raw
        if isinstance(item, dict)
    )
    if len(cases) != len(cases_raw):
        raise ValueError("Recall benchmark contains a non-object case")
    minimums_raw = payload.get("minimums")
    minimums: dict[str, float] = {}
    if isinstance(minimums_raw, dict):
        for key, value in minimums_raw.items():
            try:
                minimums[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    suite_id = str(payload.get("suite_id") or payload.get("id") or source.stem)
    return RecallBenchmarkSuite(
        schema_version=schema,
        suite_id=suite_id,
        cases=cases,
        minimums=minimums,
        description=str(payload.get("description") or ""),
    )


__all__ = [
    "LEGACY_PRIVATE_RECALL_SCHEMA",
    "RECALL_BENCHMARK_SCHEMA",
    "RecallBenchmarkCase",
    "RecallBenchmarkSuite",
    "RecallCaseCategory",
    "load_recall_benchmark",
]
