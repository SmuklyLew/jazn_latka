from __future__ import annotations

"""Deterministic FTS5-only Recall baseline.

No model is trained or loaded here. Embeddings are explicitly disabled so every
future retriever/query-rewrite/reranker experiment has a stable sparse baseline.
"""

from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

from ..settings import MemoryRebuildSettings
from ..typed_api import MemoryLayer, RecallQuery, TypedMemoryAPI
from .models import RecallBenchmarkCase


BASELINE_ID = "fts5-bm25/v1"


class FTS5RecallBaseline:
    baseline_id = BASELINE_ID
    uses_training = False
    uses_embeddings = False

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database).expanduser().resolve()
        self.settings = MemoryRebuildSettings(
            require_fts5=True,
            require_provenance=True,
            embeddings_enabled=False,
            embedding_model=None,
            automatic_l2=False,
            automatic_l3=False,
            automatic_activation=False,
        )
        self.api = TypedMemoryAPI(self.database, settings=self.settings, embedding_provider=None)

    def search(self, case: RecallBenchmarkCase) -> dict[str, Any]:
        contextual_query = " ".join((*case.context_turns, case.query)).strip()
        query = RecallQuery(
            text=contextual_query,
            layers=(MemoryLayer.L0,),
            temporal_start=case.temporal_start,
            temporal_end=case.temporal_end,
            limit=case.limit,
            require_provenance=True,
            use_embeddings=False,
        )
        started = perf_counter()
        response = self.api.recall(query)
        latency_ms = (perf_counter() - started) * 1000.0
        hits: list[dict[str, Any]] = []
        for item in response.hits:
            citation = asdict(item.citation)
            hits.append(
                {
                    "record_id": item.record_id,
                    "record_kind": item.record_kind,
                    "title": item.title,
                    "content": item.content,
                    "truth_status": item.truth_status,
                    "score": item.score,
                    "source_id": citation["source_id"],
                    "source_kind": citation["source_kind"],
                    "source_record_id": citation["source_record_id"],
                    "source_sha256": citation["source_sha256"],
                    "adapter_id": citation["adapter_id"],
                    "event_time_start": citation["event_time_start"],
                    "event_time_end": citation["event_time_end"],
                    "revision": citation["revision"],
                }
            )
        return {
            "baseline_id": self.baseline_id,
            "status": response.status.value,
            "known": response.known,
            "reason": response.reason,
            "retrieval_mode": "fts5-bm25",
            "latency_ms": latency_ms,
            "hits": hits,
            "uses_training": False,
            "uses_embeddings": False,
        }


__all__ = ["BASELINE_ID", "FTS5RecallBaseline"]
