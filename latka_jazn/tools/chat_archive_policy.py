from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
import json
import sqlite3
import uuid
import zlib

from latka_jazn.tools.chat_export_models import ConversationGraph


PAYLOAD_CODEC = "zlib-json-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})")}


def ensure_archive_schema(con: sqlite3.Connection) -> None:
    node_columns = _columns(con, "nodes")
    if "visibility" not in node_columns:
        con.execute("ALTER TABLE nodes ADD COLUMN visibility TEXT NOT NULL DEFAULT 'visible'")
    if "memory_eligible" not in node_columns:
        con.execute(
            "ALTER TABLE nodes ADD COLUMN memory_eligible "
            "INTEGER NOT NULL DEFAULT 1 CHECK(memory_eligible IN (0,1))"
        )
    conflict_columns = _columns(con, "import_conflicts")
    if "resolution_status" not in conflict_columns:
        con.execute(
            "ALTER TABLE import_conflicts ADD COLUMN resolution_status "
            "TEXT NOT NULL DEFAULT 'unresolved'"
        )
    if "resolution_reason" not in conflict_columns:
        con.execute("ALTER TABLE import_conflicts ADD COLUMN resolution_reason TEXT")
    con.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_nodes_recall_eligible
          ON nodes(conversation_id,memory_eligible,role,structural_ordinal);
        CREATE TABLE IF NOT EXISTS conversation_variant_payloads(
          variant_id TEXT PRIMARY KEY,
          conversation_id TEXT NOT NULL,
          import_id TEXT NOT NULL,
          relation_to_active TEXT NOT NULL,
          raw_tree_sha256 TEXT NOT NULL,
          semantic_tree_sha256 TEXT NOT NULL,
          payload_codec TEXT NOT NULL,
          payload_blob BLOB NOT NULL,
          payload_size_uncompressed INTEGER NOT NULL,
          created_at_utc TEXT NOT NULL,
          UNIQUE(conversation_id,import_id,semantic_tree_sha256),
          FOREIGN KEY(import_id) REFERENCES import_sources(import_id)
        );
        CREATE INDEX IF NOT EXISTS idx_conversation_variants_lookup
          ON conversation_variant_payloads(conversation_id,created_at_utc);
        """
    )
    con.execute(
        """UPDATE nodes SET visibility='non_dialogue',memory_eligible=0
           WHERE COALESCE(role,'') NOT IN ('user','assistant')"""
    )


def parent_conflicts(con: sqlite3.Connection, graph: ConversationGraph) -> tuple[str, ...]:
    existing = {
        str(row["node_id"]): str(row["parent_node_id"]) if row["parent_node_id"] is not None else None
        for row in con.execute(
            "SELECT node_id,parent_node_id FROM nodes WHERE conversation_id=?",
            (graph.conversation_id,),
        )
    }
    return tuple(sorted(
        node.node_id
        for node in graph.nodes
        if node.node_id in existing and existing[node.node_id] != node.parent_node_id
    ))


def archive_variant(
    con: sqlite3.Connection,
    *,
    import_id: str,
    graph: ConversationGraph,
    relation: str,
) -> None:
    raw = json.dumps(
        graph.source_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    compressed = zlib.compress(raw, level=6)
    variant_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        "jazn-chat-archive-variant:"
        f"{graph.conversation_id}:{graph.raw_tree_sha256}:{graph.semantic_tree_sha256}",
    ))
    con.execute(
        """INSERT OR IGNORE INTO conversation_variant_payloads(
           variant_id,conversation_id,import_id,relation_to_active,raw_tree_sha256,
           semantic_tree_sha256,payload_codec,payload_blob,payload_size_uncompressed,created_at_utc
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            variant_id,
            graph.conversation_id,
            import_id,
            relation,
            graph.raw_tree_sha256,
            graph.semantic_tree_sha256,
            PAYLOAD_CODEC,
            sqlite3.Binary(compressed),
            len(raw),
            _utc_now(),
        ),
    )


def _raw_message(graph: ConversationGraph, node_id: str) -> Mapping[str, Any]:
    mapping = graph.source_payload.get("mapping")
    raw_node = mapping.get(node_id) if isinstance(mapping, dict) else None
    message = raw_node.get("message") if isinstance(raw_node, dict) else None
    return message if isinstance(message, dict) else {}


def _visibility(role: str | None, message: Mapping[str, Any]) -> tuple[str, bool]:
    metadata = message.get("metadata")
    if isinstance(metadata, dict) and metadata.get("is_visually_hidden_from_conversation"):
        return "hidden", False
    if str(role or "") not in {"user", "assistant"}:
        return "non_dialogue", False
    if message.get("channel") not in (None, "", "final"):
        return "non_dialogue", False
    if message.get("recipient") not in (None, "", "all"):
        return "non_dialogue", False
    return "visible", True


def update_visibility(con: sqlite3.Connection, graph: ConversationGraph) -> None:
    for node in graph.nodes:
        visibility, eligible = _visibility(node.role, _raw_message(graph, node.node_id))
        con.execute(
            """UPDATE nodes SET visibility=?,memory_eligible=?
               WHERE conversation_id=? AND node_id=?""",
            (visibility, int(eligible), graph.conversation_id, node.node_id),
        )


def resolve_divergence(
    con: sqlite3.Connection,
    *,
    import_id: str,
    conversation_id: str,
    changed_node_ids: tuple[str, ...],
    parent_conflict_ids: tuple[str, ...],
) -> bool:
    safe = not changed_node_ids and not parent_conflict_ids
    status = "preserved_union" if safe else "unresolved"
    reason = (
        "shared node payloads and parents agree; unique branches are preserved"
        if safe
        else "same node identity changed payload or parent; projection decision required"
    )
    con.execute(
        """UPDATE import_conflicts SET resolution_status=?,resolution_reason=?
           WHERE import_id=? AND conversation_id=?""",
        (status, reason, import_id, conversation_id),
    )
    return safe


__all__ = [
    "archive_variant",
    "ensure_archive_schema",
    "parent_conflicts",
    "resolve_divergence",
    "update_visibility",
]
