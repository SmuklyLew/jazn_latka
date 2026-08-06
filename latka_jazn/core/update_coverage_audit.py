from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version


SCHEMA_VERSION = schema_version("update_coverage_audit")


@dataclass(slots=True)
class CoverageItem:
    requirement_id: str
    description: str
    covered: bool
    present_paths: list[str] = field(default_factory=list)
    missing_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UpdateCoverageAuditResult:
    ok: bool
    runtime_version: str
    covered_count: int
    missing_count: int
    items: list[CoverageItem]
    truth_boundary: str
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["items"] = [item.to_dict() for item in self.items]
        return payload


class UpdateCoverageAuditor:
    RESOURCE = Path("latka_jazn/resources/update_coverage_contract.json")

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def audit(self) -> UpdateCoverageAuditResult:
        source = json.loads((self.root / self.RESOURCE).read_text(encoding="utf-8"))
        items: list[CoverageItem] = []
        for spec in source.get("requirements", []):
            paths = [str(item) for item in spec.get("evidence_paths", [])]
            present = [path for path in paths if (self.root / path).is_file()]
            missing = [path for path in paths if path not in present]
            items.append(CoverageItem(
                requirement_id=str(spec.get("id") or "unknown"),
                description=str(spec.get("description") or ""),
                covered=not missing,
                present_paths=present,
                missing_paths=missing,
            ))
        missing_count = sum(1 for item in items if not item.covered)
        return UpdateCoverageAuditResult(
            ok=missing_count == 0,
            runtime_version=PACKAGE_VERSION_FULL,
            covered_count=len(items) - missing_count,
            missing_count=missing_count,
            items=items,
            truth_boundary=(
                "Audyt potwierdza obecność zadeklarowanych elementów i ich testów. "
                "Nie zastępuje wyników CI, przeglądu kodu ani wykonania runtime."
            ),
        )
