from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import hashlib

SCHEMA_VERSION="memory_recall_content_contract/v1"

@dataclass(slots=True)
class MemoryRecallItem:
    content: str
    source: str
    memory_type: str
    timestamp: str | None = None
    confidence: float = 0.0
    relevance: float = 0.0
    item_id: str = ""
    truth_boundary: str = "recalled_or_indexed_memory_not_biological_experience"
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    def to_dict(self): return asdict(self)

@dataclass(slots=True)
class MemoryRecallContract:
    query: str
    items: list[dict[str, Any]]
    counts: dict[str, int]
    raw_memory_status: str = "unknown"
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = "Pamięć musi przekazywać treść, źródło, typ, czas, confidence i relevance. Same liczniki nie wystarczają do odpowiedzi."
    def to_dict(self): return asdict(self)

class MemoryRecallContractBuilder:
    def build(self, memory_context: dict[str, Any], *, user_text: str) -> MemoryRecallContract:
        ctx=memory_context or {}; items=[]
        frozen_payload = ctx.get("memory_recall_payload")
        if isinstance(frozen_payload, dict) and isinstance(frozen_payload.get("items"), list):
            for raw in frozen_payload.get("items") or []:
                if not isinstance(raw, dict):
                    continue
                content = str(raw.get("content_excerpt") or raw.get("content") or "").strip()
                source = str(raw.get("source") or "").strip()
                memory_type = str(raw.get("item_type") or raw.get("memory_type") or "memory_item").strip()
                if not content or not source:
                    continue
                item_id = str(raw.get("item_id") or "").strip() or self._stable_item_id(
                    memory_type=memory_type,
                    source=source,
                    timestamp=raw.get("timestamp"),
                    content=content,
                )
                raw_metadata_value = raw.get("metadata")
                raw_metadata: dict[str, Any] = raw_metadata_value if isinstance(raw_metadata_value, dict) else {}
                items.append(MemoryRecallItem(
                    content=content[:1800],
                    source=source,
                    memory_type=memory_type,
                    timestamp=str(raw.get("timestamp") or "").strip() or None,
                    confidence=self._float(raw.get("confidence")),
                    relevance=self._float(raw.get("relevance_score") or raw.get("relevance")),
                    item_id=item_id,
                    truth_boundary="frozen_memory_recall_payload_item",
                    metadata={
                        "query_term": raw.get("query_term"),
                        "grounding": raw.get("grounding"),
                        "relevance_label": raw.get("relevance_label"),
                        "meaning_assessment": raw.get("meaning_assessment"),
                        "semantic_source_type": raw.get("semantic_source_type"),
                        "provenance_label": raw.get("provenance_label"),
                        "truth_status": raw.get("truth_status"),
                        "source_layer": raw_metadata.get("source_layer"),
                        "source_database": raw_metadata.get("source_database"),
                        "source_locator": raw_metadata.get("source_locator"),
                        "evidence_sources": raw_metadata.get("evidence_sources") or [],
                    },
                ).to_dict())
            return MemoryRecallContract(
                query=user_text,
                items=items,
                counts=dict(ctx.get("counts") or {}),
                raw_memory_status=str((ctx.get("living_memory_search") or {}).get("status") or "unknown"),
            )
        for hit in ctx.get('living_memory_hits') or []:
            content=str(hit.get('content_excerpt') or hit.get('content') or '')
            if content:
                layer=str(hit.get('source_layer') or 'living_memory')
                source=str(hit.get('source_database') or layer)
                locator=str(hit.get('source_locator') or '')
                if locator:
                    source=f"{source} / {locator}"
                items.append(MemoryRecallItem(
                    content=content[:1800],
                    source=source,
                    memory_type=f'living_memory:{layer}',
                    timestamp=hit.get('timestamp'),
                    confidence=float(hit.get('confidence') or 0.0),
                    relevance=float(hit.get('relevance') or 0.0),
                    truth_boundary=f"truth_status={hit.get('truth_status') or 'source_recorded'}; read_only_source_not_automatic_l3",
                    metadata=hit,
                ).to_dict())
        for ep in ctx.get('episodes') or []:
            content=str(ep.get('scene') or ep.get('text') or '')
            if content:
                items.append(MemoryRecallItem(content=content[:1800], source=str(ep.get('source') or 'episodic_memories'), memory_type='episode', timestamp=ep.get('created_at_local') or ep.get('created_at_utc'), confidence=float(ep.get('confidence') or 0.70), relevance=float(ep.get('relevance') or 0.60), metadata={k:v for k,v in ep.items() if k not in {'scene','text'}}).to_dict())
        for msg in ctx.get('legacy_messages') or []:
            content=str(msg.get('text') or msg.get('content') or '')
            if content:
                items.append(MemoryRecallItem(content=content[:1800], source=str(msg.get('conversation_title') or msg.get('source') or 'legacy_messages'), memory_type='legacy_message', timestamp=msg.get('created_at_local') or msg.get('created_at_utc'), confidence=float(msg.get('confidence') or 0.62), relevance=float(msg.get('relevance') or 0.55), metadata={k:v for k,v in msg.items() if k not in {'text','content'}}).to_dict())
        for hit in ctx.get('source_file_hits') or []:
            content=str(hit.get('content_excerpt') or hit.get('snippet') or hit.get('text') or '')
            if content:
                items.append(MemoryRecallItem(content=content[:1800], source=str(hit.get('path') or 'source_file'), memory_type='source_file_hit', timestamp=hit.get('modified_at'), confidence=float(hit.get('confidence') or 0.55), relevance=float(hit.get('score') or hit.get('relevance') or 0.50), metadata=hit).to_dict())
        for hit in ctx.get('conversation_archive_hits') or []:
            content=str(hit.get('excerpt') or hit.get('text') or '')
            if content:
                source = str(hit.get('source_name') or hit.get('source_locator') or 'conversation_archive_v1')
                items.append(MemoryRecallItem(content=content[:1800], source=source, memory_type='conversation_archive_hit', timestamp=hit.get('create_time_warsaw') or hit.get('create_time'), confidence=float(hit.get('identity_confidence') or 0.58), relevance=float(hit.get('relevance') or 0.58), metadata=hit).to_dict())
        for raw in ctx.get('raw_chat_fallback') or []:
            content=str(raw.get('snippet') or raw.get('text') or '')
            if content:
                items.append(MemoryRecallItem(content=content[:1800], source='memory/raw/chat.html', memory_type='raw_chat_fallback', timestamp=raw.get('timestamp'), confidence=0.45, relevance=float(raw.get('score') or 0.45), metadata=raw).to_dict())
        for item in items:
            item["item_id"] = str(item.get("item_id") or "").strip() or self._stable_item_id(
                memory_type=str(item.get("memory_type") or "memory_item"),
                source=str(item.get("source") or "unknown"),
                timestamp=item.get("timestamp"),
                content=str(item.get("content") or ""),
            )
        return MemoryRecallContract(query=user_text, items=items, counts=dict(ctx.get('counts') or {}), raw_memory_status=str((ctx.get('living_memory_search') or {}).get('status') or 'unknown'))

    @staticmethod
    def _stable_item_id(*, memory_type: str, source: str, timestamp: Any, content: str) -> str:
        material = "\n".join(
            (str(memory_type), str(source), str(timestamp or ""), str(content))
        ).encode("utf-8")
        return "memory_" + hashlib.sha256(material).hexdigest()[:24]

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value or 0.0)))
        except (TypeError, ValueError):
            return 0.0