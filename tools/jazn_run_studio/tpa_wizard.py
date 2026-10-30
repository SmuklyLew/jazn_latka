"""Read-only sequential operator wizard cursor over durable TPA observations.

The wizard never grants PASS. Its resume point is reconstructed from verified
per-case evidence in RunStore, not from an unsafely cached UI selection.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from .tpa_catalog import LIVE_CASES


def pending_cases(rows: Iterable[dict], state: Mapping[str, dict], *,
                  include_live: bool = False) -> tuple[str, ...]:
    pending: list[str] = []
    for case in rows:
        case_id = case["id"]
        if not include_live and case_id in LIVE_CASES:
            continue
        full = state.get(case_id, {}).get("full")
        if not isinstance(full, dict) or full.get("status") != "PASS" or full.get("source_relation") != "same":
            pending.append(case_id)
    return tuple(pending)


def wizard_counts(rows: Iterable[dict], state: Mapping[str, dict], *,
                  include_live: bool = False) -> tuple[int, int, int]:
    all_rows = tuple(rows)
    eligible = [row for row in all_rows if include_live or row["id"] not in LIVE_CASES]
    pending = pending_cases(eligible, state, include_live=True)
    deferred = 0 if include_live else sum(row["id"] in LIVE_CASES for row in all_rows)
    return len(eligible) - len(pending), len(eligible), deferred
