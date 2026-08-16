from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Mapping
import re

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("epistemic_claim_guard")


class EpistemicClaimKind(StrEnum):
    DREAM_ACTIVITY = "dream_activity"
    BACKGROUND_ACTIVITY = "background_activity"


class EpistemicClaimStatus(StrEnum):
    SUPPORTED = "supported"
    NEGATED = "negated"
    UNSUPPORTED = "unsupported"


@dataclass(slots=True, frozen=True)
class EpistemicClaimAssessment:
    kind: EpistemicClaimKind
    status: EpistemicClaimStatus
    matched_text: str
    required_evidence: tuple[str, ...]
    evidence_snapshot: dict[str, Any]
    reason: str
    schema_version: str = SCHEMA_VERSION

    @property
    def blocks_visible_reply(self) -> bool:
        return self.status is EpistemicClaimStatus.UNSUPPORTED

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["status"] = self.status.value
        data["blocks_visible_reply"] = self.blocks_visible_reply
        return data


class EpistemicClaimViolation(ValueError):
    pass


class EpistemicClaimGuard:
    """Fail-closed guard for strong runtime self-claims.

    This is intentionally narrow. It does not pretend to fact-check arbitrary prose.
    It protects claims that are especially easy for a language model to invent:
    claiming that a dream happened or that autonomous background work occurred.

    Positive claims require structured runtime evidence supplied by the caller.
    Negative/uncertain statements remain allowed. Synthetic dream content never
    counts as evidence that a real rest/dream event occurred.
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

    def assess(
        self,
        text: str,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> list[EpistemicClaimAssessment]:
        body = str(text or "")
        supplied = dict(evidence or {})
        assessments: list[EpistemicClaimAssessment] = []

        dream_positive = self._first_match(self._DREAM_POSITIVE, body)
        dream_negative = self._first_match(self._DREAM_NEGATIVE, body)
        if dream_negative:
            assessments.append(
                EpistemicClaimAssessment(
                    kind=EpistemicClaimKind.DREAM_ACTIVITY,
                    status=EpistemicClaimStatus.NEGATED,
                    matched_text=dream_negative,
                    required_evidence=(),
                    evidence_snapshot={},
                    reason="negative_or_uncertain_dream_statement",
                )
            )
        elif dream_positive:
            cycle_count = self._int_evidence(supplied, "rest_cycle_count")
            scene_count = self._int_evidence(supplied, "dream_scene_count")
            scene_ids = tuple(str(value) for value in (supplied.get("dream_scene_ids") or ()))
            supported = cycle_count > 0 and (scene_count > 0 or bool(scene_ids))
            assessments.append(
                EpistemicClaimAssessment(
                    kind=EpistemicClaimKind.DREAM_ACTIVITY,
                    status=(EpistemicClaimStatus.SUPPORTED if supported else EpistemicClaimStatus.UNSUPPORTED),
                    matched_text=dream_positive,
                    required_evidence=("rest_cycle_count>0", "dream_scene_count>0|dream_scene_ids"),
                    evidence_snapshot={
                        "rest_cycle_count": cycle_count,
                        "dream_scene_count": scene_count,
                        "dream_scene_ids": list(scene_ids),
                    },
                    reason=("verified_rest_dream_event" if supported else "missing_verified_rest_dream_event"),
                )
            )

        background_positive = self._first_match(self._BACKGROUND_POSITIVE, body)
        background_negative = self._first_match(self._BACKGROUND_NEGATIVE, body)
        if background_negative:
            assessments.append(
                EpistemicClaimAssessment(
                    kind=EpistemicClaimKind.BACKGROUND_ACTIVITY,
                    status=EpistemicClaimStatus.NEGATED,
                    matched_text=background_negative,
                    required_evidence=(),
                    evidence_snapshot={},
                    reason="negative_or_uncertain_background_statement",
                )
            )
        elif background_positive:
            daemon_verified = bool(supplied.get("daemon_verified", False))
            event_count = self._int_evidence(supplied, "background_event_count")
            supported = daemon_verified and event_count > 0
            assessments.append(
                EpistemicClaimAssessment(
                    kind=EpistemicClaimKind.BACKGROUND_ACTIVITY,
                    status=(EpistemicClaimStatus.SUPPORTED if supported else EpistemicClaimStatus.UNSUPPORTED),
                    matched_text=background_positive,
                    required_evidence=("daemon_verified=true", "background_event_count>0"),
                    evidence_snapshot={
                        "daemon_verified": daemon_verified,
                        "background_event_count": event_count,
                    },
                    reason=("verified_background_events" if supported else "missing_verified_background_events"),
                )
            )

        return assessments

    def enforce(
        self,
        text: str,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> list[EpistemicClaimAssessment]:
        assessments = self.assess(text, evidence=evidence)
        blocked = [item for item in assessments if item.blocks_visible_reply]
        if blocked:
            details = ",".join(f"{item.kind.value}:{item.reason}" for item in blocked)
            raise EpistemicClaimViolation(f"unsupported epistemic self-claim: {details}")
        return assessments
