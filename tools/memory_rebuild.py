#!/usr/bin/env python3
from __future__ import annotations

"""
Jaźń Memory Rebuild v2.4 — branch-only divergence safety hotfix.

HOTFIX:
    memory-rebuild/branch-union-v1

Purpose
-------
The canonical importer classifies two conversation trees as ``divergent`` when
both contain nodes absent from the other.  Historically every divergent case
was recorded in ``import_conflicts`` and neither branch was merged.

This launcher installs a narrow, fail-closed runtime patch before starting the
v2.4 application:

* a divergent conversation is auto-merged ONLY when ``changed_node_ids`` is
  empty and both trees contribute unique nodes;
* every shared node must retain the same stable semantic hash;
* every shared node must retain the same parent;
* parent/child links in the merged mapping must be consistent and acyclic;
* all source occurrences/revisions remain recorded;
* the canonical conversation payload becomes the deterministic union of both
  source trees;
* no automatic L2/L3 promotion is introduced;
* if any safety check fails, the original importer behaviour is used and the
  case remains an unresolved ``import_conflict``.

Important
---------
Use this hotfix for a FRESH rebuild target.  It does not silently delete or
rewrite conflicts already stored in an existing Test 03 database.
"""

from copy import deepcopy
from pathlib import Path
from typing import Any, Sequence
import hashlib
import importlib.util
import json
import math
import sys
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOTFIX_VERSION = "memory-rebuild/branch-union-v1"

_LEGACY_FLAGS = {
    "--legacy-five-db",
    "--config",
    "--write-example-config",
    "--no-ui",
    "--plan-only",
    "--all-discovered",
    "--source",
    "--self-test",
    "--confirm",
}

_LEGACY_MODULE = None


class BranchUnionUnsafe(RuntimeError):
    """The divergent pair cannot be merged without changing source meaning."""


def _legacy_path() -> Path:
    return Path(__file__).with_name("memory_rebuild_legacy_v24.py")


