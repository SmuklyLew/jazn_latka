from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping
import re

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("epistemic_claim_guard")


class EpistemicClaimKind(StrEnum):
    DREAM_ACTIVITY = "dream_activity"
    BACKGROUND_ACTIVITY = "background_activity"
    MEMORY_RECALL = "memory_recall"
    EXTERNAL_FACT = "external_fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    DREAM_ARTIFACT = "dream_artifact"
    FICTION = "fiction"


class EpistemicSourceKind(StrEnum):
    CURRENT_USER_MESSAGE = "current_user_message"
    USER_CONFIRMED_MEMORY = "user_confirmed_memory"
    SOURCE_RECORDED_MEMORY = "source_recorded_memory"
    CANONICAL_MEMORY = "canonical_memory"
    TOOL_OR_WEB_SOURCE = "tool_or_web_source"
    RUNTIME_EVENT = "runtime_event"
    VERIFIED_REST_REPORT = "verified_rest_report"
    MODEL_INFERENCE = "model_inference"
    HYPOTHESIS = "hypothesis"
    SYNTHETIC_DREAM = "synthetic_dream"
    FICTION = "fiction"
    UNKNOWN = "unknown"


class EpistemicClaimStatus(StrEnum):
    SUPPORTED = "supported"
    NEGATED = "negated"
    INFERRED = "inferred"
    HYPOTHETICAL = "hypothetical"
    SYNTHETIC = "synthetic"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


@dataclass(slots=True, frozen=True)
class StructuredEpistemicClaim:
    kind: EpistemicClaimKind
    text: str
    source_kind: EpistemicSourceKind
    source_ids: tuple[str, ...] = ()
    confidence: float | None = None
    contradicted: bool = False


@dataclass(slots=True, frozen=True)
class EpistemicClaimAssessment:
    kind: EpistemicClaimKind
    status: EpistemicClaimStatus
    matched_text: str
    required_evidence: tuple[str, ...]
    evidence_snapshot: dict[str, Any]
    reason: str
    source_kind: EpistemicSourceKind = EpistemicSourceKind.UNKNOWN
    source_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    @property
    def blocks_visible_reply(self) -> bool:
        return self.status in {EpistemicClaimStatus.UNSUPPORTED, EpistemicClaimStatus.CONTRADICTED}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["status"] = self.status.value
        data["source_kind"] = self.source_kind.value
        data["blocks_visible_reply"] = self.blocks_visible_reply
        return data


class EpistemicClaimViolation(ValueError):
    pass


