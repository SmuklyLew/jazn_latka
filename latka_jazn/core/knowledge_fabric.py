from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from latka_jazn.memory.hybrid_retriever import HybridRetriever, RetrievalHit
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("knowledge_fabric")


@dataclass(slots=True)
class KnowledgeQueryPlan:
    retrieval_required: bool
    scope: str
    modes: list[str]
    limit: int
    confidence_threshold: float
    reason: str
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class KnowledgeEvidence:
    evidence_id: str
    text: str
    source_locator: str
    score: float
    mode: str
    provenance: dict[str, Any]
    truth_status: str = "source_recorded"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KnowledgeFabric:
    """Selective local knowledge retrieval over the existing HybridRetriever.

    The fabric adds query planning, provenance-preserving deduplication and an
    optional lightweight relation graph.  It deliberately reuses the existing
    FTS5/vector infrastructure instead of creating a competing memory stack.
    """

    _RETRIEVAL_MARKERS = (
        "sprawdz", "znajdz", "wyszuk", "zrod", "archiw", "pamiet", "wspomn",
        "co wiemy", "co wiadomo", "kiedy", "gdzie", "dlaczego", "porown",
    )
    _GLOBAL_MARKERS = (
        "przez caly", "w calym", "historia", "chronolog", "ewoluc", "trend",
        "wszystkie rozmowy", "calosc", "na przestrzeni", "jak zmienial",
    )

    def __init__(self, retriever: HybridRetriever | Path | str) -> None:
        self.retriever = retriever if isinstance(retriever, HybridRetriever) else HybridRetriever(retriever)
        self._relations: dict[str, set[str]] = {}

    @staticmethod
    def _fold(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").lower()).translate(
            str.maketrans("ąćęłńóśźż", "acelnoszz")
        ).strip()

    def add_relations(self, relations: Iterable[tuple[str, str]]) -> None:
        for left, right in relations:
            a, b = str(left).strip(), str(right).strip()
            if not a or not b or a == b:
                continue
            self._relations.setdefault(a, set()).add(b)
            self._relations.setdefault(b, set()).add(a)

    def plan_query(self, query: str, *, explicit_retrieval: bool = False) -> KnowledgeQueryPlan:
        folded = self._fold(query)
        retrieval_required = explicit_retrieval or any(marker in folded for marker in self._RETRIEVAL_MARKERS)
        global_scope = any(marker in folded for marker in self._GLOBAL_MARKERS) or len(folded.split()) >= 30
        scope = "global" if global_scope else "local"
        modes = ["fts5_bm25", "vector_if_available"]
        if global_scope and self._relations:
            modes.append("relation_graph")
        return KnowledgeQueryPlan(
            retrieval_required=retrieval_required,
            scope=scope,
            modes=modes if retrieval_required else [],
            limit=12 if global_scope else 6,
            confidence_threshold=0.22 if global_scope else 0.30,
            reason=("global query requires broad evidence" if global_scope else "local targeted retrieval") if retrieval_required else "current context is sufficient; retrieval not forced",
        )

    @staticmethod
    def _evidence_from_hit(hit: RetrievalHit) -> KnowledgeEvidence:
        return KnowledgeEvidence(
            evidence_id=hit.document_id,
            text=hit.text,
            source_locator=hit.source_locator,
            score=max(0.0, min(1.0, float(hit.confidence))),
            mode=hit.retrieval_mode,
            provenance=dict(hit.provenance),
        )

    @classmethod
    def _retrieval_query(cls, query: str) -> str:
        # FTS5 treats whitespace-separated terms as an implicit AND.  Strip
        # command words so "znajdź Pamiętnik" searches for the subject rather
        # than requiring the source document to contain the verb "znajdź".
        stop = {
            "znajdz", "wyszukaj", "sprawdz", "pokaz", "przejrzyj", "odnajdz",
            "prosze", "mi", "nam", "teraz", "zrodla", "zrodlo",
        }
        tokens = [token for token in re.findall(r"[\wąćęłńóśźż]+", str(query or "").lower()) if cls._fold(token) not in stop]
        return " ".join(tokens[:12]) or str(query or "").strip()

    def retrieve(
        self,
        query: str,
        *,
        explicit_retrieval: bool = False,
        current_turn_text: str | None = None,
    ) -> tuple[KnowledgeQueryPlan, list[KnowledgeEvidence]]:
        plan = self.plan_query(query, explicit_retrieval=explicit_retrieval)
        if not plan.retrieval_required:
            return plan, []
        search_query = self._retrieval_query(query)
        hits = self.retriever.search(search_query, limit=plan.limit, current_turn_text=current_turn_text)
        evidence: list[KnowledgeEvidence] = []
        seen_sources: set[tuple[str, str]] = set()
        for hit in hits:
            item = self._evidence_from_hit(hit)
            key = (item.source_locator, item.text[:160])
            if key in seen_sources or item.score < plan.confidence_threshold:
                continue
            seen_sources.add(key)
            evidence.append(item)
        return plan, evidence
