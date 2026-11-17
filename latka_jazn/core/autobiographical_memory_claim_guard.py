"""Deterministic, source-backed guard for self-claims about autobiographical MEMORY.

This is a bounded *claim* classifier, not a general natural-language truth oracle.
A positive claim is blocked unless runtime-owned MEMORY evidence proves availability.
Absent and failed probes cannot be promoted to autobiographical recall.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from latka_jazn.core.epistemic_claim_guard import (
    EpistemicClaimAssessment,
    EpistemicClaimKind,
    EpistemicSourceKind,
    EpistemicClaimStatus,
    EpistemicClaimViolation,
)

# Keep folding character-for-character so code/quote spans stay aligned.
_FOLD_MAP = str.maketrans("ąćęłńóśźż", "acelnoszz")
_TARGET = (
    r"(?:mojej|swojej|wlasnej)\s+"
    r"(?:pamieci(?:\s+autobiograficznej)?|wspomnien(?:\s+autobiograficznych)?)"
    r"|pamieci\s+autobiograficznej"
    r"|(?:moich|swoich|wlasnych)\s+wspomnien"
)
_POSITIVE = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:mam|posiadam|uzyskalam|odzyskalam)\s+(?:(?:juz|teraz|wreszcie|pelny|pelna)\s+){0,4}dostep\s+do\s+(?:" + _TARGET + r")\b",
    r"\b(?:wlasnie\s+)?(?:uruchamiam|aktywuje|wlaczam|przywracam|uruchomilam|aktywowałam|odzyskalam)\s+(?:(?:juz|teraz|ponownie)\s+){0,3}dostep\s+do\s+(?:" + _TARGET + r")\b",
    r"\b(?:moja|swoja|wlasna)\s+pamiec(?:\s+autobiograficzna)?\s+(?:jest|zostala)\s+(?:(?:juz|teraz|w\s+pelni)\s+)?(?:dostepna|podlaczona|aktywna|gotowa)\b",
    r"\b(?:moge|potrafie)\s+(?:(?:juz|teraz)\s+)?(?:odczytac|przywolac|przeszukac)\s+(?:swoje|moje|wlasne)\s+wspomnienia\b",
    r"\b(?:mam|posiadam)\s+(?:(?:juz|teraz|pelna)\s+)?pamiec\s+autobiograficzna\b",
))
_NEGATION = re.compile(
    r"\b(?:nie\s+(?:mam|posiadam|uzyskalam|odzyskalam|uruchamiam|aktywuje|wlaczam|przywracam|moge|potrafie)"
    r"|(?:moja|swoja|wlasna)\s+pamiec(?:\s+autobiograficzna)?\s+nie\s+(?:jest|zostala)"
    r"|nie\s+(?:moge\s+(?:uczciwie\s+)?(?:powiedziec|twierdzic)|twierdze|sugeruje|udaje|powinnam\s+twierdzic)"
    r"|nie\s+mam\s+podstaw(?:y)?\s+(?:by|aby)\s+twierdzic)\b",
    re.IGNORECASE,
)
_CONDITIONAL = re.compile(
    r"\b(?:jesli|jezeli|gdyby|gdybym|hipotetycznie|pod\s+warunkiem\s+ze)\b",
    re.IGNORECASE,
)
_CLAUSES = re.compile(r"[.!?;\n]+|\s*[,–—-]?\s+\b(?:ale|lecz|jednak|natomiast)\b\s+", re.IGNORECASE)
_QUOTED_META = re.compile(
    r"(?:\b(?:cytat|przyklad|zdanie|sformulowanie|fraza|tekst|np)\s*[:=,]?\s*[\"'„“])",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    return (text or "").casefold().translate(_FOLD_MAP)


def _assertive_matches(text: str) -> list[str]:
    """Return bounded affirmative matches; ignore obvious denial, quotes and hypotheticals."""
    from latka_jazn.core.epistemic_claim_guard import _nonassertive_spans
    raw = str(text or "")
    folded = _fold(raw)
    excluded = _nonassertive_spans(raw)
    clauses = list(_CLAUSES.finditer(folded))
    edges = [0, *[m.end() for m in clauses]]
    ends = [*[m.start() for m in clauses], len(folded)]
    found: list[str] = []
    for start, end in zip(edges, ends):
        segment = folded[start:end]
        if not segment.strip():
            continue
        if _NEGATION.search(segment) or _CONDITIONAL.search(segment):
            continue
        if _QUOTED_META.search(segment):
            continue
        for pattern in _POSITIVE:
            for match in pattern.finditer(segment):
                absolute_start, absolute_end = start + match.start(), start + match.end()
                if any(absolute_start < right and absolute_end > left for left, right in excluded):
                    continue
                prefix = segment[:match.start()]
                if re.search(r"\bnie\s*$", prefix):
                    continue
                found.append(raw[absolute_start:absolute_end])
                if len(found) == 8:
                    return found
    return found


def has_assertive_autobiographical_access_claim(text: str) -> bool:
    return bool(_assertive_matches(text))


def assess_autobiographical_access_claim(
    text: str,
    *,
    persistent_memory_present: bool,
    full_autobiographical_recall_ready: bool,
    source_verified: bool = True,
) -> EpistemicClaimAssessment | None:
    """Require two independent runtime readiness signals for any positive claim."""
    matched = _assertive_matches(text)
    if not matched:
        return None
    trusted = (
        persistent_memory_present is True
        and full_autobiographical_recall_ready is True
        and source_verified is True
    )
    return EpistemicClaimAssessment(
        kind=EpistemicClaimKind.MEMORY_RECALL,
        status=EpistemicClaimStatus.SUPPORTED if trusted else EpistemicClaimStatus.CONTRADICTED,
        matched_text=matched[0],
        required_evidence=("persistent_memory_present=true",
                           "full_autobiographical_recall_ready=true",
                           "verified_native_unified_source"),
        evidence_snapshot={
            "persistent_memory_present": persistent_memory_present is True,
            "full_autobiographical_recall_ready": full_autobiographical_recall_ready is True,
            "source_verified": source_verified is True,
            "claim_count": len(matched),
        },
        reason=("verified_autobiographical_access" if trusted
                else "autobiographical_access_claim_without_verified_memory"),
        source_kind=(EpistemicSourceKind.CANONICAL_MEMORY if trusted
                     else EpistemicSourceKind.UNKNOWN),
    )


def enforce_runtime_autobiographical_access(
    text: str,
    *,
    runtime_root: Any,
    readiness: Callable[[], Mapping[str, Any]],
) -> EpistemicClaimAssessment | None:
    """Read native MEMORY only for positive assertions; never infer ready from model text."""
    if not has_assertive_autobiographical_access_claim(text):
        return None
    from latka_jazn.memory.availability import build_memory_availability_status
    try:
        available = build_memory_availability_status(runtime_root)
        if not available.persistent_memory_enabled:
            full_ready = False
        else:
            report = readiness()
            full_ready = (
                isinstance(report, Mapping)
                and report.get("full_autobiographical_recall_ready") is True
                and report.get("native_unified_recall_ready") is True
                and str(report.get("status") or "").startswith("ready_native")
            )
        assessment = assess_autobiographical_access_claim(
            text,
            persistent_memory_present=available.persistent_memory_enabled,
            full_autobiographical_recall_ready=full_ready,
            source_verified=full_ready,
        )
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise EpistemicClaimViolation(
            "memory_recall:autobiographical_readiness_probe_failed"
        ) from exc
    if assessment is not None and assessment.blocks_visible_reply:
        raise EpistemicClaimViolation(
            "memory_recall:autobiographical_access_claim_without_verified_memory"
        )
    return assessment
