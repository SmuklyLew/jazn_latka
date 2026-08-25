from __future__ import annotations

"""Typed, read-only memory API for Łatka and host adapters.

Callers select L0 and active memory explicitly.  The API never promotes,
activates, edits, or accepts SQL from a caller.
"""

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Sequence
import json
import sqlite3

from latka_jazn.tools.memory_rebuild_common import fts_queries

from .embeddings import EmbeddingProvider, cosine_similarity, unpack_vector
from .settings import MemoryRebuildSettings
from .sqlite_utils import ClosingSQLiteConnection


class MemoryLayer(str, Enum):
    L0 = "l0"
    ACTIVE = "active"


class RecallStatus(str, Enum):
    EVIDENCE_FOUND = "evidence_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RecallQuery:
    text: str
    layers: tuple[MemoryLayer, ...] = (MemoryLayer.L0,)
    temporal_start: str | None = None
    temporal_end: str | None = None
    limit: int = 20
    require_provenance: bool = True
    use_embeddings: bool = False

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("RecallQuery.text nie może być pusty")
        if not self.layers:
            raise ValueError("RecallQuery.layers nie może być puste")
        if self.limit < 1 or self.limit > 500:
            raise ValueError("RecallQuery.limit musi mieścić się w zakresie 1..500")
        if self.temporal_start and self.temporal_end and self.temporal_start > self.temporal_end:
            raise ValueError("temporal_start nie może być późniejsze niż temporal_end")


@dataclass(frozen=True, slots=True)
class MemoryCitation:
    source_id: str
    source_kind: str
    source_record_id: str
    source_sha256: str | None
    adapter_id: str | None
    event_time_start: str | None
    event_time_end: str | None
    revision: int | None


@dataclass(frozen=True, slots=True)
class RecallHit:
    record_id: str
    layer: MemoryLayer
    record_kind: str
    title: str
    content: str
    truth_status: str
    score: float
    citation: MemoryCitation


@dataclass(frozen=True, slots=True)
class RecallResponse:
    status: RecallStatus
    known: bool
    query: RecallQuery
    hits: tuple[RecallHit, ...]
    reason: str
    retrieval_mode: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["query"]["layers"] = [item.value for item in self.query.layers]
        for item in value["hits"]:
            item["layer"] = item["layer"].value if isinstance(item["layer"], MemoryLayer) else str(item["layer"])
        return value