def _load_legacy_module():
    global _LEGACY_MODULE
    if _LEGACY_MODULE is not None:
        return _LEGACY_MODULE
    module_name = "_jazn_memory_rebuild_legacy_v24_compat"
    existing = sys.modules.get(module_name)
    if existing is not None:
        _LEGACY_MODULE = existing
        return existing
    path = _legacy_path()
    if not path.is_file():
        raise FileNotFoundError(f"Brak zgodnościowego narzędzia: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Nie można wczytać zgodnościowego narzędzia: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    _LEGACY_MODULE = module
    return module


def _expose_legacy_contract() -> None:
    """Expose the historical public API only when legacy mode is requested."""
    module = _load_legacy_module()
    for name in dir(module):
        if name.startswith("__") or name in {"main", "ROOT", "self_test"}:
            continue
        globals().setdefault(name, getattr(module, name))


# Preserve the original launcher's historical import-time public contract when
# the compatibility module is present (normal repository layout).  Standalone
# self-test copies may omit that adjacent file, so absence is tolerated here.
try:
    _expose_legacy_contract()
except FileNotFoundError:
    pass


def self_test(state):
    """Run the historical self-test while preserving the canonical filename."""
    module = _load_legacy_module()
    report = module.self_test(state)
    for check in report.get("checks", []):
        if check.get("name") == "canonical_filename":
            check["ok"] = Path(__file__).name == "memory_rebuild.py"
            check["value"] = Path(__file__).name
            break
    report["ok"] = all(bool(item.get("ok")) for item in report.get("checks", []))
    return report


def _legacy_requested(args: list[str]) -> bool:
    if args and args[0] == "legacy":
        return True
    return any(item in _LEGACY_FLAGS for item in args)


def _run_legacy(args: list[str]) -> int:
    _expose_legacy_contract()
    module = _load_legacy_module()
    cleaned = [item for item in args if item != "--legacy-five-db"]
    if cleaned and cleaned[0] == "legacy":
        cleaned = cleaned[1:]
    if "--self-test" in cleaned:
        parsed_args = module.build_parser().parse_args(cleaned)
        state = module._settings_from_args(
            parsed_args,
            module.load_state(parsed_args.config),
        )
        state.ui_mode = "text"
        return 0 if self_test(state).get("ok") else 2
    return int(module.main(cleaned))


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float("-inf")
    return result if math.isfinite(result) else float("-inf")


def _payload_preference_key(payload: dict[str, Any]) -> tuple[float, str]:
    # Latest source metadata wins.  Canonical JSON hash is a deterministic tie
    # breaker so the result does not depend on import order when update_time ties.
    return (_number(payload.get("update_time")), _sha256_json(payload))


def _node_parent(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("parent")
    return str(value) if value not in (None, "") else None


def _node_children(raw: Any) -> list[str]:
    if not isinstance(raw, dict):
        return []
    value = raw.get("children")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")]


def _ordered_union(primary: list[str], secondary: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in (*primary, *secondary):
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _deterministic_shared_node(
    active_raw: dict[str, Any],
    incoming_raw: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Prefer one complete raw representation deterministically.  The semantic
    # payload itself has already been checked separately; this only chooses which
    # volatile/raw metadata representation becomes the canonical base.
    if _sha256_json(incoming_raw) > _sha256_json(active_raw):
        return incoming_raw, active_raw
    return active_raw, incoming_raw


def _validate_parent_cycles(mapping: dict[str, Any]) -> None:
    for start in mapping:
        seen: set[str] = set()
        current = str(start)
        while current in mapping:
            if current in seen:
                raise BranchUnionUnsafe(
                    f"cycle detected in merged parent chain at node {current}"
                )
            seen.add(current)
            parent = _node_parent(mapping[current])
            if parent is None:
                break
            if parent not in mapping:
                raise BranchUnionUnsafe(
                    f"node {current} points to missing parent {parent}"
                )
            current = parent


def _validate_reciprocal_edges(mapping: dict[str, Any]) -> None:
    for node_id, raw in mapping.items():
        parent = _node_parent(raw)
        if parent is not None:
            parent_children = _node_children(mapping[parent])
            if str(node_id) not in parent_children:
                raise BranchUnionUnsafe(
                    f"parent {parent} does not list child {node_id}"
                )
        for child in _node_children(raw):
            if child not in mapping:
                raise BranchUnionUnsafe(
                    f"node {node_id} references missing child {child}"
                )
            child_parent = _node_parent(mapping[child])
            if child_parent != str(node_id):
                raise BranchUnionUnsafe(
                    f"child {child} has parent {child_parent!r}, expected {node_id!r}"
                )


def _merge_branch_only_payloads(
    active_payload: dict[str, Any],
    incoming_payload: dict[str, Any],
) -> dict[str, Any]:
    """Return a deterministic structural union of two compatible raw trees.

    This function intentionally does NOT decide semantic compatibility.  The
    installed store patch performs stable-node-hash checks before calling it.
    """
    if not isinstance(active_payload, dict) or not isinstance(incoming_payload, dict):
        raise BranchUnionUnsafe("both conversation payloads must be JSON objects")

    active_id = str(
        active_payload.get("id") or active_payload.get("conversation_id") or ""
    ).strip()
    incoming_id = str(
        incoming_payload.get("id") or incoming_payload.get("conversation_id") or ""
    ).strip()
    if not active_id or active_id != incoming_id:
        raise BranchUnionUnsafe("conversation IDs differ")

    active_mapping_raw = active_payload.get("mapping")
    incoming_mapping_raw = incoming_payload.get("mapping")
    if not isinstance(active_mapping_raw, dict) or not isinstance(
        incoming_mapping_raw, dict
    ):
        raise BranchUnionUnsafe("both payloads require mapping objects")

    active_mapping = {str(key): value for key, value in active_mapping_raw.items()}
    incoming_mapping = {
        str(key): value for key, value in incoming_mapping_raw.items()
    }
    if not active_mapping or not incoming_mapping:
        raise BranchUnionUnsafe("empty conversation mapping")

    shared = set(active_mapping) & set(incoming_mapping)
    active_only = set(active_mapping) - set(incoming_mapping)
    incoming_only = set(incoming_mapping) - set(active_mapping)
    if not active_only or not incoming_only:
        raise BranchUnionUnsafe(
            "branch-only merge requires unique nodes on both sides"
        )

    preferred_payload, fallback_payload = (
        (incoming_payload, active_payload)
        if _payload_preference_key(incoming_payload)
        > _payload_preference_key(active_payload)
        else (active_payload, incoming_payload)
    )
    merged = deepcopy(preferred_payload)

    # Preserve missing top-level metadata from the other source without replacing
    # explicit values from the preferred source.
    for key, value in fallback_payload.items():
        if key == "mapping":
            continue
        if key not in merged or merged[key] in (None, ""):
            merged[key] = deepcopy(value)

    merged_mapping: dict[str, Any] = {}
    for node_id in sorted(set(active_mapping) | set(incoming_mapping)):
        if node_id in shared:
            active_raw = active_mapping[node_id]
            incoming_raw = incoming_mapping[node_id]
            if not isinstance(active_raw, dict) or not isinstance(incoming_raw, dict):
                raise BranchUnionUnsafe(f"shared node {node_id} is not an object")
            active_parent = _node_parent(active_raw)
            incoming_parent = _node_parent(incoming_raw)
            if active_parent != incoming_parent:
                raise BranchUnionUnsafe(
                    f"shared node {node_id} changed parent: "
                    f"{active_parent!r} -> {incoming_parent!r}"
                )
            primary, secondary = _deterministic_shared_node(
                active_raw, incoming_raw
            )
            raw = deepcopy(primary)
            for key, value in secondary.items():
                if key not in raw:
                    raw[key] = deepcopy(value)
            raw["parent"] = active_parent
            raw["children"] = _ordered_union(
                _node_children(primary),
                _node_children(secondary),
            )
            merged_mapping[node_id] = raw
        elif node_id in active_mapping:
            merged_mapping[node_id] = deepcopy(active_mapping[node_id])
        else:
            merged_mapping[node_id] = deepcopy(incoming_mapping[node_id])

    # Parent pointers are the stronger structural assertion.  Ensure every child
    # is present in its parent's children list, but never invent/change a parent.
    for node_id, raw in list(merged_mapping.items()):
        if not isinstance(raw, dict):
            raise BranchUnionUnsafe(f"node {node_id} is not an object")
        parent = _node_parent(raw)
        if parent is None:
            continue
        if parent not in merged_mapping:
            raise BranchUnionUnsafe(
                f"node {node_id} points to missing parent {parent}"
            )
        parent_raw = merged_mapping[parent]
        if not isinstance(parent_raw, dict):
            raise BranchUnionUnsafe(f"parent node {parent} is not an object")
        children = _node_children(parent_raw)
        if node_id not in children:
            parent_raw["children"] = [*children, node_id]

    _validate_parent_cycles(merged_mapping)
    _validate_reciprocal_edges(merged_mapping)

    merged["mapping"] = merged_mapping

    # current_node is presentation/navigation state, not proof of truth. Prefer
    # the latest payload's current node if it still exists in the union.
    preferred_current = preferred_payload.get("current_node")
    fallback_current = fallback_payload.get("current_node")
    if preferred_current is not None and str(preferred_current) in merged_mapping:
        merged["current_node"] = str(preferred_current)
    elif fallback_current is not None and str(fallback_current) in merged_mapping:
        merged["current_node"] = str(fallback_current)
    else:
        merged["current_node"] = None

    create_times = [
        _number(active_payload.get("create_time")),
        _number(incoming_payload.get("create_time")),
    ]
    finite_create = [item for item in create_times if math.isfinite(item)]
    if finite_create:
        merged["create_time"] = min(finite_create)

    update_times = [
        _number(active_payload.get("update_time")),
        _number(incoming_payload.get("update_time")),
    ]
    finite_update = [item for item in update_times if math.isfinite(item)]
    if finite_update:
        merged["update_time"] = max(finite_update)

    return merged


def _is_branch_only_divergence(plan: Any) -> bool:
    return bool(
        getattr(plan, "relation", None) == "divergent"
        and not tuple(getattr(plan, "changed_node_ids", ()) or ())
        and tuple(getattr(plan, "added_node_ids", ()) or ())
        and tuple(getattr(plan, "missing_from_incoming_node_ids", ()) or ())
    )


def _install_branch_union_hotfix() -> None:
    """Patch ChatExportArchiveStore.store_graph for this process only."""
    from latka_jazn.tools.chat_export_dedupe import stable_node_hash
    from latka_jazn.tools.chat_export_reader import build_conversation_graph
    from latka_jazn.tools.chat_export_store import ChatExportArchiveStore

    if getattr(ChatExportArchiveStore, "_branch_union_hotfix_version", None):
        return

    original_store_graph = ChatExportArchiveStore.store_graph

    def patched_store_graph(self, import_id, graph, plan):
        if not _is_branch_only_divergence(plan):
            return original_store_graph(self, import_id, graph, plan)

        # Any unexpected structural condition falls back to the canonical
        # fail-closed path, which records import_conflicts exactly as before.
        try:
            active_payload = self.conversation_payload(graph.conversation_id)
            if active_payload is None:
                raise BranchUnionUnsafe("active payload is missing")

            active_graph = build_conversation_graph(active_payload)
            active_nodes = active_graph.node_index()
            incoming_nodes = graph.node_index()
            shared = set(active_nodes) & set(incoming_nodes)

            # Re-check semantic compatibility instead of trusting only the plan.
            semantic_changes = [
                node_id
                for node_id in shared
                if stable_node_hash(active_nodes[node_id])
                != stable_node_hash(incoming_nodes[node_id])
            ]
            if semantic_changes:
                raise BranchUnionUnsafe(
                    "shared node semantic content changed: "
                    + ",".join(sorted(semantic_changes)[:10])
                )

            parent_changes = [
                node_id
                for node_id in shared
                if active_nodes[node_id].parent_node_id
                != incoming_nodes[node_id].parent_node_id
            ]
            if parent_changes:
                raise BranchUnionUnsafe(
                    "shared node parent changed: "
                    + ",".join(sorted(parent_changes)[:10])
                )

            merged_payload = _merge_branch_only_payloads(
                active_payload, graph.source_payload
            )
            merged_graph = build_conversation_graph(merged_payload)

            expected_ids = set(active_nodes) | set(incoming_nodes)
            merged_ids = set(merged_graph.node_index())
            if merged_ids != expected_ids:
                raise BranchUnionUnsafe(
                    "merged node set differs from source union"
                )

            merged_index = merged_graph.node_index()
            for node_id in shared:
                if stable_node_hash(merged_index[node_id]) != stable_node_hash(
                    active_nodes[node_id]
                ):
                    raise BranchUnionUnsafe(
                        f"merged shared node {node_id} changed semantic content"
                    )

            now = __import__(
                "datetime", fromlist=["datetime"]
            ).datetime.now(__import__(
                "datetime", fromlist=["timezone"]
            ).timezone.utc).isoformat()

            raw = _json_bytes(merged_graph.source_payload)
            compressed = zlib.compress(raw, level=6)

            self.con.execute(
                """UPDATE conversations SET
                   title=?,create_time=?,update_time=?,current_node_id=?,
                   raw_tree_sha256=?,semantic_tree_sha256=?,payload_codec=?,
                   payload_blob=?,payload_size_uncompressed=?,
                   payload_size_compressed=?,node_count=?,message_count=?,
                   current_path_count=?,branch_point_count=?,
                   last_seen_import_id=?,revision=revision+1,updated_at_utc=?
                   WHERE conversation_id=?""",
                (
                    merged_graph.title,
                    merged_graph.create_time,
                    merged_graph.update_time,
                    merged_graph.current_node_id,
                    merged_graph.raw_tree_sha256,
                    merged_graph.semantic_tree_sha256,
                    "zlib-json-v1",
                    compressed,
                    len(raw),
                    len(compressed),
                    merged_graph.node_count,
                    merged_graph.message_count,
                    len(merged_graph.current_path),
                    len(merged_graph.branch_points),
                    import_id,
                    now,
                    merged_graph.conversation_id,
                ),
            )

            existing_ids = {
                str(row["node_id"])
                for row in self.con.execute(
                    "SELECT node_id FROM nodes WHERE conversation_id=?",
                    (merged_graph.conversation_id,),
                ).fetchall()
            }
            new_nodes = [
                node for node in merged_graph.nodes if node.node_id not in existing_ids
            ]

            counters = {
                "conversations_inserted": 0,
                "conversations_updated": 1,
                "nodes_inserted": 0,
                "fts_inserted": 0,
                "assets_upserted": 0,
                "conflicts": 0,
                "branch_only_merges": 1,
            }
            if new_nodes:
                inserted = self._insert_nodes(import_id, merged_graph, new_nodes)
                counters.update(
                    {
                        "nodes_inserted": int(inserted.get("nodes_inserted", 0)),
                        "fts_inserted": int(inserted.get("fts_inserted", 0)),
                        "assets_upserted": int(
                            inserted.get("assets_upserted", 0)
                        ),
                    }
                )

            # Recompute structural metadata for every canonical node because the
            # union can introduce new branch points and alter DFS ordinals/path.
            self.con.executemany(
                """UPDATE nodes SET
                   parent_node_id=?,structural_ordinal=?,on_current_path=?,
                   branch_id=?,has_assets=?
                   WHERE conversation_id=? AND node_id=?""",
                [
                    (
                        node.parent_node_id,
                        node.structural_ordinal,
                        int(node.on_current_path),
                        node.branch_id,
                        int(bool(node.assets)),
                        merged_graph.conversation_id,
                        node.node_id,
                    )
                    for node in merged_graph.nodes
                ],
            )

            incoming_ids = set(incoming_nodes)
            self.con.executemany(
                """UPDATE nodes SET last_seen_import_id=?
                   WHERE conversation_id=? AND node_id=?""",
                [
                    (import_id, merged_graph.conversation_id, node_id)
                    for node_id in sorted(incoming_ids)
                ],
            )
            self.con.execute(
                "UPDATE fts_docs SET title=? WHERE conversation_id=?",
                (merged_graph.title, merged_graph.conversation_id),
            )

            self.con.execute(
                """INSERT OR IGNORE INTO conversation_occurrences
                   (conversation_id,import_id,relation_to_active,raw_tree_sha256,
                    semantic_tree_sha256,node_count,message_count,observed_at_utc)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    graph.conversation_id,
                    import_id,
                    "divergent",
                    graph.raw_tree_sha256,
                    graph.semantic_tree_sha256,
                    graph.node_count,
                    graph.message_count,
                    now,
                ),
            )

            details = {
                "added_node_ids": list(plan.added_node_ids),
                "changed_node_ids": [],
                "missing_from_incoming_node_ids": list(
                    plan.missing_from_incoming_node_ids
                ),
                "reason": plan.reason,
                "resolution": "auto_merged_branch_only_union",
                "resolution_hotfix": HOTFIX_VERSION,
                "merged_semantic_tree_sha256": (
                    merged_graph.semantic_tree_sha256
                ),
                "merged_node_count": merged_graph.node_count,
                "truth_boundary": (
                    "Only source-recorded nodes with unchanged shared semantic "
                    "content were unioned. No memory-tier promotion occurred."
                ),
            }
            self.con.execute(
                """INSERT OR IGNORE INTO conversation_revisions
                   (revision_id,conversation_id,import_id,relation_to_active,
                    raw_tree_sha256,semantic_tree_sha256,node_count,
                    details_json,created_at_utc)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()),
                    graph.conversation_id,
                    import_id,
                    "divergent",
                    graph.raw_tree_sha256,
                    graph.semantic_tree_sha256,
                    graph.node_count,
                    json.dumps(
                        details,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    now,
                ),
            )
            return counters
        except BranchUnionUnsafe:
            return original_store_graph(self, import_id, graph, plan)

    ChatExportArchiveStore.store_graph = patched_store_graph
    ChatExportArchiveStore._branch_union_hotfix_version = HOTFIX_VERSION


def _branch_union_self_test() -> int:
    # Pure structural checks; full DB integration still belongs to repository
    # pytest after this file is dropped into tools/.
    active = {
        "id": "conv-1",
        "title": "T",
        "create_time": 1,
        "update_time": 10,
        "current_node": "a",
        "mapping": {
            "root": {"parent": None, "children": ["a"], "message": None},
            "a": {"parent": "root", "children": [], "message": {"id": "m-a"}},
        },
    }
    incoming = {
        "id": "conv-1",
        "title": "T",
        "create_time": 1,
        "update_time": 11,
        "current_node": "b",
        "mapping": {
            "root": {"parent": None, "children": ["b"], "message": None},
            "b": {"parent": "root", "children": [], "message": {"id": "m-b"}},
        },
    }
    merged = _merge_branch_only_payloads(active, incoming)
    assert set(merged["mapping"]) == {"root", "a", "b"}
    assert set(merged["mapping"]["root"]["children"]) == {"a", "b"}
    assert merged["current_node"] == "b"

    unsafe = deepcopy(incoming)
    unsafe["mapping"]["root"]["parent"] = "a"
    try:
        _merge_branch_only_payloads(active, unsafe)
    except BranchUnionUnsafe:
        pass
    else:
        raise AssertionError("unsafe structural divergence was not rejected")

    print(
        json.dumps(
            {
                "ok": True,
                "hotfix_version": HOTFIX_VERSION,
                "checks": [
                    "branch_union_preserves_both_unique_branches",
                    "latest_current_node_selected",
                    "unsafe_parent_change_rejected",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args == ["--branch-union-self-test"]:
        return _branch_union_self_test()

    if _legacy_requested(args):
        return _run_legacy(args)

    _install_branch_union_hotfix()
    from latka_jazn.tools.memory_rebuild_app.cli import main as app_main

    return int(app_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
