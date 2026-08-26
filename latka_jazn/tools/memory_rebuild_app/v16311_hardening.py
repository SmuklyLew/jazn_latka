from __future__ import annotations

"""v16.3.11 hardening for lossless, chat-by-chat base-memory rebuilds.

The module deliberately layers migrations over the v16.1 modular application
instead of forking a second rebuild engine.  It adds:

* selective conversation import from a canonical ChatGPT export,
* strict JSON <-> embedded-HTML control comparison,
* durable full conversation variants for selective imports,
* non-destructive storage of divergent archive branches,
* visible/hidden/non-dialogue classification and recall eligibility,
* attachment metadata cataloguing without claiming unavailable file bytes.

L0 remains source evidence.  Nothing here auto-promotes L2/L3 memory.
"""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence
import hashlib
import json
import sqlite3
import uuid
import zlib

from latka_jazn.tools.chat_export_models import ConversationGraph, MessageNode
from latka_jazn.tools.chat_export_reader import ChatExportReader
from latka_jazn.tools.chat_export_store import ChatExportArchiveStore

from .html_import import read_html_conversations
from .intermediate import IntermediateRecord, PreparedSource, canonical_json, sha256_file
from .l0_store import UnifiedL0Store

HARDENING_VERSION = "memory-rebuild-hardening/v16.3.11"
EXTENDED_L0_SCHEMA_VERSION = "memory_rebuild_l0/v16.3.11"
SELECTIVE_ADAPTER_ID = "chat-selective/v16.3.11"
PAYLOAD_CODEC = "zlib-json-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column_if_missing(con: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    if name not in _table_columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _ensure_extended_l0_schema(con: sqlite3.Connection) -> None:
    _add_column_if_missing(
        con,
        "memory_l0_records",
        "visibility",
        "visibility TEXT NOT NULL DEFAULT 'visible'",
    )
    _add_column_if_missing(
        con,
        "memory_l0_records",
        "memory_eligible",
        "memory_eligible INTEGER NOT NULL DEFAULT 1 CHECK(memory_eligible IN (0,1))",
    )
    # Existing v16.1 system/tool rows can be classified safely from their role.
    con.execute(
        """UPDATE memory_l0_records
           SET visibility='non_dialogue', memory_eligible=0
           WHERE COALESCE(role,'') NOT IN ('user','assistant')"""
    )
    con.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_l0_recall_eligible
          ON memory_l0_records(is_current_revision,memory_eligible,role);
        CREATE TABLE IF NOT EXISTS memory_l0_assets(
          asset_pointer TEXT PRIMARY KEY,
          original_filename TEXT,
          content_type TEXT,
          mime_type TEXT,
          availability_status TEXT NOT NULL DEFAULT 'referenced_only',
          file_sha256 TEXT,
          first_seen_source_id TEXT NOT NULL,
          last_seen_source_id TEXT NOT NULL,
          first_seen_at_utc TEXT NOT NULL,
          last_seen_at_utc TEXT NOT NULL,
          FOREIGN KEY(first_seen_source_id) REFERENCES memory_l0_sources(source_id),
          FOREIGN KEY(last_seen_source_id) REFERENCES memory_l0_sources(source_id)
        );
        CREATE TABLE IF NOT EXISTS memory_l0_record_assets(
          record_id TEXT NOT NULL,
          asset_pointer TEXT NOT NULL,
          PRIMARY KEY(record_id,asset_pointer),
          FOREIGN KEY(record_id) REFERENCES memory_l0_records(record_id) ON DELETE CASCADE,
          FOREIGN KEY(asset_pointer) REFERENCES memory_l0_assets(asset_pointer)
        );
        CREATE TABLE IF NOT EXISTS memory_l0_conversations(
          variant_id TEXT PRIMARY KEY,
          conversation_id TEXT NOT NULL,
          revision INTEGER NOT NULL CHECK(revision>=1),
          source_id TEXT NOT NULL,
          title TEXT NOT NULL DEFAULT '',
          create_time REAL,
          update_time REAL,
          current_node_id TEXT,
          raw_tree_sha256 TEXT NOT NULL,
          semantic_tree_sha256 TEXT NOT NULL,
          node_count INTEGER NOT NULL,
          message_count INTEGER NOT NULL,
          branch_point_count INTEGER NOT NULL,
          payload_codec TEXT NOT NULL,
          payload_blob BLOB NOT NULL,
          payload_size_uncompressed INTEGER NOT NULL,
          created_at_utc TEXT NOT NULL,
          is_current_revision INTEGER NOT NULL CHECK(is_current_revision IN (0,1)),
          UNIQUE(conversation_id,revision),
          UNIQUE(conversation_id,semantic_tree_sha256,source_id),
          FOREIGN KEY(source_id) REFERENCES memory_l0_sources(source_id)
        );
        CREATE INDEX IF NOT EXISTS idx_memory_l0_conversation_current
          ON memory_l0_conversations(conversation_id,is_current_revision,revision);
        CREATE TABLE IF NOT EXISTS memory_l0_imports(
          import_id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL,
          imported_at_utc TEXT NOT NULL,
          mode TEXT NOT NULL,
          selector_json TEXT NOT NULL,
          control_json TEXT NOT NULL DEFAULT '{}',
          conversation_count INTEGER NOT NULL,
          truth_boundary TEXT NOT NULL,
          FOREIGN KEY(source_id) REFERENCES memory_l0_sources(source_id)
        );
        """
    )
    con.execute(
        "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('l0_schema_version',?)",
        (EXTENDED_L0_SCHEMA_VERSION,),
    )
    con.execute(
        "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('chat_archive_hardening',?)",
        (HARDENING_VERSION,),
    )


def _ensure_archive_extension(con: sqlite3.Connection) -> None:
    _add_column_if_missing(
        con,
        "nodes",
        "visibility",
        "visibility TEXT NOT NULL DEFAULT 'visible'",
    )
    _add_column_if_missing(
        con,
        "nodes",
        "memory_eligible",
        "memory_eligible INTEGER NOT NULL DEFAULT 1 CHECK(memory_eligible IN (0,1))",
    )
    con.execute(
        """UPDATE nodes SET visibility='non_dialogue', memory_eligible=0
           WHERE COALESCE(role,'') NOT IN ('user','assistant')"""
    )
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


def _raw_message(graph: ConversationGraph, node_id: str) -> dict[str, Any]:
    mapping = graph.source_payload.get("mapping")
    if not isinstance(mapping, dict):
        return {}
    raw_node = mapping.get(node_id)
    if not isinstance(raw_node, dict):
        return {}
    message = raw_node.get("message")
    return message if isinstance(message, dict) else {}


def _visibility(node: MessageNode, message: Mapping[str, Any]) -> tuple[str, bool]:
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    hidden = bool(metadata.get("is_visually_hidden_from_conversation"))
    role = str(node.role or "")
    channel = message.get("channel")
    recipient = message.get("recipient")
    if hidden:
        return "hidden", False
    if role not in {"user", "assistant"}:
        return "non_dialogue", False
    if channel not in (None, "", "final"):
        return "non_dialogue", False
    if recipient not in (None, "", "all"):
        return "non_dialogue", False
    return "visible", True


def _asset_rows(node: MessageNode, message: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for asset in node.assets:
        rows[asset.asset_pointer] = {
            "asset_pointer": asset.asset_pointer,
            "original_filename": asset.original_filename,
            "content_type": asset.content_type,
            "mime_type": asset.mime_type,
            "availability_status": asset.availability_status,
            "file_sha256": None,
        }
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    attachments = metadata.get("attachments") if isinstance(metadata.get("attachments"), list) else []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        pointer = str(
            attachment.get("id")
            or attachment.get("file_id")
            or attachment.get("asset_pointer")
            or ""
        ).strip()
        if not pointer:
            continue
        row = rows.setdefault(
            pointer,
            {
                "asset_pointer": pointer,
                "original_filename": None,
                "content_type": "attachment",
                "mime_type": None,
                "availability_status": "referenced_only",
                "file_sha256": None,
            },
        )
        row["original_filename"] = (
            attachment.get("name") or attachment.get("filename") or row["original_filename"]
        )
        row["mime_type"] = attachment.get("mimeType") or attachment.get("mime_type") or row["mime_type"]
        digest = attachment.get("sha256") or attachment.get("file_sha256")
        if digest:
            row["file_sha256"] = str(digest)
    return sorted(rows.values(), key=lambda item: str(item["asset_pointer"]))


def _iso_from_epoch(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (OSError, OverflowError, TypeError, ValueError):
        return str(value).strip() or None


def conversation_records_v16311(graphs: Iterable[ConversationGraph]) -> Iterator[IntermediateRecord]:
    for graph in graphs:
        for node in graph.nodes:
            if not (node.text or "").strip():
                continue
            message = _raw_message(graph, node.node_id)
            visibility, eligible = _visibility(node, message)
            assets = _asset_rows(node, message)
            source_record_id = str(node.message_id or node.node_id)
            event_time = _iso_from_epoch(node.create_time)
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
                    "assets": assets,
                },
                provenance={
                    "conversation_id": graph.conversation_id,
                    "conversation_semantic_tree_sha256": graph.semantic_tree_sha256,
                    "conversation_raw_tree_sha256": graph.raw_tree_sha256,
                    "node_id": node.node_id,
                    "message_id": node.message_id,
                },
            )


def _source_member(info: Mapping[str, Any]) -> str:
    members = info.get("conversation_members")
    if isinstance(members, (list, tuple)) and members:
        return "|".join(str(item) for item in members)
    return str(info.get("html_member") or info.get("conversations_member") or "")


@contextmanager
def _graph_source(source: str | Path) -> Iterator[tuple[Iterator[ConversationGraph], dict[str, Any]]]:
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_file() and path.suffix.casefold() in {".html", ".htm"}:
        raw, member, mode, warnings = read_html_conversations(path)
        info = {
            "path": str(path),
            "source_name": path.name,
            "source_kind": "html",
            "source_sha256": sha256_file(path),
            "html_member": member,
            "conversation_members": [],
            "mode": mode,
            "warnings": list(warnings),
        }
        yield (build_conversation_graph(item) for item in raw), info
        return
    with ChatExportReader(path, verify_crc=True) as reader:
        info = reader.info.to_dict()
        info["source_sha256"] = reader.info.sha256
        info["mode"] = "canonical_json"
        yield reader.iter_graphs(), info


def build_conversation_graph(raw: dict[str, Any]) -> ConversationGraph:
    # Local indirection keeps imports cycle-safe when html_import imports this package.
    from latka_jazn.tools.chat_export_reader import build_conversation_graph as build

    return build(raw)


def _summary(graph: ConversationGraph) -> dict[str, Any]:
    return {
        "conversation_id": graph.conversation_id,
        "title": graph.title,
        "create_time": graph.create_time,
        "update_time": graph.update_time,
        "first_message_time": graph.first_message_time,
        "last_message_time": graph.last_message_time,
        "node_count": graph.node_count,
        "message_count": graph.message_count,
        "branch_point_count": len(graph.branch_points),
        "raw_tree_sha256": graph.raw_tree_sha256,
        "semantic_tree_sha256": graph.semantic_tree_sha256,
    }


def list_chat_conversations(source: str | Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with _graph_source(source) as (graphs, info):
        for graph in graphs:
            rows.append(_summary(graph))
    return {
        "ok": True,
        "source": str(Path(source).expanduser().resolve()),
        "source_sha256": info.get("source_sha256"),
        "mode": info.get("mode"),
        "conversation_count": len(rows),
        "conversations": rows,
        "warnings": list(info.get("warnings") or []),
    }


def _parse_time_bound(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _graph_time(graph: ConversationGraph) -> float | None:
    return graph.create_time or graph.first_message_time or graph.update_time or graph.last_message_time


def _select_graphs(
    source: str | Path,
    *,
    conversation_ids: Sequence[str] = (),
    title: str | None = None,
    temporal_start: str | None = None,
    temporal_end: str | None = None,
) -> tuple[list[ConversationGraph], dict[str, Any], dict[str, Any]]:
    wanted = {str(item).strip() for item in conversation_ids if str(item).strip()}
    title_query = str(title or "").strip().casefold()
    start = _parse_time_bound(temporal_start)
    end = _parse_time_bound(temporal_end)
    if start is not None and end is not None and start > end:
        raise ValueError("conversation_time_start_after_end")
    selected: list[ConversationGraph] = []
    seen_ids: set[str] = set()
    with _graph_source(source) as (graphs, info):
        for graph in graphs:
            seen_ids.add(graph.conversation_id)
            if wanted and graph.conversation_id not in wanted:
                continue
            if title_query and title_query not in graph.title.casefold():
                continue
            event = _graph_time(graph)
            if start is not None and (event is None or event < start):
                continue
            if end is not None and (event is None or event > end):
                continue
            selected.append(graph)
    missing_ids = sorted(wanted - seen_ids)
    selector = {
        "conversation_ids": sorted(wanted),
        "title": title or None,
        "temporal_start": temporal_start,
        "temporal_end": temporal_end,
        "missing_requested_conversation_ids": missing_ids,
    }
    if missing_ids:
        raise ValueError("requested_conversation_ids_missing:" + ",".join(missing_ids))
    if not selected:
        raise ValueError("conversation_selector_matched_nothing")
    return selected, info, selector


def _hash_map(source: str | Path) -> tuple[dict[str, str], dict[str, Any]]:
    hashes: dict[str, str] = {}
    with _graph_source(source) as (graphs, info):
        for graph in graphs:
            hashes[graph.conversation_id] = graph.semantic_tree_sha256
    return hashes, info


def compare_chat_sources(
    primary: str | Path,
    control: str | Path,
    *,
    conversation_ids: Sequence[str] = (),
) -> dict[str, Any]:
    primary_map, primary_info = _hash_map(primary)
    control_map, control_info = _hash_map(control)
    requested = {str(item).strip() for item in conversation_ids if str(item).strip()}
    strict = str(control_info.get("mode")) != "rendered_html_fallback"
    scope = requested or set(primary_map)
    missing_primary = sorted(scope - set(primary_map))
    missing_control = sorted(scope - set(control_map))
    mismatched = sorted(
        conversation_id
        for conversation_id in (scope & set(primary_map) & set(control_map))
        if primary_map[conversation_id] != control_map[conversation_id]
    )
    extra_control = sorted(set(control_map) - set(primary_map)) if not requested else []
    ok = strict and not missing_primary and not missing_control and not mismatched and not extra_control
    return {
        "ok": ok,
        "strict": strict,
        "primary": str(Path(primary).expanduser().resolve()),
        "control": str(Path(control).expanduser().resolve()),
        "primary_mode": primary_info.get("mode"),
        "control_mode": control_info.get("mode"),
        "requested_conversation_ids": sorted(requested),
        "checked_conversation_count": len(scope - set(missing_primary) - set(missing_control)),
        "missing_primary": missing_primary,
        "missing_control": missing_control,
        "semantic_mismatches": mismatched,
        "extra_control": extra_control,
        "reason": (
            "semantic_graphs_match"
            if ok
            else "rendered_html_is_not_lossless_control"
            if not strict
            else "chat_source_control_mismatch"
        ),
    }


def _compressed_payload(graph: ConversationGraph) -> tuple[bytes, int]:
    raw = json.dumps(
        graph.source_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return zlib.compress(raw, level=6), len(raw)


def _store_l0_conversation_variants(
    database: Path,
    source_id: str,
    graphs: Sequence[ConversationGraph],
) -> None:
    now = _utc_now()
    with sqlite3.connect(database, timeout=30) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        _ensure_extended_l0_schema(con)
        for graph in graphs:
            existing = con.execute(
                """SELECT variant_id,revision FROM memory_l0_conversations
                   WHERE conversation_id=? AND semantic_tree_sha256=? AND source_id=?""",
                (graph.conversation_id, graph.semantic_tree_sha256, source_id),
            ).fetchone()
            if existing is not None:
                continue
            revision = int(
                con.execute(
                    "SELECT COALESCE(MAX(revision),0)+1 FROM memory_l0_conversations WHERE conversation_id=?",
                    (graph.conversation_id,),
                ).fetchone()[0]
            )
            compressed, raw_size = _compressed_payload(graph)
            con.execute(
                "UPDATE memory_l0_conversations SET is_current_revision=0 WHERE conversation_id=?",
                (graph.conversation_id,),
            )
            variant_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jazn-l0-conversation:{graph.conversation_id}:{revision}:{graph.semantic_tree_sha256}:{source_id}",
            ))
            con.execute(
                """INSERT INTO memory_l0_conversations(
                   variant_id,conversation_id,revision,source_id,title,create_time,update_time,current_node_id,
                   raw_tree_sha256,semantic_tree_sha256,node_count,message_count,branch_point_count,
                   payload_codec,payload_blob,payload_size_uncompressed,created_at_utc,is_current_revision
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    variant_id, graph.conversation_id, revision, source_id, graph.title,
                    graph.create_time, graph.update_time, graph.current_node_id,
                    graph.raw_tree_sha256, graph.semantic_tree_sha256, graph.node_count,
                    graph.message_count, len(graph.branch_points), PAYLOAD_CODEC,
                    sqlite3.Binary(compressed), raw_size, now,
                ),
            )
        con.commit()