class TypedMemoryAPI:
    def __init__(
        self,
        database: str | Path,
        *,
        settings: MemoryRebuildSettings | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.path = Path(database).expanduser().resolve()
        self.settings = settings or MemoryRebuildSettings()
        self.embedding_provider = embedding_provider

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        con = sqlite3.connect(
            f"file:{self.path.as_posix()}?mode=ro",
            uri=True,
            timeout=30,
            factory=ClosingSQLiteConnection,
        )
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        return con

    @staticmethod
    def _score(rank: Any) -> float:
        try:
            return 1.0 / (1.0 + abs(float(rank)))
        except (TypeError, ValueError):
            return 0.0

    def _l0_hits(self, con: sqlite3.Connection, query: RecallQuery) -> list[RecallHit]:
        rows: Sequence[sqlite3.Row] = ()
        for expression in fts_queries(query.text):
            rows = con.execute(
                """SELECT r.*,s.adapter_id,s.source_sha256,bm25(memory_l0_fts) AS lexical_rank
                   FROM memory_l0_fts
                   JOIN memory_l0_records r ON r.rowid=memory_l0_fts.rowid
                   JOIN memory_l0_sources s ON s.source_id=r.source_id
                   WHERE memory_l0_fts MATCH ? AND r.is_current_revision=1
                     AND (? IS NULL OR COALESCE(r.event_time_end,r.event_time_start)>=?)
                     AND (? IS NULL OR COALESCE(r.event_time_start,r.event_time_end)<=?)
                   ORDER BY lexical_rank LIMIT ?""",
                (
                    expression,
                    query.temporal_start, query.temporal_start,
                    query.temporal_end, query.temporal_end,
                    max(query.limit * 4, query.limit),
                ),
            ).fetchall()
            if rows:
                break
        result: list[RecallHit] = []
        for row in rows:
            try:
                provenance = json.loads(str(row["provenance_json"] or "{}"))
            except json.JSONDecodeError:
                provenance = {}
            source_id = str(provenance.get("source_id") or row["source_id"] or "")
            source_sha = str(provenance.get("source_sha256") or row["source_sha256"] or "") or None
            if query.require_provenance and (not source_id or not source_sha):
                continue
            score = self._score(row["lexical_rank"])
            if score < self.settings.min_lexical_score:
                continue
            result.append(RecallHit(
                record_id=str(row["record_id"]),
                layer=MemoryLayer.L0,
                record_kind=str(row["record_kind"]),
                title=str(row["title"] or ""),
                content=str(row["content"]),
                truth_status=str(row["truth_status"]),
                score=score,
                citation=MemoryCitation(
                    source_id=source_id,
                    source_kind=str(row["source_kind"]),
                    source_record_id=str(row["source_record_id"]),
                    source_sha256=source_sha,
                    adapter_id=str(row["adapter_id"]),
                    event_time_start=str(row["event_time_start"]) if row["event_time_start"] else None,
                    event_time_end=str(row["event_time_end"]) if row["event_time_end"] else None,
                    revision=int(row["revision"]),
                ),
            ))
        return result

    def _active_hits(self, con: sqlite3.Connection, query: RecallQuery) -> list[RecallHit]:
        rows: Sequence[sqlite3.Row] = ()
        for expression in fts_queries(query.text):
            rows = con.execute(
                """SELECT r.*,bm25(memory_records_fts) AS lexical_rank
                   FROM memory_records_fts
                   JOIN memory_records r ON r.rowid=memory_records_fts.rowid
                   WHERE memory_records_fts MATCH ? AND r.active=1
                     AND (? IS NULL OR r.updated_at_utc>=?)
                     AND (? IS NULL OR r.created_at_utc<=?)
                   ORDER BY lexical_rank LIMIT ?""",
                (
                    expression,
                    query.temporal_start, query.temporal_start,
                    query.temporal_end, query.temporal_end,
                    max(query.limit * 4, query.limit),
                ),
            ).fetchall()
            if rows:
                break
        result: list[RecallHit] = []
        for row in rows:
            evidence = con.execute(
                """SELECT source_type,source_id,evidence_json FROM memory_evidence
                   WHERE memory_id=? ORDER BY evidence_key LIMIT 1""",
                (row["memory_id"],),
            ).fetchone()
            if query.require_provenance and evidence is None:
                continue
            source_type = str(evidence["source_type"]) if evidence else "active_memory"
            source_id = str(evidence["source_id"]) if evidence else str(row["memory_id"])
            source_sha: str | None = None
            if evidence:
                try:
                    payload = json.loads(str(evidence["evidence_json"] or "{}"))
                    source_sha = str(payload.get("source_sha256") or "") or None
                except json.JSONDecodeError:
                    pass
            result.append(RecallHit(
                record_id=str(row["memory_id"]),
                layer=MemoryLayer.ACTIVE,
                record_kind=str(row["kind"]),
                title="",
                content=str(row["content"]),
                truth_status=str(row["truth_status"]),
                score=self._score(row["lexical_rank"]),
                citation=MemoryCitation(
                    source_id=source_id,
                    source_kind=source_type,
                    source_record_id=source_id,
                    source_sha256=source_sha,
                    adapter_id=None,
                    event_time_start=str(row["created_at_utc"]),
                    event_time_end=str(row["updated_at_utc"]),
                    revision=None,
                ),
            ))
        return result

    def _rerank_embeddings(
        self, con: sqlite3.Connection, query: RecallQuery, hits: list[RecallHit],
    ) -> list[RecallHit]:
        if not query.use_embeddings:
            return hits
        if not self.settings.embeddings_enabled or self.embedding_provider is None:
            raise ValueError("Embedding retrieval wymaga jawnie włączonych ustawień i providera.")
        provider = self.embedding_provider
        vectors = provider.embed([query.text])
        if len(vectors) != 1 or len(vectors[0]) != provider.dimensions:
            raise ValueError("Embedding provider returned an invalid query vector")
        query_vector = vectors[0]
        reranked: list[RecallHit] = []
        for hit in hits:
            if hit.layer is not MemoryLayer.L0:
                reranked.append(hit)
                continue
            row = con.execute(
                """SELECT dimensions,vector_blob FROM memory_l0_embeddings
                   WHERE record_id=? AND model_id=?""",
                (hit.record_id, provider.model_id),
            ).fetchone()
            if row is None:
                reranked.append(hit)
                continue
            vector = unpack_vector(bytes(row["vector_blob"]), int(row["dimensions"]))
            semantic = (cosine_similarity(query_vector, vector) + 1.0) / 2.0
            reranked.append(RecallHit(
                record_id=hit.record_id,
                layer=hit.layer,
                record_kind=hit.record_kind,
                title=hit.title,
                content=hit.content,
                truth_status=hit.truth_status,
                score=(0.65 * hit.score) + (0.35 * semantic),
                citation=hit.citation,
            ))
        return reranked

    def recall(self, query: RecallQuery) -> RecallResponse:
        hits: list[RecallHit] = []
        with self._connect() as con:
            tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master")}
            if "memory_l0_fts" not in tables:
                raise ValueError("Baza nie ma obowiązkowego indeksu FTS5 memory_l0_fts.")
            if MemoryLayer.L0 in query.layers:
                hits.extend(self._l0_hits(con, query))
            if MemoryLayer.ACTIVE in query.layers:
                if "memory_records_fts" not in tables:
                    raise ValueError("Baza nie ma obowiązkowego indeksu FTS5 pamięci aktywnej.")
                hits.extend(self._active_hits(con, query))
            hits = self._rerank_embeddings(con, query, hits)
        hits.sort(key=lambda item: (-item.score, item.citation.event_time_start or "", item.record_id))
        selected = tuple(hits[:query.limit])
        if not selected:
            return RecallResponse(
                status=RecallStatus.UNKNOWN,
                known=False,
                query=query,
                hits=(),
                reason="Brak wystarczających, temporalnie zgodnych rekordów z wymaganą proweniencją.",
                retrieval_mode="fts5+optional_embeddings",
            )
        return RecallResponse(
            status=RecallStatus.EVIDENCE_FOUND,
            known=True,
            query=query,
            hits=selected,
            reason="Znaleziono rekordy spełniające warunki temporalne i proweniencji.",
            retrieval_mode="fts5+optional_embeddings",
        )


__all__ = [
    "MemoryCitation", "MemoryLayer", "RecallHit", "RecallQuery", "RecallResponse",
    "RecallStatus", "TypedMemoryAPI",
]
