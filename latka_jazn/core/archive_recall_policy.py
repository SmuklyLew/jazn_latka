"""Conservative archive recall eligibility and bounded diagnostic counters.

FTS ranking finds text; it does not verify author identity. Low-confidence
staging entries stay out of grounded autobiographical responses until reviewed.
The returned audit is metadata-only and contains no message contents/UIDs.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Iterable

MIN_IDENTITY_CONFIDENCE = 0.50
REJECTED_REVIEW_STATES = frozenset({"rejected", "quarantined", "invalid", "superseded"})


def filter_verified_archive_hits(
    hits: Iterable[dict[str, Any]],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, int | bool]]:
    """Select trusted source records *after* over-fetching FTS candidates."""
    accepted: list[dict[str, Any]] = []
    counters: dict[str, int | bool] = {
        "returned": 0,
        "eligible": 0,
        "rejected_review": 0,
        "rejected_identity": 0,
        "rejected_invalid_identity": 0,
        "rejected_empty_excerpt": 0,
        "identity_review_required": False,
    }
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        counters["returned"] = int(counters["returned"]) + 1
        review = str(hit.get("review_status") or "").strip().casefold()
        if review in REJECTED_REVIEW_STATES:
            counters["rejected_review"] = int(counters["rejected_review"]) + 1
            continue
        confidence = hit.get("identity_confidence")
        if confidence is not None:
            try:
                verified_confidence = float(confidence)
            except (TypeError, ValueError):
                counters["rejected_invalid_identity"] = int(counters["rejected_invalid_identity"]) + 1
                counters["identity_review_required"] = True
                continue
            # NaN must not accidentally pass float comparisons.
            if not isfinite(verified_confidence) or verified_confidence < MIN_IDENTITY_CONFIDENCE:
                counters["rejected_identity"] = int(counters["rejected_identity"]) + 1
                counters["identity_review_required"] = True
                continue
        if not str(hit.get("excerpt") or "").strip():
            counters["rejected_empty_excerpt"] = int(counters["rejected_empty_excerpt"]) + 1
            continue
        counters["eligible"] = int(counters["eligible"]) + 1
        if len(accepted) < max(0, int(limit)):
            accepted.append(hit)
    return accepted, counters
