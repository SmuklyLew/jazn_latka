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


def _raw_message(graph: ConversationGraph, node_id: str) -> Mapping[str, Any]:
    mapping = graph.source_payload.get("mapping")
    raw_node = mapping.get(node_id) if isinstance(mapping, dict) else None
    message = raw_node.get("message") if isinstance(raw_node, dict) else None
    return message if isinstance(message, dict) else {}


def _visibility(node_role: str | None, message: Mapping[str, Any]) -> tuple[str, bool]:
    metadata = message.get("metadata")
    hidden = bool(metadata.get("is_visually_hidden_from_conversation")) if isinstance(metadata, dict) else False
    if hidden:
        return "hidden", False
    if str(node_role or "") not in {"user", "assistant"}:
        return "non_dialogue", False
    if message.get("channel") not in (None, "", "final"):
        return "non_dialogue", False
    if message.get("recipient") not in (None, "", "all"):
        return "non_dialogue", False
    return "visible", True


def _assets(node: Any, message: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = {
        asset.asset_pointer: {
            "asset_pointer": asset.asset_pointer,
            "original_filename": asset.original_filename,
            "content_type": asset.content_type,
            "mime_type": asset.mime_type,
            "availability_status": asset.availability_status,
            "file_sha256": None,
        }
        for asset in node.assets
    }
    metadata = message.get("metadata")
    attachments = metadata.get("attachments") if isinstance(metadata, dict) else None
    for attachment in attachments if isinstance(attachments, list) else ():
        if not isinstance(attachment, dict):
            continue
        pointer = str(attachment.get("id") or attachment.get("file_id") or attachment.get("asset_pointer") or "").strip()
        if not pointer:
            continue
        row = rows.setdefault(pointer, {
            "asset_pointer": pointer,
            "original_filename": None,
            "content_type": "attachment",
            "mime_type": None,
            "availability_status": "referenced_only",
            "file_sha256": None,
        })
        row["original_filename"] = attachment.get("name") or attachment.get("filename") or row["original_filename"]
        row["mime_type"] = attachment.get("mimeType") or attachment.get("mime_type") or row["mime_type"]
        row["file_sha256"] = attachment.get("sha256") or attachment.get("file_sha256") or row["file_sha256"]
    return [rows[key] for key in sorted(rows)]


def conversation_records(graphs: Iterable[ConversationGraph]) -> Iterator[IntermediateRecord]:
    for graph in graphs:
        for node in graph.nodes:
            if not (node.text or "").strip():
                continue
            message = _raw_message(graph, node.node_id)
            visibility, eligible = _visibility(node.role, message)
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
                importance=0.55 if eligible else 0.05,
                raw={
                    "node_id": node.node_id,
                    "parent_node_id": node.parent_node_id,
                    "children": list(node.children),
                    "branch_id": node.branch_id,
                    "on_current_path": node.on_current_path,
                    "content_type": node.content_type,
                    "text_sha256": node.text_sha256,
                    "visibility": visibility,
                    "memory_eligible": eligible,
                    "assets": _assets(node, message),
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
