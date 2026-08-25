from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping
import hashlib
import json
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
    external_tool_action_count: int = 0
    external_tool_action_ids: tuple[str, ...] = ()
    external_tool_actions: tuple[str, ...] = ()
    model_inference_ids: tuple[str, ...] = ()
    hypothesis_ids: tuple[str, ...] = ()
    synthetic_dream_ids: tuple[str, ...] = ()
    fiction_ids: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Evidence snapshots contain only bounded machine-observable identifiers, verified report metadata, and "
        "bounded host-attested external-tool action descriptors. Host attestations prove what the authenticated host "
        "declared for the turn; they do not make the local runtime the executor of that tool. Model output, confidence, "
        "daemon presence and synthetic dream text are never evidence for their own claims."
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
        external_tool_action_ids = self._ids(external.get("external_tool_action_ids"))
        external_tool_actions = self._ids(external.get("external_tool_actions"))
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
            external_tool_action_count=len(external_tool_action_ids),
            external_tool_action_ids=external_tool_action_ids,
            external_tool_actions=external_tool_actions,
            model_inference_ids=self._ids(generated.get("model_inference_ids")),
            hypothesis_ids=self._ids(generated.get("hypothesis_ids")),
            synthetic_dream_ids=self._ids(generated.get("synthetic_dream_ids")),
            fiction_ids=self._ids(generated.get("fiction_ids")),
            issues=tuple(issues),
        )


def host_tool_attestations_to_external_evidence(
    attestations: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Project validated host tool attestations into bounded epistemic evidence.

    The phase-2 candidate guard validates the allowlist, operation syntax, and source
    locators first. This projection intentionally stores only action descriptors,
    stable hashes, and bounded source identifiers. It does not claim that the local
    runtime executed GitHub or web.run itself.
    """

    source_ids: list[str] = []
    action_ids: list[str] = []
    actions: list[str] = []
    for raw in attestations or ():
        if not isinstance(raw, Mapping):
            continue
        tool = str(raw.get("tool") or "").strip()[:64]
        operation = str(raw.get("operation") or "").strip().lower()[:64]
        if not tool or not operation:
            continue
        refs = [str(item).strip()[:128] for item in raw.get("source_refs") or [] if str(item).strip()]
        urls = [str(item).strip()[:2048] for item in raw.get("source_urls") or [] if str(item).strip()]
        descriptor = f"{tool}:{operation}"[:160]
        if descriptor not in actions:
            actions.append(descriptor)
        canonical = json.dumps(
            {"tool": tool, "operation": operation, "source_refs": refs[:16], "source_urls": urls[:16]},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        action_id = f"host_tool_action:{digest}"
        if action_id not in action_ids:
            action_ids.append(action_id)
        for ref in refs[:16]:
            if ref not in source_ids:
                source_ids.append(ref)
        for url in urls[:16]:
            url_id = f"url_sha256:{hashlib.sha256(url.encode('utf-8')).hexdigest()}"
            if url_id not in source_ids:
                source_ids.append(url_id)
        if len(action_ids) >= 8:
            break
    return {
        "external_source_count": len(source_ids[:32]),
        "external_source_ids": source_ids[:32],
        "external_tool_action_count": len(action_ids[:8]),
        "external_tool_action_ids": action_ids[:8],
        "external_tool_actions": actions[:8],
        "host_attested": bool(action_ids),
        "runtime_independently_verified_execution": False,
    }


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
