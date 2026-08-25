from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Mapping
import hashlib

from latka_jazn.tools.chat_export_models import ConversationGraph

from ..intermediate import IntermediateRecord, canonical_json


def iso_from_epoch(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (OSError, OverflowError, TypeError, ValueError):
        return str(value).strip() or None


def conversation_records(graphs: Iterable[ConversationGraph]) -> Iterator[IntermediateRecord]:
    for graph in graphs:
        for node in graph.nodes:
            if not (node.text or "").strip():
                continue
            source_record_id = str(node.message_id or node.node_id)
            event_time = iso_from_epoch(node.create_time)
            yield IntermediateRecord(
                logical_key=f"chat:{graph.conversation_id}:{source_record_id}",
                source_record_id=source_record_id,
                record_kind="conversation_message",
                title=graph.title,
                content=node.text,
                event_time_start=event_time,
                event_time_end=event_time,
                timestamp_status=node.timestamp_status,
                conversation_id=graph.conversation_id,
                role=node.role,
                truth_status="source_recorded",
                importance=0.55,
                raw={
                    "node_id": node.node_id,
                    "parent_node_id": node.parent_node_id,
                    "branch_id": node.branch_id,
                    "on_current_path": node.on_current_path,
                    "content_type": node.content_type,
                    "text_sha256": node.text_sha256,
                },
                provenance={
                    "conversation_id": graph.conversation_id,
                    "conversation_semantic_tree_sha256": graph.semantic_tree_sha256,
                    "conversation_raw_tree_sha256": graph.raw_tree_sha256,
                    "node_id": node.node_id,
                    "message_id": node.message_id,
                },
            )


def stable_key(prefix: str, raw: Mapping[str, Any], candidates: Iterable[str]) -> str:
    for name in candidates:
        value = str(raw.get(name) or "").strip()
        if value:
            return f"{prefix}:{value.casefold()}"
    digest = hashlib.sha256(canonical_json(dict(raw)).encode("utf-8")).hexdigest()
    return f"{prefix}:sha256:{digest}"


__all__ = ["conversation_records", "iso_from_epoch", "stable_key"]
