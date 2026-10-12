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
_REFERENTIAL_CONTROL_TERMS = frozenset({
    "wroc", "wrocmy", "doprecyzuj", "doprecyz", "zrodlo", "zrodla",
    "wspomnienie", "wspomnienia", "poszukaj", "znajdz", "odnajdz",
})


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


def _meaningful_focus_terms(focus_terms: Iterable[str], query: str) -> set[str]:
    values: set[str] = set()
    for term in focus_terms:
        folded = _fold(term)
        if folded and folded not in _REFERENTIAL_CONTROL_TERMS:
            values.add(folded)
    if values:
        return values
    return {
        token
        for token in _fold(query).split()
        if token and token not in _REFERENTIAL_CONTROL_TERMS
    }


@dataclass(slots=True, frozen=True)
class GraphRetrievalDecision(Generic[T]):
    selected: tuple[T, ...]
    candidate: tuple[T, ...]
    telemetry: dict[str, Any]


class GraphAwareRetrievalController:
    """Bounded deterministic reranker with an FTS baseline and fail-safe promotion.

    The candidate lane may promote an existing FTS hit only when that hit covers a
    meaningful focus term. Hits with zero focus coverage retain their FTS order and
    therefore cannot be promoted merely to satisfy conversation diversity. This
    keeps the graph experiment from trading recall for a larger wrong-conversation
    rate. The controller cannot write memory, create facts or approve promotion.
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
        focus = _meaningful_focus_terms(focus_terms, query)

        scored: list[tuple[float, float, int, str, T, tuple[str, ...]]] = []
        reason_counts: dict[str, int] = {}
        pool_size = max(1, len(pool))
        for baseline_rank, hit in enumerate(pool):
            metadata = getattr(hit, "metadata", None)
            metadata = metadata if isinstance(metadata, dict) else {}
            searchable = _fold(
                " ".join((
                    str(getattr(hit, "title", None) or ""),
                    str(getattr(hit, "content_excerpt", None) or ""),
                ))
            )
            searchable_terms = set(searchable.split())
            coverage = len(focus & searchable_terms) / max(1, len(focus)) if focus else 0.0
            baseline_relevance = max(0.0, min(1.0, float(getattr(hit, "relevance", 0.0) or 0.0)))
            rank_prior = 1.0 - (baseline_rank / max(1, pool_size - 1))
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
                0.42 * baseline_relevance
                + 0.30 * coverage
                + 0.10 * rank_prior
                + 0.07 * focus_pass
                + 0.06 * explicit_evidence
                + 0.05 * grounded
            )
            reasons = ["fts_baseline_relevance", "fts_rank_prior"]
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
            scored.append((round(score, 9), coverage, baseline_rank, identifier, hit, tuple(reasons)))

        # Only evidence-bearing focus matches may move ahead of their FTS rank. All
        # zero-coverage rows keep the original FTS order. This deliberately removes
        # the old hard conversation-diversity rule that could promote unrelated
        # conversations and worsen the wrong-conversation rate.
        promotable = [item for item in scored if item[1] > 0.0]
        promotable.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
        promotable_ids = {id(item[4]) for item in promotable}
        stable_remainder = [item for item in scored if id(item[4]) not in promotable_ids]

        candidate_list: list[T] = []
        seen_objects: set[int] = set()
        per_conversation: dict[str, int] = {}
        diversity_deferred = 0
        ordered = [*promotable, *stable_remainder]
        for index, item in enumerate(ordered):
            _, coverage, _, _, hit, _ = item
            object_id = id(hit)
            if object_id in seen_objects:
                continue
            key = _conversation_key(hit)
            # Conversation diversity is a bounded tie-break among equally or
            # better focus-grounded hits. Defer a repeated conversation only when
            # the remaining positive-focus pool can still fill every output slot;
            # diversity must never force a zero-focus row into the result.
            if coverage > 0.0 and per_conversation.get(key, 0) >= self.max_per_conversation:
                remaining_slots = bounded_limit - len(candidate_list)
                positive_remaining = [
                    later
                    for later in range(index + 1, len(ordered))
                    if id(ordered[later][4]) not in seen_objects
                    and ordered[later][1] > 0.0
                ]
                alternative_index = next(
                    (
                        later
                        for later in positive_remaining
                        if ordered[later][1] >= coverage
                        and _conversation_key(ordered[later][4]) != key
                    ),
                    None,
                )
                if alternative_index is not None and len(positive_remaining) >= remaining_slots:
                    diversity_deferred += 1
                    continue
            candidate_list.append(hit)
            seen_objects.add(object_id)
            per_conversation[key] = per_conversation.get(key, 0) + 1
            if len(candidate_list) >= bounded_limit:
                break

        if len(candidate_list) < bounded_limit:
            for hit in pool:
                if id(hit) in seen_objects:
                    continue
                candidate_list.append(hit)
                seen_objects.add(id(hit))
                if len(candidate_list) >= bounded_limit:
                    break
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
        zero_coverage_promotions = sum(
            1
            for index, hit in enumerate(candidate)
            if index < len(baseline)
            and baseline[index] is not hit
            and next((item[1] for item in scored if item[4] is hit), 0.0) <= 0.0
        )
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
                "zero_coverage_promotion_count": zero_coverage_promotions,
                "diversity_deferred_count": diversity_deferred,
                "meaningful_focus_term_count": len(focus),
                "baseline_fingerprint": _fingerprint(baseline),
                "candidate_fingerprint": _fingerprint(candidate),
                "reason_counts": reason_counts,
                "input_truncated": len(all_hits) > len(pool),
                "fts_fallback_available": True,
                "content_recorded_in_telemetry": False,
                "fact_creation_allowed": False,
                "memory_promotion_allowed": False,
                "promotion_requires_focus_coverage": True,
                "truth_boundary": (
                    "Graph-aware retrieval only reranks existing read-only FTS hits. "
                    "A hit with zero meaningful focus coverage cannot be promoted over the FTS baseline; "
                    "conversation diversity is only a bounded tie-break among equally grounded matches. "
                    "The controller creates no facts, writes no memory and authorizes no promotion."
                ),
            },
        )


__all__ = ["GraphAwareRetrievalController", "GraphRetrievalDecision"]
