from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("operational_learning_memory")


@dataclass(slots=True)
class OperationalLesson:
    lesson_id: str
    trigger_signature: str
    expected_behavior: str
    observed_failure: str
    root_cause: str
    repair_rule: str
    regression_test_id: str | None = None
    applicability_terms: list[str] = field(default_factory=list)
    confidence: float = 0.8
    verified: bool = False
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Lekcja operacyjna jest audytowalną regułą antyregresyjną. Nie modyfikuje samodzielnie kodu, "
        "nie staje się wspomnieniem autobiograficznym i nie może zastąpić testu."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OperationalLearningMemory:
    def __init__(self, lessons: Iterable[OperationalLesson] | None = None) -> None:
        self._lessons: dict[str, OperationalLesson] = {item.lesson_id: item for item in (lessons or [])}

    @staticmethod
    def _fold(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").lower()).translate(
            str.maketrans("ąćęłńóśźż", "acelnoszz")
        ).strip()

    @classmethod
    def make_lesson(
        cls,
        *,
        trigger_signature: str,
        expected_behavior: str,
        observed_failure: str,
        root_cause: str,
        repair_rule: str,
        regression_test_id: str | None = None,
        applicability_terms: Iterable[str] = (),
        confidence: float = 0.8,
        verified: bool = False,
    ) -> OperationalLesson:
        material = "\n".join((trigger_signature, expected_behavior, root_cause, repair_rule)).encode("utf-8")
        lesson_id = "lesson-" + hashlib.sha256(material).hexdigest()[:20]
        return OperationalLesson(
            lesson_id=lesson_id,
            trigger_signature=trigger_signature,
            expected_behavior=expected_behavior,
            observed_failure=observed_failure,
            root_cause=root_cause,
            repair_rule=repair_rule,
            regression_test_id=regression_test_id,
            applicability_terms=[str(item) for item in applicability_terms if str(item).strip()][:24],
            confidence=max(0.0, min(1.0, float(confidence))),
            verified=bool(verified),
        )

    def add(self, lesson: OperationalLesson) -> None:
        self._lessons[lesson.lesson_id] = lesson

    @classmethod
    def from_json_file(cls, path: Path | str) -> "OperationalLearningMemory":
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return cls()
        rows = payload.get("lessons") if isinstance(payload, dict) else None
        lessons: list[OperationalLesson] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                required = ("trigger_signature", "expected_behavior", "observed_failure", "root_cause", "repair_rule")
                if not all(str(row.get(name) or "").strip() for name in required):
                    continue
                lessons.append(
                    cls.make_lesson(
                        trigger_signature=str(row["trigger_signature"]),
                        expected_behavior=str(row["expected_behavior"]),
                        observed_failure=str(row["observed_failure"]),
                        root_cause=str(row["root_cause"]),
                        repair_rule=str(row["repair_rule"]),
                        regression_test_id=str(row.get("regression_test_id") or "") or None,
                        applicability_terms=[str(item) for item in row.get("applicability_terms", []) if str(item).strip()],
                        confidence=float(row.get("confidence") or 0.8),
                        verified=bool(row.get("verified")),
                    )
                )
        return cls(lessons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "lesson_count": len(self._lessons),
            "verified_count": sum(1 for item in self._lessons.values() if item.verified),
            "lessons": [item.to_dict() for item in sorted(self._lessons.values(), key=lambda item: item.lesson_id)],
            "truth_boundary": (
                "Operational lessons are verified anti-regression guidance; they cannot modify source code autonomously."
            ),
        }


    def relevant(self, text: str, *, limit: int = 5, verified_only: bool = True) -> list[OperationalLesson]:
        folded = self._fold(text)
        scored: list[tuple[float, OperationalLesson]] = []
        for lesson in self._lessons.values():
            if verified_only and not lesson.verified:
                continue
            terms = [self._fold(item) for item in lesson.applicability_terms if self._fold(item)]
            overlap = sum(1 for term in terms if term in folded)
            trigger = self._fold(lesson.trigger_signature)
            if trigger and trigger in folded:
                overlap += 2
            if overlap <= 0:
                continue
            score = min(1.0, 0.25 * overlap + 0.5 * lesson.confidence)
            scored.append((score, lesson))
        scored.sort(key=lambda item: (-item[0], item[1].lesson_id))
        return [lesson for _, lesson in scored[: max(0, int(limit))]]
