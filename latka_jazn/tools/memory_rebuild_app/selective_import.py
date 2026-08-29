from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence
import json
import sqlite3
import uuid
import zlib

from latka_jazn.tools.chat_export_models import ConversationGraph

from .adapters.common import conversation_records
from .chat_sources import compare_chat_sources, graph_source
from .intermediate import IntermediateRecord, PreparedSource, canonical_json, sha256_file
from .l0_store import UnifiedL0Store
from .schema_l0 import ensure_l0_schema_extensions


SELECTIVE_ADAPTER_ID = "chat-selective/v4"
PAYLOAD_CODEC = "zlib-json-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _parse_time_bound(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
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
    with graph_source(source) as (graphs, info):
        for graph in graphs:
            seen_ids.add(graph.conversation_id)
            event = _graph_time(graph)
            if wanted and graph.conversation_id not in wanted:
                continue
            if title_query and title_query not in graph.title.casefold():
                continue
            if start is not None and (event is None or event < start):
                continue
            if end is not None and (event is None or event > end):
                continue
            selected.append(graph)
    missing = sorted(wanted - seen_ids)
    selector = {
        "conversation_ids": sorted(wanted),
        "title": title or None,
        "temporal_start": temporal_start,
        "temporal_end": temporal_end,
        "missing_requested_conversation_ids": missing,
    }
    if missing:
        raise ValueError("requested_conversation_ids_missing:" + ",".join(missing))
    if not selected:
        raise ValueError("conversation_selector_matched_nothing")
    return selected, info, selector


def _source_member(info: dict[str, Any]) -> str:
    members = info.get("conversation_members")
    if isinstance(members, (list, tuple)) and members:
        return "|".join(str(item) for item in members)
    return str(info.get("html_member") or info.get("conversations_member") or "")


def _store_variants(database: Path, source_id: str, graphs: Sequence[ConversationGraph]) -> None:
    now = _utc_now()
    with sqlite3.connect(database, timeout=30) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        ensure_l0_schema_extensions(con)
        for graph in graphs:
            exists = con.execute(
                """SELECT 1 FROM memory_l0_conversations
                   WHERE conversation_id=? AND semantic_tree_sha256=? AND source_id=?""",
                (graph.conversation_id, graph.semantic_tree_sha256, source_id),
            ).fetchone()
            if exists is not None:
                continue
            revision = int(con.execute(
                "SELECT COALESCE(MAX(revision),0)+1 FROM memory_l0_conversations WHERE conversation_id=?",
                (graph.conversation_id,),
            ).fetchone()[0])
            raw = json.dumps(
                graph.source_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
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
                    variant_id,
                    graph.conversation_id,
                    revision,
                    source_id,
                    graph.title,
                    graph.create_time,
                    graph.update_time,
                    graph.current_node_id,
                    graph.raw_tree_sha256,
                    graph.semantic_tree_sha256,
                    graph.node_count,
                    graph.message_count,
                    len(graph.branch_points),
                    PAYLOAD_CODEC,
                    sqlite3.Binary(zlib.compress(raw, level=6)),
                    len(raw),
                    now,
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

    source_sha = str(info.get("source_sha256") or (sha256_file(path) if path.is_file() else ""))
    if not source_sha:
        raise ValueError("selective_source_sha256_missing")

    def records() -> Iterator[IntermediateRecord]:
        yield from conversation_records(iter(selected))

    prepared = PreparedSource(
        adapter_id=SELECTIVE_ADAPTER_ID,
        source_kind="chatgpt_conversation",
        source_sha256=source_sha,
        source_name=path.name,
        source_member=_source_member(info),
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
    _store_variants(store.path, source_id, selected)
    with sqlite3.connect(store.path, timeout=30) as con:
        con.execute("PRAGMA foreign_keys=ON")
        ensure_l0_schema_extensions(con)
        con.execute(
            """INSERT INTO memory_l0_imports(
               import_id,source_id,imported_at_utc,mode,selector_json,control_json,
               conversation_count,truth_boundary
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()),
                source_id,
                _utc_now(),
                "selective_chat_import",
                canonical_json(selector),
                canonical_json(control),
                len(selected),
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


__all__ = ["SELECTIVE_ADAPTER_ID", "import_selected_conversations"]
