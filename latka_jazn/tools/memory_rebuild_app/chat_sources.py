from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from latka_jazn.tools.chat_export_models import ConversationGraph
from latka_jazn.tools.chat_export_reader import ChatExportReader, build_conversation_graph, sha256_file

from .html_import import read_html_conversations
from .html_semantics import HtmlSemanticNormalizer


@contextmanager
def graph_source(source: str | Path) -> Iterator[tuple[Iterator[ConversationGraph], dict[str, Any]]]:
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_file() and path.suffix.casefold() in {".html", ".htm"}:
        raw, member, mode, warnings = read_html_conversations(path)
        yield (build_conversation_graph(item) for item in raw), {
            "path": str(path),
            "source_name": path.name,
            "source_kind": "html",
            "source_sha256": sha256_file(path),
            "html_member": member,
            "mode": mode,
            "warnings": list(warnings),
        }
        return
    with ChatExportReader(path, verify_crc=True) as reader:
        assets = reader.assets_map()
        normalizer = HtmlSemanticNormalizer()

        def semantic_graphs() -> Iterator[ConversationGraph]:
            for raw in reader.iter_raw_conversations():
                yield build_conversation_graph(normalizer.normalize(raw), assets_map=assets)

        info = reader.info.to_dict()
        info["source_sha256"] = reader.info.sha256
        info["mode"] = "canonical_json"
        yield semantic_graphs(), info


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
    with graph_source(source) as (graphs, info):
        rows = [_summary(graph) for graph in graphs]
    return {
        "ok": True,
        "source": str(Path(source).expanduser().resolve()),
        "source_sha256": info.get("source_sha256"),
        "mode": info.get("mode"),
        "conversation_count": len(rows),
        "conversations": rows,
        "warnings": list(info.get("warnings") or []),
    }


def _hash_map(source: str | Path) -> tuple[dict[str, str], dict[str, Any]]:
    with graph_source(source) as (graphs, info):
        return {graph.conversation_id: graph.semantic_tree_sha256 for graph in graphs}, info


def compare_chat_sources(
    primary: str | Path,
    control: str | Path,
    *,
    conversation_ids: Sequence[str] = (),
) -> dict[str, Any]:
    primary_map, primary_info = _hash_map(primary)
    control_map, control_info = _hash_map(control)
    requested = {str(item).strip() for item in conversation_ids if str(item).strip()}
    control_mode = str(control_info.get("mode"))
    strict = control_mode in {"canonical_json", "embedded_json_lossless"}
    scope = requested or set(primary_map)
    missing_primary = sorted(scope - set(primary_map))
    missing_control = sorted(scope - set(control_map))
    mismatched = sorted(
        key
        for key in scope & set(primary_map) & set(control_map)
        if primary_map[key] != control_map[key]
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


__all__ = ["compare_chat_sources", "graph_source", "list_chat_conversations"]
