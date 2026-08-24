from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping
import re

from latka_jazn.config import JaznConfig
from latka_jazn.memory.rest_wake_report import load_latest_rest_wake_report
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("epistemic_evidence")
_SHA256 = re.compile(r"[0-9a-f]{64}")


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
    model_inference_ids: tuple[str, ...] = ()
    hypothesis_ids: tuple[str, ...] = ()
    synthetic_dream_ids: tuple[str, ...] = ()
    fiction_ids: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Evidence snapshots contain only bounded machine-observable identifiers and verified report metadata. "
        "Model output, confidence, daemon presence and synthetic dream text are never evidence for their own claims."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EpistemicEvidenceCollector:
    """Collect evidence classes without interpreting model-generated prose."""

    def __init__(self, config: JaznConfig | None = None) -> None:
        self.config = config or JaznConfig()

    @staticmethod
    def _ids(value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple, set)):
            return ()
        out: list[str] = []
        for raw in value:
            item = str(raw or "").strip()[:160]
            if item and item not in out:
                out.append(item)
            if len(out) >= 32:
                break
        return tuple(out)

    @staticmethod
    def _reported_count(value: Any) -> int:
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
        generated_evidence: Mapping[str, Any] | None = None,
    ) -> EpistemicEvidenceSnapshot:
        runtime = dict(runtime_evidence or {})
        memory = dict(memory_evidence or {})
        external = dict(external_evidence or {})
        generated = dict(generated_evidence or {})
        issues: list[str] = []

        rest = load_latest_rest_wake_report(self.config.rest_cycle_db_path)
        continuity = str(rest.get("rest_continuity_status") or "rest_none")
        report_sha = str(rest.get("report_sha256") or "").strip().lower()
        report_id = str(rest.get("report_id") or "").strip()[:160]
        rest_verified = continuity == "rest_verified" and bool(_SHA256.fullmatch(report_sha)) and bool(report_id)
        if continuity == "rest_integrity_failed":
            issues.append(str(rest.get("reason") or "rest_integrity_failed"))
        elif continuity == "rest_verified" and not rest_verified:
            issues.append("verified_rest_report_missing_identity_or_hash")
            continuity = "rest_integrity_failed"

        scene_ids = self._ids(rest.get("dream_scene_ids") or rest.get("scene_hashes")) if rest_verified else ()
        try:
            cycle_count = max(0, int(rest.get("cycle_count") or 0)) if rest_verified else 0
            scene_count = max(0, int(rest.get("dream_scene_count") or 0)) if rest_verified else 0
        except (TypeError, ValueError):
            cycle_count = 0
            scene_count = 0
            issues.append("verified_rest_report_count_invalid")

        background_ids = self._ids(runtime.get("background_event_ids"))
        reported_background_count = self._reported_count(runtime.get("background_event_count"))
        if reported_background_count and reported_background_count != len(background_ids):
            issues.append("background_event_count_not_identifier_backed")

        memory_ids = self._ids(memory.get("memory_source_ids") or memory.get("source_ids"))
        reported_memory_count = self._reported_count(memory.get("memory_evidence_count"))
        if reported_memory_count and reported_memory_count != len(memory_ids):
            issues.append("memory_evidence_count_not_identifier_backed")

        external_ids = self._ids(external.get("external_source_ids") or external.get("source_ids"))
        reported_external_count = self._reported_count(external.get("external_source_count"))
        if reported_external_count and reported_external_count != len(external_ids):
            issues.append("external_source_count_not_identifier_backed")

        return EpistemicEvidenceSnapshot(
            rest_continuity_status=continuity,
            rest_cycle_count=cycle_count,
            dream_scene_count=scene_count,
            dream_scene_ids=scene_ids,
            rest_report_id=(report_id or None) if rest_verified else None,
            rest_report_sha256=(report_sha or None) if rest_verified else None,
            daemon_verified=bool(runtime.get("daemon_verified", False)),
            background_event_count=len(background_ids),
            background_event_ids=background_ids,
            memory_evidence_count=len(memory_ids),
            memory_source_ids=memory_ids,
            external_source_count=len(external_ids),
            external_source_ids=external_ids,
            model_inference_ids=self._ids(generated.get("model_inference_ids")),
            hypothesis_ids=self._ids(generated.get("hypothesis_ids")),
            synthetic_dream_ids=self._ids(generated.get("synthetic_dream_ids")),
            fiction_ids=self._ids(generated.get("fiction_ids")),
            issues=tuple(issues),
        )


def collect_epistemic_evidence(
    *,
    config: JaznConfig | None = None,
    runtime_evidence: Mapping[str, Any] | None = None,
    memory_evidence: Mapping[str, Any] | None = None,
    external_evidence: Mapping[str, Any] | None = None,
    generated_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return EpistemicEvidenceCollector(config).collect(
        runtime_evidence=runtime_evidence,
        memory_evidence=memory_evidence,
        external_evidence=external_evidence,
        generated_evidence=generated_evidence,
    ).to_dict()