def import_selected_conversations(
    store: Any,
    source: str | Path,
    *,
    conversation_ids: Sequence[str] = (),
    title: str | None = None,
    temporal_start: str | None = None,
    temporal_end: str | None = None,
    html_control: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    store.ensure_initialized()
    path = Path(source).expanduser().resolve()
    selected, info, selector = _select_graphs(
        path,
        conversation_ids=conversation_ids,
        title=title,
        temporal_start=temporal_start,
        temporal_end=temporal_end,
    )
    selected_ids = [graph.conversation_id for graph in selected]
    control: dict[str, Any] = {}
    if html_control is not None:
        control = compare_chat_sources(path, html_control, conversation_ids=selected_ids)
        if not control.get("ok"):
            raise ValueError("html_control_failed:" + str(control.get("reason")))

    if dry_run:
        return {
            "ok": True,
            "status": "planned",
            "source": str(path),
            "selected_conversation_count": len(selected),
            "selected_conversations": [_summary(graph) for graph in selected],
            "selector": selector,
            "control": control,
            "automatic_l2": False,
            "automatic_l3": False,
            "automatic_activation": False,
        }

    source_sha = str(info.get("source_sha256") or "")
    if not source_sha:
        source_sha = sha256_file(path)
    member = _source_member(info)

    def records() -> Iterator[IntermediateRecord]:
        yield from conversation_records_v16311(iter(selected))

    prepared = PreparedSource(
        adapter_id=SELECTIVE_ADAPTER_ID,
        source_kind="chatgpt_conversation",
        source_sha256=source_sha,
        source_name=path.name,
        source_member=member,
        metadata={
            "source_mode": info.get("mode"),
            "selector": selector,
            "selected_conversation_ids": selected_ids,
            "html_control": control,
            "truth_boundary": "Selective import stores source evidence only; no automatic L2/L3 promotion.",
        },
        record_factory=records,
        native_projection="l0_only",
    )
    common = UnifiedL0Store(store.path).ingest(prepared, dry_run=False)
    with sqlite3.connect(store.path, timeout=30) as con:
        con.row_factory = sqlite3.Row
        source_row = con.execute(
            """SELECT source_id FROM memory_l0_sources
               WHERE adapter_id=? AND source_sha256=? AND source_member=?""",
            (prepared.adapter_id, prepared.source_sha256, prepared.source_member or ""),
        ).fetchone()
        if source_row is None:
            raise RuntimeError("selective_l0_source_registration_missing")
        source_id = str(source_row["source_id"])
    _store_l0_conversation_variants(store.path, source_id, selected)
    with sqlite3.connect(store.path, timeout=30) as con:
        con.execute("PRAGMA foreign_keys=ON")
        _ensure_extended_l0_schema(con)
        con.execute(
            """INSERT INTO memory_l0_imports(
               import_id,source_id,imported_at_utc,mode,selector_json,control_json,
               conversation_count,truth_boundary
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()), source_id, _utc_now(), "selective_chat_import",
                canonical_json(selector), canonical_json(control), len(selected),
                "Full selected conversation variants are retained as L0 source evidence; L2/L3 remain review-gated.",
            ),
        )
        con.commit()
    return {
        "ok": bool(common.get("ok")),
        "status": "imported",
        "source": str(path),
        "source_sha256": source_sha,
        "selected_conversation_count": len(selected),
        "selected_conversation_ids": selected_ids,
        "selector": selector,
        "control": control,
        "intermediate_model": common,
        "automatic_l2": False,
        "automatic_l3": False,
        "automatic_activation": False,
    }


def _record_metadata_after_ingest(store: UnifiedL0Store, prepared: PreparedSource) -> None:
    now = _utc_now()
    with store._connect() as con:  # noqa: SLF001 - extension of the same storage component
        _ensure_extended_l0_schema(con)
        source_row = con.execute(
            """SELECT source_id FROM memory_l0_sources
               WHERE adapter_id=? AND source_sha256=? AND source_member=?""",
            (prepared.adapter_id, prepared.source_sha256, prepared.source_member or ""),
        ).fetchone()
        if source_row is None:
            return
        source_id = str(source_row["source_id"])
        for record in prepared.iter_records():
            row = con.execute(
                """SELECT record_id FROM memory_l0_records
                   WHERE logical_key=? AND is_current_revision=1""",
                (record.logical_key,),
            ).fetchone()
            if row is None:
                continue
            record_id = str(row["record_id"])
            visibility = str(record.raw.get("visibility") or "visible")
            eligible = bool(record.raw.get("memory_eligible", True))
            con.execute(
                "UPDATE memory_l0_records SET visibility=?,memory_eligible=? WHERE record_id=?",
                (visibility, int(eligible), record_id),
            )
            assets = record.raw.get("assets")
            if not isinstance(assets, list):
                continue
            for asset in assets:
                if not isinstance(asset, Mapping):
                    continue
                pointer = str(asset.get("asset_pointer") or "").strip()
                if not pointer:
                    continue
                con.execute(
                    """INSERT INTO memory_l0_assets(
                       asset_pointer,original_filename,content_type,mime_type,availability_status,
                       file_sha256,first_seen_source_id,last_seen_source_id,first_seen_at_utc,last_seen_at_utc
                       ) VALUES(?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(asset_pointer) DO UPDATE SET
                         original_filename=COALESCE(excluded.original_filename,memory_l0_assets.original_filename),
                         content_type=COALESCE(excluded.content_type,memory_l0_assets.content_type),
                         mime_type=COALESCE(excluded.mime_type,memory_l0_assets.mime_type),
                         availability_status=excluded.availability_status,
                         file_sha256=COALESCE(excluded.file_sha256,memory_l0_assets.file_sha256),
                         last_seen_source_id=excluded.last_seen_source_id,
                         last_seen_at_utc=excluded.last_seen_at_utc""",
                    (
                        pointer,
                        asset.get("original_filename"),
                        asset.get("content_type"),
                        asset.get("mime_type"),
                        str(asset.get("availability_status") or "referenced_only"),
                        asset.get("file_sha256"),
                        source_id,
                        source_id,
                        now,
                        now,
                    ),
                )
                con.execute(
                    "INSERT OR IGNORE INTO memory_l0_record_assets(record_id,asset_pointer) VALUES(?,?)",
                    (record_id, pointer),
                )
        con.commit()


def _archive_variant(self: ChatExportArchiveStore, import_id: str, graph: ConversationGraph, relation: str) -> None:
    compressed, raw_size = _compressed_payload(graph)
    variant_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"jazn-chat-archive-variant:{graph.conversation_id}:{import_id}:{graph.semantic_tree_sha256}",
    ))
    self.con.execute(
        """INSERT OR IGNORE INTO conversation_variant_payloads(
           variant_id,conversation_id,import_id,relation_to_active,raw_tree_sha256,
           semantic_tree_sha256,payload_codec,payload_blob,payload_size_uncompressed,created_at_utc
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            variant_id, graph.conversation_id, import_id, relation, graph.raw_tree_sha256,
            graph.semantic_tree_sha256, PAYLOAD_CODEC, sqlite3.Binary(compressed), raw_size, _utc_now(),
        ),
    )


def _update_archive_visibility(self: ChatExportArchiveStore, graph: ConversationGraph) -> None:
    for node in graph.nodes:
        message = _raw_message(graph, node.node_id)
        visibility, eligible = _visibility(node, message)
        self.con.execute(
            """UPDATE nodes SET visibility=?,memory_eligible=?
               WHERE conversation_id=? AND node_id=?""",
            (visibility, int(eligible), graph.conversation_id, node.node_id),
        )


def apply() -> None:
    if getattr(UnifiedL0Store, "_JAZN_V16311_HARDENING_APPLIED", False):
        return

    from . import adapters as adapters_package
    from .adapters import common as common_adapter
    from .adapters import chatgpt_json as json_adapter
    from .adapters import html as html_adapter
    from .typed_api import TypedMemoryAPI
    from .unified_core import UnifiedCoreMixin

    original_ensure_schema = UnifiedL0Store.ensure_schema
    original_ingest = UnifiedL0Store.ingest
    original_archive_init = ChatExportArchiveStore.__init__
    original_store_graph = ChatExportArchiveStore.store_graph
    original_l0_hits = TypedMemoryAPI._l0_hits

    def ensure_schema(self: UnifiedL0Store, con: sqlite3.Connection | None = None) -> None:
        original_ensure_schema(self, con)
        owns = con is None
        connection = con or self._connect()
        try:
            _ensure_extended_l0_schema(connection)
            if owns:
                connection.commit()
        finally:
            if owns:
                connection.close()

    def ingest(self: UnifiedL0Store, prepared: PreparedSource, *, dry_run: bool = False) -> dict[str, Any]:
        result = original_ingest(self, prepared, dry_run=dry_run)
        if not dry_run:
            _record_metadata_after_ingest(self, prepared)
        result["schema_version"] = EXTENDED_L0_SCHEMA_VERSION
        result["visibility_classification"] = True
        result["attachment_catalog"] = True
        return result

    def archive_init(self: ChatExportArchiveStore, *args: Any, **kwargs: Any) -> None:
        original_archive_init(self, *args, **kwargs)
        _ensure_archive_extension(self.con)

    def store_graph(self: ChatExportArchiveStore, import_id: str, graph: ConversationGraph, plan: Any) -> dict[str, int]:
        counters = original_store_graph(self, import_id, graph, plan)
        _ensure_archive_extension(self.con)
        _archive_variant(self, import_id, graph, str(plan.relation))
        if str(plan.relation) == "divergent" and plan.added_node_ids:
            added = set(str(item) for item in plan.added_node_ids)
            new_nodes = [node for node in graph.nodes if node.node_id in added]
            if new_nodes:
                delta = self._insert_nodes(import_id, graph, new_nodes)  # noqa: SLF001
                for key, value in delta.items():
                    counters[key] = counters.get(key, 0) + int(value)
                self.con.execute(
                    """UPDATE conversations
                       SET node_count=node_count+?, message_count=message_count+?,
                           last_seen_import_id=?, updated_at_utc=?
                       WHERE conversation_id=?""",
                    (
                        len(new_nodes),
                        sum(1 for node in new_nodes if node.message_id),
                        import_id,
                        _utc_now(),
                        graph.conversation_id,
                    ),
                )
        _update_archive_visibility(self, graph)
        return counters

    def eligible_l0_hits(self: Any, con: sqlite3.Connection, query: Any) -> list[Any]:
        if "memory_eligible" not in _table_columns(con, "memory_l0_records"):
            return original_l0_hits(self, con, query)
        expanded = replace(query, limit=min(500, max(int(query.limit) * 8, int(query.limit))))
        hits = original_l0_hits(self, con, expanded)
        if not hits:
            return hits
        ids = [str(hit.record_id) for hit in hits]
        placeholders = ",".join("?" for _ in ids)
        eligible = {
            str(row[0])
            for row in con.execute(
                f"SELECT record_id FROM memory_l0_records WHERE memory_eligible=1 AND record_id IN ({placeholders})",
                ids,
            ).fetchall()
        }
        return [hit for hit in hits if str(hit.record_id) in eligible][: int(query.limit)]

    def import_source_selected(
        self: Any,
        source: str | Path,
        *,
        conversation_ids: Sequence[str] = (),
        title: str | None = None,
        temporal_start: str | None = None,
        temporal_end: str | None = None,
        html_control: str | Path | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return import_selected_conversations(
            self,
            source,
            conversation_ids=conversation_ids,
            title=title,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            html_control=html_control,
            dry_run=dry_run,
        )

    UnifiedL0Store.ensure_schema = ensure_schema
    UnifiedL0Store.ingest = ingest
    ChatExportArchiveStore.__init__ = archive_init
    ChatExportArchiveStore.store_graph = store_graph
    TypedMemoryAPI._l0_hits = eligible_l0_hits
    setattr(UnifiedCoreMixin, "import_source_selected", import_source_selected)

    # Adapters imported conversation_records by name, so update all aliases.
    common_adapter.conversation_records = conversation_records_v16311
    json_adapter.conversation_records = conversation_records_v16311
    html_adapter.conversation_records = conversation_records_v16311
    setattr(adapters_package, "conversation_records_v16311", conversation_records_v16311)

    setattr(UnifiedL0Store, "_JAZN_V16311_HARDENING_APPLIED", True)


__all__ = [
    "EXTENDED_L0_SCHEMA_VERSION",
    "HARDENING_VERSION",
    "SELECTIVE_ADAPTER_ID",
    "apply",
    "compare_chat_sources",
    "conversation_records_v16311",
    "import_selected_conversations",
    "list_chat_conversations",
]
