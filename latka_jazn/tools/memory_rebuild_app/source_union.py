from __future__ import annotations

"""Order-independent source-set closure for ChatGPT export snapshots."""

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable
import json
import os

from latka_jazn.tools.chat_export_dedupe import stable_node_hash
from latka_jazn.tools.chat_export_reader import (
    ChatExportReader,
    build_conversation_graph,
    probe_json_source_kind,
    sha256_file,
)

from .html_import import read_html_conversations


SOURCE_UNION_SCHEMA = "jazn_memory_rebuild_source_union/v1"
TOOL_REVISION = "15.3.23.01"
TOOL_RELEASE_LABEL = "15.3.23.01 - Poprawione narzędzie odbudowy pamięci"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_sha(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(data.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def _read_source(path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash = sha256_file(source)
    suffix = source.suffix.casefold()
    mode = "ignored"
    priority = 99
    warnings: tuple[str, ...] = ()
    graphs = ()

    if suffix == ".json":
        kind = probe_json_source_kind(source)
        if kind != "conversation":
            return {
                "path": source,
                "sha256": source_hash,
                "mode": f"sidecar_json:{kind}",
                "priority": priority,
                "graphs": graphs,
                "warnings": warnings,
                "ignored_reason": "non_conversation_json",
            }
        with ChatExportReader(source, verify_crc=False) as reader:
            graphs = tuple(reader.iter_graphs())
            warnings = reader.record_warnings
        mode = "canonical_json"
        priority = 0
    elif suffix in {".html", ".htm"}:
        records, _member, html_mode, warnings = read_html_conversations(source)
        graphs = tuple(build_conversation_graph(item) for item in records)
        mode = html_mode
        priority = 1 if html_mode == "embedded_json" else 2
    elif suffix == ".zip":
        with ChatExportReader(source, verify_crc=True) as reader:
            if reader.info.conversation_members:
                graphs = tuple(reader.iter_graphs())
                warnings = reader.record_warnings
                mode = "canonical_json_in_zip"
                priority = 0
            elif reader.info.html_member:
                records, _member, html_mode, warnings = read_html_conversations(source)
                graphs = tuple(build_conversation_graph(item) for item in records)
                mode = f"html_in_zip:{html_mode}"
                priority = 1 if html_mode == "embedded_json" else 2
    return {
        "path": source,
        "sha256": source_hash,
        "mode": mode,
        "priority": priority,
        "graphs": graphs,
        "warnings": warnings,
        "ignored_reason": None if graphs else "no_lossless_conversation_graph",
    }


def _variant(source: dict[str, Any], graph: Any) -> dict[str, Any]:
    return {
        "source_sha256": source["sha256"],
        "source_mode": source["mode"],
        "semantic_tree_sha256": graph.semantic_tree_sha256,
        "raw_tree_sha256": graph.raw_tree_sha256,
        "node_ids": frozenset(node.node_id for node in graph.nodes),
        "message_node_ids": frozenset(node.node_id for node in graph.nodes if node.message_id),
        "message_hashes": {node.node_id: stable_node_hash(node) for node in graph.nodes},
        "parents": {node.node_id: node.parent_node_id for node in graph.nodes},
        "branch_points": frozenset(graph.branch_points),
    }


def _relation(variants: list[dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    if len(variants) <= 1:
        return "single", [], []
    message_versions: dict[str, set[str]] = defaultdict(set)
    parent_versions: dict[str, set[str | None]] = defaultdict(set)
    for variant in variants:
        for node_id, digest in variant["message_hashes"].items():
            message_versions[node_id].add(digest)
        for node_id, parent in variant["parents"].items():
            parent_versions[node_id].add(parent)
    changed_messages = sorted(node_id for node_id, values in message_versions.items() if len(values) > 1)
    changed_parents = sorted(node_id for node_id, values in parent_versions.items() if len(values) > 1)
    if changed_messages or changed_parents:
        return "conflict", changed_messages, changed_parents
    node_sets = [variant["node_ids"] for variant in variants]
    comparable = all(a <= b or b <= a for index, a in enumerate(node_sets) for b in node_sets[index + 1 :])
    return ("extension_family" if comparable else "branch_union"), [], []


def _union_branch_points(variants: list[dict[str, Any]]) -> set[str]:
    children_by_parent: dict[str, set[str]] = defaultdict(set)
    for variant in variants:
        for node_id, parent in variant["parents"].items():
            if parent is not None:
                children_by_parent[parent].add(node_id)
    return {parent for parent, children in children_by_parent.items() if len(children) > 1}


def _variant_cover(
    sources: list[dict[str, Any]],
    requirements: set[tuple[str, str]],
    by_source: dict[str, set[tuple[str, str]]],
) -> list[str]:
    uncovered = set(requirements)
    chosen: list[str] = []
    source_map = {item["sha256"]: item for item in sources}
    while uncovered:
        candidates = []
        for source_sha, values in by_source.items():
            gain = len(uncovered & values)
            if gain and source_sha not in chosen:
                candidates.append((-gain, int(source_map[source_sha]["priority"]), source_sha))
        if not candidates:
            break
        _gain, _priority, selected = min(candidates)
        chosen.append(selected)
        uncovered.difference_update(by_source[selected])
    return chosen


def build_source_union_manifest(sources: Iterable[str | Path]) -> dict[str, Any]:
    """Union every unique semantic conversation variant; never infer truth from size/order/name."""

    paths: list[Path] = []
    seen: set[str] = set()
    for raw in sources:
        path = Path(raw).expanduser().resolve()
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            paths.append(path)

    observations: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in paths:
        try:
            observations.append(_read_source(path))
        except Exception as exc:
            errors.append({"path": str(path), "error_type": type(exc).__name__, "error": str(exc)})

    chat_sources = [item for item in observations if item["graphs"]]
    lossless = [item for item in chat_sources if "rendered_html_fallback" not in item["mode"]]
    lossy = [item for item in chat_sources if item not in lossless]
    conversations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_source: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for source in lossless:
        for graph in source["graphs"]:
            item = _variant(source, graph)
            conversations[graph.conversation_id].append(item)
            by_source[source["sha256"]].add((graph.conversation_id, graph.semantic_tree_sha256))

    rows: list[dict[str, Any]] = []
    requirements: set[tuple[str, str]] = set()
    union_nodes = union_messages = union_branches = variants_total = 0
    extension_count = branch_union_count = conflict_count = 0
    changed_messages_total = changed_parents_total = 0
    for conversation_id in sorted(conversations):
        deduped = {item["semantic_tree_sha256"]: item for item in conversations[conversation_id]}
        variants = [deduped[key] for key in sorted(deduped)]
        relation, changed_messages, changed_parents = _relation(variants)
        nodes = set().union(*(item["node_ids"] for item in variants))
        message_nodes = set().union(*(item["message_node_ids"] for item in variants))
        branches = _union_branch_points(variants)
        for item in variants:
            requirements.add((conversation_id, item["semantic_tree_sha256"]))
        union_nodes += len(nodes)
        union_messages += len(message_nodes)
        union_branches += len(branches)
        variants_total += len(variants)
        extension_count += int(relation == "extension_family")
        branch_union_count += int(relation == "branch_union")
        conflict_count += int(relation == "conflict")
        changed_messages_total += len(changed_messages)
        changed_parents_total += len(changed_parents)
        rows.append(
            {
                "conversation_id": conversation_id,
                "relation": relation,
                "variant_count": len(variants),
                "semantic_tree_sha256": [item["semantic_tree_sha256"] for item in variants],
                "raw_tree_sha256": [item["raw_tree_sha256"] for item in variants],
                "source_sha256": sorted({item["source_sha256"] for item in conversations[conversation_id]}),
                "union_node_count": len(nodes),
                "union_message_node_count": len(message_nodes),
                "union_branch_point_count": len(branches),
                "changed_message_node_ids": changed_messages,
                "changed_parent_node_ids": changed_parents,
            }
        )

    fingerprint = _canonical_sha(
        [
            {
                "conversation_id": row["conversation_id"],
                "relation": row["relation"],
                "semantic_tree_sha256": row["semantic_tree_sha256"],
                "union_node_count": row["union_node_count"],
                "union_message_node_count": row["union_message_node_count"],
                "union_branch_point_count": row["union_branch_point_count"],
                "changed_message_node_ids": row["changed_message_node_ids"],
                "changed_parent_node_ids": row["changed_parent_node_ids"],
            }
            for row in rows
        ]
    )
    cover = _variant_cover(lossless, requirements, by_source)
    cover_set = set(cover)
    source_rows = [
        {
            "path": str(item["path"]),
            "source_sha256": item["sha256"],
            "mode": item["mode"],
            "conversation_count": len(item["graphs"]),
            "ignored_reason": item["ignored_reason"],
            "warning_count": len(item["warnings"]),
        }
        for item in sorted(observations, key=lambda value: (value["priority"], value["sha256"]))
    ]
    ready = bool(lossless) and not errors
    return {
        "schema_version": SOURCE_UNION_SCHEMA,
        "tool_revision": TOOL_REVISION,
        "generated_at_utc": _utc_now(),
        "ok": ready,
        "status": "ready" if ready else ("source_error" if errors else "no_lossless_chat_sources"),
        "source_count": len(observations),
        "lossless_chat_source_count": len(lossless),
        "lossy_chat_source_count": len(lossy),
        "ignored_non_chat_source_count": sum(1 for item in observations if item["ignored_reason"]),
        "unique_conversation_count": len(rows),
        "unique_conversation_variant_count": variants_total,
        "union_node_count": union_nodes,
        "union_message_node_count": union_messages,
        "union_branch_point_count": union_branches,
        "extension_family_count": extension_count,
        "branch_union_count": branch_union_count,
        "projection_conflict_conversation_count": conflict_count,
        "changed_message_node_count": changed_messages_total,
        "changed_parent_node_count": changed_parents_total,
        "requires_projection_resolution": conflict_count > 0,
        "union_fingerprint_sha256": fingerprint,
        "deterministic_variant_cover_source_sha256": cover,
        "redundant_lossless_source_sha256": sorted(
            item["sha256"] for item in lossless if item["sha256"] not in cover_set
        ),
        "sources": source_rows,
        "conversations": rows,
        "errors": errors,
        "truth_boundary": (
            "Source union preserves variants; it never chooses autobiographical truth "
            "from filename, file size, or import order."
        ),
        "automatic_l2": False,
        "automatic_l3": False,
        "automatic_activation": False,
    }


def run_source_union_analysis(
    sources: Iterable[str | Path],
    *,
    output_root: str | Path,
) -> dict[str, Any]:
    report = build_source_union_manifest(sources)
    root = Path(output_root).expanduser().resolve()
    private_path = _write_json(root / "source-union.private.json", report)
    sanitized = {
        key: value
        for key, value in report.items()
        if key not in {"sources", "conversations", "errors"}
    }
    sanitized.update(
        {
            "private_paths_persisted": False,
            "conversation_ids_persisted": False,
            "raw_content_persisted": False,
            "source_error_count": len(report["errors"]),
        }
    )
    sanitized_path = _write_json(root / "source-union.sanitized.json", sanitized)
    return {
        **sanitized,
        "private_report": str(private_path),
        "sanitized_report": str(sanitized_path),
    }


__all__ = [
    "SOURCE_UNION_SCHEMA",
    "TOOL_RELEASE_LABEL",
    "TOOL_REVISION",
    "build_source_union_manifest",
    "run_source_union_analysis",
]