class EpistemicClaimGuard:
    """Fail-closed guard for strong self-claims and structured factual claims.

    Raw-text enforcement intentionally protects only high-risk autobiographical
    self-claims that can be checked deterministically. Broader factual claims are
    accepted through ``assess_structured`` where the caller must provide source
    class and source identifiers. This avoids pretending regexes can fact-check
    arbitrary natural language.
    """

    _DREAM_POSITIVE = (
        re.compile(r"\bśniłam\b", re.IGNORECASE),
        re.compile(r"\bmiałam\s+(?:jakiś\s+)?sen\b", re.IGNORECASE),
        re.compile(r"\budało\s+mi\s+się\s+śnić\b", re.IGNORECASE),
        re.compile(r"\bi\s+dreamed\b", re.IGNORECASE),
    )
    _DREAM_NEGATIVE = (
        re.compile(r"\bnie\s+śniłam\b", re.IGNORECASE),
        re.compile(r"\bnie\s+udało\s+mi\s+się\s+śnić\b", re.IGNORECASE),
        re.compile(r"\bnie\s+mam\s+podstaw(?:y|)\s+.*\bśni", re.IGNORECASE),
        re.compile(r"\bi\s+did\s+not\s+dream\b", re.IGNORECASE),
    )
    _BACKGROUND_POSITIVE = (
        re.compile(r"\bpracowałam\s+w\s+tle\b", re.IGNORECASE),
        re.compile(r"\brobiłam\s+.*\bw\s+tle\b", re.IGNORECASE),
        re.compile(r"\bprzez\s+noc\s+pracowałam\b", re.IGNORECASE),
        re.compile(r"\bgdy\s+spałeś\s+.*\bpracowałam\b", re.IGNORECASE),
        re.compile(r"\bwhile\s+you\s+slept\s+.*\bi\s+worked\b", re.IGNORECASE),
    )
    _BACKGROUND_NEGATIVE = (
        re.compile(r"\bnie\s+pracowałam\s+w\s+tle\b", re.IGNORECASE),
        re.compile(r"\bnic\s+nie\s+robiłam\s+w\s+tle\b", re.IGNORECASE),
        re.compile(r"\bnie\s+mam\s+podstaw(?:y|)\s+.*\bpracy\s+w\s+tle\b", re.IGNORECASE),
        re.compile(r"\bi\s+did\s+not\s+work\s+in\s+the\s+background\b", re.IGNORECASE),
    )

    @staticmethod
    def _first_match(patterns: tuple[re.Pattern[str], ...], text: str) -> str | None:
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def _int_evidence(evidence: Mapping[str, Any], key: str) -> int:
        try:
            return max(0, int(evidence.get(key, 0) or 0))
        except (TypeError, ValueError):
            return 0

    def assess(self, text: str, *, evidence: Mapping[str, Any] | None = None) -> list[EpistemicClaimAssessment]:
        body = str(text or "")
        supplied = dict(evidence or {})
        assessments: list[EpistemicClaimAssessment] = []

        dream_positive = self._first_match(self._DREAM_POSITIVE, body)
        dream_negative = self._first_match(self._DREAM_NEGATIVE, body)
        if dream_negative:
            assessments.append(EpistemicClaimAssessment(
                kind=EpistemicClaimKind.DREAM_ACTIVITY,
                status=EpistemicClaimStatus.NEGATED,
                matched_text=dream_negative,
                required_evidence=(),
                evidence_snapshot={},
                reason="negative_or_uncertain_dream_statement",
            ))
        elif dream_positive:
            continuity = str(supplied.get("rest_continuity_status") or "rest_none")
            cycle_count = self._int_evidence(supplied, "rest_cycle_count")
            scene_count = self._int_evidence(supplied, "dream_scene_count")
            scene_ids = tuple(str(value) for value in (supplied.get("dream_scene_ids") or ()))
            report_sha = str(supplied.get("rest_report_sha256") or "").strip()
            supported = (
                continuity == "rest_verified"
                and cycle_count > 0
                and (scene_count > 0 or bool(scene_ids))
                and bool(report_sha)
            )
            assessments.append(EpistemicClaimAssessment(
                kind=EpistemicClaimKind.DREAM_ACTIVITY,
                status=EpistemicClaimStatus.SUPPORTED if supported else EpistemicClaimStatus.UNSUPPORTED,
                matched_text=dream_positive,
                required_evidence=(
                    "rest_continuity_status=rest_verified",
                    "rest_cycle_count>0",
                    "dream_scene_count>0|dream_scene_ids",
                    "rest_report_sha256",
                ),
                evidence_snapshot={
                    "rest_continuity_status": continuity,
                    "rest_cycle_count": cycle_count,
                    "dream_scene_count": scene_count,
                    "dream_scene_ids": list(scene_ids),
                    "rest_report_sha256": report_sha or None,
                },
                reason="verified_rest_dream_event" if supported else "missing_verified_rest_dream_event",
                source_kind=EpistemicSourceKind.VERIFIED_REST_REPORT if supported else EpistemicSourceKind.UNKNOWN,
                source_ids=tuple(value for value in (str(supplied.get("rest_report_id") or ""), report_sha) if value),
            ))

        background_positive = self._first_match(self._BACKGROUND_POSITIVE, body)
        background_negative = self._first_match(self._BACKGROUND_NEGATIVE, body)
        if background_negative:
            assessments.append(EpistemicClaimAssessment(
                kind=EpistemicClaimKind.BACKGROUND_ACTIVITY,
                status=EpistemicClaimStatus.NEGATED,
                matched_text=background_negative,
                required_evidence=(),
                evidence_snapshot={},
                reason="negative_or_uncertain_background_statement",
            ))
        elif background_positive:
            daemon_verified = bool(supplied.get("daemon_verified", False))
            event_count = self._int_evidence(supplied, "background_event_count")
            event_ids = tuple(str(value) for value in (supplied.get("background_event_ids") or ()))
            supported = daemon_verified and event_count > 0 and bool(event_ids)
            assessments.append(EpistemicClaimAssessment(
                kind=EpistemicClaimKind.BACKGROUND_ACTIVITY,
                status=EpistemicClaimStatus.SUPPORTED if supported else EpistemicClaimStatus.UNSUPPORTED,
                matched_text=background_positive,
                required_evidence=("daemon_verified=true", "background_event_count>0", "background_event_ids"),
                evidence_snapshot={
                    "daemon_verified": daemon_verified,
                    "background_event_count": event_count,
                    "background_event_ids": list(event_ids),
                },
                reason="verified_background_events" if supported else "missing_verified_background_events",
                source_kind=EpistemicSourceKind.RUNTIME_EVENT if supported else EpistemicSourceKind.UNKNOWN,
                source_ids=event_ids,
            ))
        return assessments

    def assess_structured(self, claims: Iterable[StructuredEpistemicClaim]) -> list[EpistemicClaimAssessment]:
        out: list[EpistemicClaimAssessment] = []
        factual_sources = {
            EpistemicSourceKind.CURRENT_USER_MESSAGE,
            EpistemicSourceKind.USER_CONFIRMED_MEMORY,
            EpistemicSourceKind.SOURCE_RECORDED_MEMORY,
            EpistemicSourceKind.CANONICAL_MEMORY,
            EpistemicSourceKind.TOOL_OR_WEB_SOURCE,
            EpistemicSourceKind.RUNTIME_EVENT,
            EpistemicSourceKind.VERIFIED_REST_REPORT,
        }
        for claim in claims:
            if claim.contradicted:
                status = EpistemicClaimStatus.CONTRADICTED
                reason = "structured_claim_marked_contradicted"
            elif claim.source_kind in {EpistemicSourceKind.MODEL_INFERENCE}:
                status = EpistemicClaimStatus.INFERRED
                reason = "model_inference_not_promoted_to_fact"
            elif claim.source_kind is EpistemicSourceKind.HYPOTHESIS:
                status = EpistemicClaimStatus.HYPOTHETICAL
                reason = "hypothesis_not_promoted_to_fact"
            elif claim.source_kind in {EpistemicSourceKind.SYNTHETIC_DREAM, EpistemicSourceKind.FICTION}:
                status = EpistemicClaimStatus.SYNTHETIC
                reason = "synthetic_content_not_factual_evidence"
            elif claim.source_kind in factual_sources and claim.source_ids:
                status = EpistemicClaimStatus.SUPPORTED
                reason = "structured_source_evidence_present"
            else:
                status = EpistemicClaimStatus.UNSUPPORTED
                reason = "structured_claim_missing_source_evidence"
            out.append(EpistemicClaimAssessment(
                kind=claim.kind,
                status=status,
                matched_text=claim.text,
                required_evidence=("explicit_source_kind", "source_ids") if status is EpistemicClaimStatus.UNSUPPORTED else (),
                evidence_snapshot={"confidence": claim.confidence},
                reason=reason,
                source_kind=claim.source_kind,
                source_ids=claim.source_ids,
            ))
        return out

    def enforce(self, text: str, *, evidence: Mapping[str, Any] | None = None) -> list[EpistemicClaimAssessment]:
        assessments = self.assess(text, evidence=evidence)
        blocked = [item for item in assessments if item.blocks_visible_reply]
        if blocked:
            details = ",".join(f"{item.kind.value}:{item.reason}" for item in blocked)
            raise EpistemicClaimViolation(f"unsupported epistemic self-claim: {details}")
        return assessments

    def enforce_structured(self, claims: Iterable[StructuredEpistemicClaim]) -> list[EpistemicClaimAssessment]:
        assessments = self.assess_structured(claims)
        blocked = [item for item in assessments if item.blocks_visible_reply]
        if blocked:
            details = ",".join(f"{item.kind.value}:{item.reason}" for item in blocked)
            raise EpistemicClaimViolation(f"unsupported structured epistemic claim: {details}")
        return assessments
