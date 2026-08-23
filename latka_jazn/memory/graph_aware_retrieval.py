from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata
from typing import Any, Generic, Iterable, TypeVar

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("graph_aware_retrieval")
T = TypeVar("T")
_VALID_MODES = frozenset({"shadow", "ab", "active"})


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return " ".join(
        re.findall(r"[a-z0-9]+", "".join(ch for ch in text if not unicodedata.combining(ch)))
    )


def _fingerprint(items: Iterable[Any]) -> str:
    identifiers = [
        str(getattr(item, "record_id", None) or getattr(item, "source_locator", None) or "")
        for item in items
    ]
    return hashlib.sha256("\n".join(identifiers).encode("utf-8")).hexdigest()


def _conversation_key(hit: Any) -> str:
    metadata = getattr(hit, "metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    for key in ("conversation_id", "source_conversation_id", "chat_id"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    locator = str(getattr(hit, "source_locator", None) or "").strip()
    return locator.split(":", 1)[0] if locator else "unknown"


@dataclass(slots=True, frozen=True)
class GraphRetrievalDecision(Generic[T]):
    selected: tuple[T, ...]
    candidate: tuple[T, ...]
    telemetry: dict[str, Any]


class GraphAwareRetrievalController:
    """Bounded deterministic reranker with FTS baseline and sanitized telemetry.

    The controller cannot write memory, create facts or approve promotion. The
    default ``shadow`` mode computes a candidate lane but always returns the FTS
    baseline. ``ab`` chooses a stable lane from the query hash; ``active`` must
    be enabled explicitly by the caller.
    """

    def __init__(self, *, max_candidates: int = 80, max_per_conversation: int = 2) -> None:
        self.max_candidates = max(8, min(160, int(max_candidates)))
        self.max_per_conversation = max(1, min(8, int(max_per_conversation)))

    def select(
        self,
        hits: Iterable[T],
        *,
        query: str,
        focus_terms: Iterable[str] = (),
        limit: int = 6,
        mode: str = "shadow",
    ) -> GraphRetrievalDecision[T]:
        normalized_mode = str(mode or "shadow").strip().lower()
        if normalized_mode not in _VALID_MODES:
            raise ValueError(f"unsupported graph retrieval mode: {normalized_mode}")
        bounded_limit = max(1, int(limit))
        all_hits = list(hits)
        pool = all_hits[: self.max_candidates]
        baseline = tuple(pool[:bounded_limit])
        focus = {_fold(term) for term in focus_terms if _fold(term)}
        if not focus:
            focus = set(_fold(query).split())

        scored: list[tuple[float, str, T, tuple[str, ...]]] = []
        reason_counts: dict[str, int] = {}
        for hit in pool:
            metadata = getattr(hit, "metadata", None)
            metadata = metadata if isinstance(metadata, dict) else {}
            searchable = _fold(
                " ".join((
                    str(getattr(hit, "title", None) or ""),
                    str(getattr(hit, "content_excerpt", None) or ""),
                ))
            )
            searchable_terms = set(searchable.split())
            coverage = len(focus & searchable_terms) / max(1, len(focus))
            baseline_relevance = max(0.0, min(1.0, float(getattr(hit, "relevance", 0.0) or 0.0)))
            focus_pass = 1.0 if str(metadata.get("query_pass") or "") == "focus" else 0.0
            explicit_evidence = 1.0 if any(
                metadata.get(key) not in (None, "", [], ())
                for key in ("source_id", "node_ids", "segment_id", "conversation_id")
            ) else 0.0
            truth_status = str(getattr(hit, "truth_status", None) or "").lower()
            grounded = 1.0 if truth_status in {
                "verified", "user_confirmed", "source_recorded", "canonical"
            } else 0.0
            score = (
                0.58 * baseline_relevance
                + 0.22 * coverage
                + 0.08 * focus_pass
                + 0.07 * explicit_evidence
                + 0.05 * grounded
            )
            reasons = ["fts_baseline_relevance"]
            if coverage:
                reasons.append("focus_term_coverage")
            if focus_pass:
                reasons.append("focus_query_pass")
            if explicit_evidence:
                reasons.append("explicit_source_metadata")
            if grounded:
                reasons.append("grounded_truth_status")
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            identifier = str(
                getattr(hit, "record_id", None)
                or getattr(hit, "source_locator", None)
                or ""
            )
            scored.append((round(score, 9), identifier, hit, tuple(reasons)))
        scored.sort(key=lambda item: (-item[0], item[1]))

        candidate_list: list[T] = []
        per_conversation: dict[str, int] = {}
        deferred: list[T] = []
        for _, _, hit, _ in scored:
            key = _conversation_key(hit)
            if per_conversation.get(key, 0) >= self.max_per_conversation:
                deferred.append(hit)
                continue
            candidate_list.append(hit)
            per_conversation[key] = per_conversation.get(key, 0) + 1
            if len(candidate_list) >= bounded_limit:
                break
        for hit in deferred:
            if len(candidate_list) >= bounded_limit:
                break
            candidate_list.append(hit)
        candidate = tuple(candidate_list)

        bucket = int(hashlib.sha256(_fold(query).encode("utf-8")).hexdigest()[:8], 16) % 2
        if normalized_mode == "active":
            lane = "graph_candidate"
        elif normalized_mode == "ab" and bucket == 1:
            lane = "graph_candidate"
        else:
            lane = "fts_baseline"
        selected = candidate if lane == "graph_candidate" else baseline
        changed_positions = sum(
            1
            for index in range(min(len(baseline), len(candidate)))
            if baseline[index] is not candidate[index]
        ) + abs(len(baseline) - len(candidate))
        return GraphRetrievalDecision(
            selected=selected,
            candidate=candidate,
            telemetry={
                "schema_version": SCHEMA_VERSION,
                "status": "ready",
                "mode": normalized_mode,
                "selected_lane": lane,
                "ab_bucket": bucket if normalized_mode == "ab" else None,
                "candidate_count": len(pool),
                "selected_count": len(selected),
                "changed_position_count": changed_positions,
                "baseline_fingerprint": _fingerprint(baseline),
                "candidate_fingerprint": _fingerprint(candidate),
                "reason_counts": reason_counts,
                "input_truncated": len(all_hits) > len(pool),
                "fts_fallback_available": True,
                "content_recorded_in_telemetry": False,
                "fact_creation_allowed": False,
                "memory_promotion_allowed": False,
                "truth_boundary": (
                    "Graph-aware retrieval only reranks existing read-only FTS hits. "
                    "It creates no facts, writes no memory and authorizes no promotion."
                ),
            },
        )


__all__ = ["GraphAwareRetrievalController", "GraphRetrievalDecision"]
