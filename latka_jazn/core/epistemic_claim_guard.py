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
    RUNTIME_ACTION = "runtime_action"
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
    """Fail closed for deterministic strong self/runtime claims."""

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
    _RUNTIME_ACTION_POSITIVE = (
        re.compile(r"\b(?:uruchomiłam|wdrożyłam|zaktualizowałam)\b", re.IGNORECASE),
        re.compile(r"\b(?:zapisałam|zmieniłam)\s+(?:plik|kod|bazę|baze|pamięć|pamiec)\b", re.IGNORECASE),
        re.compile(r"\bwykonałam\s+(?:test|komendę|polecenie|audyt)\b", re.IGNORECASE),
    )

    @staticmethod
    def _first_match(patterns: tuple[re.Pattern[str], ...], text: str) -> str | None:
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def _ids(evidence: Mapping[str, Any], key: str) -> tuple[str, ...]:
        value = evidence.get(key)
        if not isinstance(value, (list, tuple, set)):
            return ()
        return tuple(str(item)[:160] for item in value if str(item).strip())[:32]

    def assess(self, text: str, *, evidence: Mapping[str, Any] | None = None) -> list[EpistemicClaimAssessment]:
        body = str(text or "")
        supplied = dict(evidence or {})
        assessments: list[EpistemicClaimAssessment] = []

        dream_positive = self._first_match(self._DREAM_POSITIVE, body)
        dream_negative = self._first_match(self._DREAM_NEGATIVE, body)
        if dream_negative:
            assessments.append(EpistemicClaimAssessment(
                EpistemicClaimKind.DREAM_ACTIVITY,
                EpistemicClaimStatus.NEGATED,
                dream_negative,
                (),
                {},
                "negative_or_uncertain_dream_statement",
            ))
        elif dream_positive:
            continuity = str(supplied.get("rest_continuity_status") or "rest_none")
            scene_ids = self._ids(supplied, "dream_scene_ids")
            report_sha = str(supplied.get("rest_report_sha256") or "")
            report_id = str(supplied.get("rest_report_id") or "")
            supported = continuity == "rest_verified" and bool(scene_ids) and len(report_sha) == 64 and bool(report_id)
            assessments.append(EpistemicClaimAssessment(
                EpistemicClaimKind.DREAM_ACTIVITY,
                EpistemicClaimStatus.SUPPORTED if supported else EpistemicClaimStatus.UNSUPPORTED,
                dream_positive,
                ("verified_rest_report", "dream_scene_ids", "rest_report_sha256"),
                {
                    "rest_continuity_status": continuity,
                    "dream_scene_ids": list(scene_ids),
                    "rest_report_id": report_id or None,
                    "rest_report_sha256": report_sha or None,
                },
                "verified_rest_dream_event" if supported else "missing_verified_rest_dream_event",
                EpistemicSourceKind.VERIFIED_REST_REPORT if supported else EpistemicSourceKind.UNKNOWN,
                tuple(value for value in (report_id, report_sha, *scene_ids) if value),
            ))

        background_positive = self._first_match(self._BACKGROUND_POSITIVE, body)
        background_negative = self._first_match(self._BACKGROUND_NEGATIVE, body)
        if background_negative:
            assessments.append(EpistemicClaimAssessment(
                EpistemicClaimKind.BACKGROUND_ACTIVITY,
                EpistemicClaimStatus.NEGATED,
                background_negative,
                (),
                {},
                "negative_or_uncertain_background_statement",
            ))
        elif background_positive:
            event_ids = self._ids(supplied, "background_event_ids")
            supported = bool(supplied.get("daemon_verified")) and bool(event_ids)
            assessments.append(EpistemicClaimAssessment(
                EpistemicClaimKind.BACKGROUND_ACTIVITY,
                EpistemicClaimStatus.SUPPORTED if supported else EpistemicClaimStatus.UNSUPPORTED,
                background_positive,
                ("daemon_verified=true", "background_event_ids"),
                {"daemon_verified": bool(supplied.get("daemon_verified")), "background_event_ids": list(event_ids)},
                "verified_background_events" if supported else "missing_verified_background_events",
                EpistemicSourceKind.RUNTIME_EVENT if supported else EpistemicSourceKind.UNKNOWN,
                event_ids,
            ))

        runtime_action = self._first_match(self._RUNTIME_ACTION_POSITIVE, body)
        if runtime_action and not background_positive:
            event_ids = self._ids(supplied, "runtime_action_event_ids")
            supported = bool(event_ids)
            assessments.append(EpistemicClaimAssessment(
                EpistemicClaimKind.RUNTIME_ACTION,
                EpistemicClaimStatus.SUPPORTED if supported else EpistemicClaimStatus.UNSUPPORTED,
                runtime_action,
                ("runtime_action_event_ids",),
                {"runtime_action_event_ids": list(event_ids)},
                "verified_runtime_action_events" if supported else "missing_runtime_action_events",
                EpistemicSourceKind.RUNTIME_EVENT if supported else EpistemicSourceKind.UNKNOWN,
                event_ids,
            ))
        return assessments

    def assess_structured(self, claims: Iterable[StructuredEpistemicClaim]) -> list[EpistemicClaimAssessment]:
        factual_sources = {
            EpistemicSourceKind.CURRENT_USER_MESSAGE,
            EpistemicSourceKind.USER_CONFIRMED_MEMORY,
            EpistemicSourceKind.SOURCE_RECORDED_MEMORY,
            EpistemicSourceKind.CANONICAL_MEMORY,
            EpistemicSourceKind.TOOL_OR_WEB_SOURCE,
            EpistemicSourceKind.RUNTIME_EVENT,
            EpistemicSourceKind.VERIFIED_REST_REPORT,
        }
        out: list[EpistemicClaimAssessment] = []
        for claim in claims:
            source_ids = tuple(str(item)[:160] for item in claim.source_ids if str(item).strip())[:32]
            if claim.contradicted:
                status, reason = EpistemicClaimStatus.CONTRADICTED, "structured_claim_marked_contradicted"
            elif claim.source_kind is EpistemicSourceKind.MODEL_INFERENCE:
                if claim.kind is EpistemicClaimKind.INFERENCE:
                    status, reason = EpistemicClaimStatus.INFERRED, "model_inference_not_promoted_to_fact"
                else:
                    status, reason = EpistemicClaimStatus.UNSUPPORTED, "model_inference_cannot_support_factual_claim"
            elif claim.source_kind is EpistemicSourceKind.HYPOTHESIS:
                if claim.kind is EpistemicClaimKind.HYPOTHESIS:
                    status, reason = EpistemicClaimStatus.HYPOTHETICAL, "hypothesis_not_promoted_to_fact"
                else:
                    status, reason = EpistemicClaimStatus.UNSUPPORTED, "hypothesis_cannot_support_factual_claim"
            elif claim.source_kind in {EpistemicSourceKind.SYNTHETIC_DREAM, EpistemicSourceKind.FICTION}:
                if claim.kind in {EpistemicClaimKind.DREAM_ARTIFACT, EpistemicClaimKind.FICTION}:
                    status, reason = EpistemicClaimStatus.SYNTHETIC, "synthetic_content_not_factual_evidence"
                else:
                    status, reason = EpistemicClaimStatus.UNSUPPORTED, "synthetic_content_cannot_support_factual_claim"
            elif claim.source_kind in factual_sources and source_ids:
                status, reason = EpistemicClaimStatus.SUPPORTED, "structured_source_evidence_present"
            else:
                status, reason = EpistemicClaimStatus.UNSUPPORTED, "structured_claim_missing_source_evidence"
            out.append(EpistemicClaimAssessment(
                claim.kind,
                status,
                claim.text,
                ("explicit_source_kind", "source_ids") if status is EpistemicClaimStatus.UNSUPPORTED else (),
                {"confidence": claim.confidence},
                reason,
                claim.source_kind,
                source_ids,
            ))
        return out

    @staticmethod
    def _enforce(assessments: list[EpistemicClaimAssessment], *, structured: bool) -> list[EpistemicClaimAssessment]:
        blocked = [item for item in assessments if item.blocks_visible_reply]
        if blocked:
            details = ",".join(f"{item.kind.value}:{item.reason}" for item in blocked)
            prefix = "unsupported structured epistemic claim" if structured else "unsupported epistemic self-claim"
            raise EpistemicClaimViolation(f"{prefix}: {details}")
        return assessments

    def enforce(self, text: str, *, evidence: Mapping[str, Any] | None = None) -> list[EpistemicClaimAssessment]:
        return self._enforce(self.assess(text, evidence=evidence), structured=False)

    def enforce_structured(self, claims: Iterable[StructuredEpistemicClaim]) -> list[EpistemicClaimAssessment]:
        return self._enforce(self.assess_structured(claims), structured=True)
