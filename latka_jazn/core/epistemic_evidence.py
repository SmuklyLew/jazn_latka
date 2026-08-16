from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping
import json

from latka_jazn.config import JaznConfig
from latka_jazn.memory.rest_wake_report import load_latest_rest_wake_report
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("epistemic_evidence")


@dataclass(slots=True, frozen=True)
class EpistemicEvidenceSnapshot:
    rest_continuity_status: str = "rest_none"
    rest_cycle_count: int = 0
    dream_scene_count: int = 0
    dream_scene_ids: tuple[str, ...] = ()
    rest_report_id: str | None = None
    rest_report_sha256: str | None = None
    daemon_verified: bool = False
    background_event_count: int = 0
    background_event_ids: tuple[str, ...] = ()
    memory_evidence_count: int = 0
    memory_source_ids: tuple[str, ...] = ()
    external_source_count: int = 0
    external_source_ids: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Evidence snapshots contain only machine-observable runtime/source metadata. "
        "Missing evidence remains missing; the collector never invents activity, memories, sources, or confidence."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EpistemicEvidenceCollector:
    """Collect bounded evidence for epistemic claim checks without model inference.

    The collector intentionally performs no semantic interpretation. Rest evidence
    comes from the hash-verified wake report. Other evidence must be supplied by
    the caller from already-authorized runtime/tool/memory contracts.
    """

    def __init__(self, config: JaznConfig | None = None) -> None:
        self.config = config or JaznConfig()

    @staticmethod
    def _ids(value: Any) -> tuple[str, ...]:
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value if str(item).strip())
        return ()

    @staticmethod
    def _count(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def collect(
        self,
        *,
        runtime_evidence: Mapping[str, Any] | None = None,
        memory_evidence: Mapping[str, Any] | None = None,
        external_evidence: Mapping[str, Any] | None = None,
    ) -> EpistemicEvidenceSnapshot:
        runtime = dict(runtime_evidence or {})
        memory = dict(memory_evidence or {})
        external = dict(external_evidence or {})
        issues: list[str] = []

        rest = load_latest_rest_wake_report(self.config.rest_cycle_db_path)
        continuity = str(rest.get("rest_continuity_status") or "rest_none")
        cycle_count = self._count(rest.get("cycle_count"))
        scene_count = self._count(rest.get("dream_scene_count"))
        scene_ids = self._ids(rest.get("dream_scene_ids"))
        if not scene_ids:
            # Older reports expose scene hashes rather than ids. Hashes are valid
            # evidence that a persisted scene exists, but are never treated as content.
            scene_ids = self._ids(rest.get("scene_hashes"))
        report_sha = str(rest.get("report_sha256") or "").strip() or None
        report_id = str(rest.get("report_id") or "").strip() or None
        if continuity == "rest_integrity_failed":
            issues.append(str(rest.get("reason") or "rest_integrity_failed"))
            cycle_count = 0
            scene_count = 0
            scene_ids = ()
            report_sha = None
            report_id = None

        background_ids = self._ids(runtime.get("background_event_ids"))
        background_count = max(self._count(runtime.get("background_event_count")), len(background_ids))
        daemon_verified = bool(runtime.get("daemon_verified", False))

        memory_ids = self._ids(memory.get("memory_source_ids") or memory.get("source_ids"))
        memory_count = max(self._count(memory.get("memory_evidence_count")), len(memory_ids))

        external_ids = self._ids(external.get("external_source_ids") or external.get("source_ids"))
        external_count = max(self._count(external.get("external_source_count")), len(external_ids))

        return EpistemicEvidenceSnapshot(
            rest_continuity_status=continuity,
            rest_cycle_count=cycle_count,
            dream_scene_count=scene_count,
            dream_scene_ids=scene_ids,
            rest_report_id=report_id,
            rest_report_sha256=report_sha,
            daemon_verified=daemon_verified,
            background_event_count=background_count,
            background_event_ids=background_ids,
            memory_evidence_count=memory_count,
            memory_source_ids=memory_ids,
            external_source_count=external_count,
            external_source_ids=external_ids,
            issues=tuple(issues),
        )


def collect_epistemic_evidence(
    *,
    config: JaznConfig | None = None,
    runtime_evidence: Mapping[str, Any] | None = None,
    memory_evidence: Mapping[str, Any] | None = None,
    external_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return EpistemicEvidenceCollector(config).collect(
        runtime_evidence=runtime_evidence,
        memory_evidence=memory_evidence,
        external_evidence=external_evidence,
    ).to_dict()
