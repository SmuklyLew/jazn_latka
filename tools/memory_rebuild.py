#!/usr/bin/env python3
from __future__ import annotations

"""
Jaźń Memory Rebuild v2.4 — safe structural-divergence reconciliation hotfix.

HOTFIX:
    memory-rebuild/structural-variant-union-v2

Why v2 exists
-------------
Real ChatGPT exports can contain the same stable message/node IDs with unchanged
semantic message content but a different tree topology (notably a different
``parent``).  The canonical deduper intentionally ignores topology in
``stable_node_hash`` and therefore reports such a pair as ``divergent`` with
``changed_node_ids=[]``.

v1 only merged cases where shared nodes also kept identical parents.  Real Test
03 data proved that this was too narrow.

v2 resolves ONLY semantic-safe structural divergence:

* ``plan.relation == "divergent"``;
* ``changed_node_ids`` is empty;
* both sides contribute unique nodes;
* every shared node has the same durable semantic hash;
* each source tree is individually valid;
* a deterministic canonical projection of the union is acyclic and has
  reciprocal parent/children links.

The exact pre-merge active payload and exact incoming source payload are
compressed and stored inside ``conversation_revisions.details_json`` so the
structural variants remain auditable and survive the existing five-db ->
unified-memory migration (``conversation_revisions`` is already copied by the
canonical migration pipeline).

The canonical ``conversations.payload_blob`` becomes a derived union projection:
all source-recorded nodes are retained, while topology for shared nodes is taken
from the deterministically preferred (normally newer ``update_time``) source.
Children are then recomputed from the chosen parent pointers.

Truth boundary
--------------
This hotfix does NOT:
* change message content;
* invent memories;
* auto-promote L2/L3;
* treat semantic payload conflicts as resolvable;
* delete previously recorded conflicts from an existing database.

If any semantic or structural safety check fails, the original importer runs and
records a normal unresolved ``import_conflict``.

Use a FRESH rebuild target.
"""

from copy import deepcopy
from pathlib import Path
from typing import Any, Sequence
import base64
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

HOTFIX_VERSION = "memory-rebuild/structural-variant-union-v2"

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


class StructuralVariantUnsafe(RuntimeError):
    """The divergent pair cannot be reconciled without losing source truth."""


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
    module = _load_legacy_module()
    for name in dir(module):
        if name.startswith("__") or name in {"main", "ROOT", "self_test"}:
            continue
        globals().setdefault(name, getattr(module, name))


try:
    _expose_legacy_contract()
except FileNotFoundError:
    # Allows the standalone safety self-test outside a full repository checkout.
    pass


def self_test(state):
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


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _finite_number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float("-inf")
    return result if math.isfinite(result) else float("-inf")


def _payload_preference_key(payload: dict[str, Any]) -> tuple[float, str]:
    # update_time is the source chronology signal.  SHA is only a deterministic
    # tie breaker, so import order cannot affect equal-time reconciliation.
    return (_finite_number(payload.get("update_time")), _json_sha256(payload))


def _mapping(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = payload.get("mapping")
    if not isinstance(raw, dict) or not raw:
        raise StructuralVariantUnsafe("conversation mapping is missing or empty")
    result: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            raise StructuralVariantUnsafe(f"node {key!r} is not an object")
        result[str(key)] = value
    return result


def _parent(raw: dict[str, Any]) -> str | None:
    value = raw.get("parent")
    return str(value) if value not in (None, "") else None


def _children(raw: dict[str, Any]) -> list[str]:
    value = raw.get("children")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")]


def _ordered_unique(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _validate_parent_graph(mapping: dict[str, dict[str, Any]]) -> None:
    for node_id, raw in mapping.items():
        parent = _parent(raw)
        if parent is not None and parent not in mapping:
            raise StructuralVariantUnsafe(
                f"node {node_id} points to missing parent {parent}"
            )

    for start in mapping:
        seen: set[str] = set()
        current = start
        while current in mapping:
            if current in seen:
                raise StructuralVariantUnsafe(
                    f"cycle detected in parent graph at node {current}"
                )
            seen.add(current)
            parent = _parent(mapping[current])
            if parent is None:
                break
            current = parent


def _rebuild_children(
    mapping: dict[str, dict[str, Any]],
    *,
    preferred: dict[str, dict[str, Any]],
    fallback: dict[str, dict[str, Any]],
) -> None:
    desired: dict[str, list[str]] = {node_id: [] for node_id in mapping}
    for node_id, raw in mapping.items():
        parent = _parent(raw)
        if parent is not None:
            desired[parent].append(node_id)

    for parent_id, expected_children in desired.items():
        ordering: list[str] = []
        for source in (preferred.get(parent_id), fallback.get(parent_id)):
            if source is None:
                continue
            for child in _children(source):
                if child in expected_children:
                    ordering.append(child)
        for child in sorted(expected_children):
            ordering.append(child)
        mapping[parent_id]["children"] = _ordered_unique(ordering)


def _validate_reciprocal_edges(mapping: dict[str, dict[str, Any]]) -> None:
    for node_id, raw in mapping.items():
        parent = _parent(raw)
        if parent is not None and node_id not in _children(mapping[parent]):
            raise StructuralVariantUnsafe(
                f"parent {parent} does not list child {node_id}"
            )
        for child in _children(raw):
            if child not in mapping:
                raise StructuralVariantUnsafe(
                    f"node {node_id} references missing child {child}"
                )
            if _parent(mapping[child]) != node_id:
                raise StructuralVariantUnsafe(
                    f"child {child} has non-reciprocal parent"
                )


def _canonical_union_projection(
    active_payload: dict[str, Any],
    incoming_payload: dict[str, Any],
) -> dict[str, Any]:
    active_id = str(
        active_payload.get("id") or active_payload.get("conversation_id") or ""
    ).strip()
    incoming_id = str(
        incoming_payload.get("id") or incoming_payload.get("conversation_id") or ""
    ).strip()
    if not active_id or active_id != incoming_id:
        raise StructuralVariantUnsafe("conversation IDs differ")

    active_mapping = _mapping(active_payload)
    incoming_mapping = _mapping(incoming_payload)
    active_only = set(active_mapping) - set(incoming_mapping)
    incoming_only = set(incoming_mapping) - set(active_mapping)
    if not active_only or not incoming_only:
        raise StructuralVariantUnsafe(
            "structural union requires unique nodes on both sides"
        )

    if _payload_preference_key(incoming_payload) > _payload_preference_key(
        active_payload
    ):
        preferred_payload, fallback_payload = incoming_payload, active_payload
        preferred_mapping, fallback_mapping = incoming_mapping, active_mapping
    else:
        preferred_payload, fallback_payload = active_payload, incoming_payload
        preferred_mapping, fallback_mapping = active_mapping, incoming_mapping

    merged = deepcopy(preferred_payload)
    for key, value in fallback_payload.items():
        if key == "mapping":
            continue
        if key not in merged or merged[key] in (None, ""):
            merged[key] = deepcopy(value)

    # One canonical node per source-recorded node ID.  Shared-node semantic
    # equality is verified by the store patch before this function is called.
    # For topology/volatile metadata, prefer the newer deterministic source.
    union_mapping: dict[str, dict[str, Any]] = {}
    for node_id in sorted(set(active_mapping) | set(incoming_mapping)):
        if node_id in preferred_mapping:
            union_mapping[node_id] = deepcopy(preferred_mapping[node_id])
        else:
            union_mapping[node_id] = deepcopy(fallback_mapping[node_id])

    _validate_parent_graph(union_mapping)
    _rebuild_children(
        union_mapping,
        preferred=preferred_mapping,
        fallback=fallback_mapping,
    )
    _validate_reciprocal_edges(union_mapping)

    merged["mapping"] = union_mapping

    preferred_current = preferred_payload.get("current_node")
    fallback_current = fallback_payload.get("current_node")
    if (
        preferred_current is not None
        and str(preferred_current) in union_mapping
    ):
        merged["current_node"] = str(preferred_current)
    elif (
        fallback_current is not None
        and str(fallback_current) in union_mapping
    ):
        merged["current_node"] = str(fallback_current)
    else:
        merged["current_node"] = None

    create_values = [
        _finite_number(active_payload.get("create_time")),
        _finite_number(incoming_payload.get("create_time")),
    ]
    create_values = [x for x in create_values if math.isfinite(x)]
    if create_values:
        merged["create_time"] = min(create_values)

    update_values = [
        _finite_number(active_payload.get("update_time")),
        _finite_number(incoming_payload.get("update_time")),
    ]
    update_values = [x for x in update_values if math.isfinite(x)]
    if update_values:
        merged["update_time"] = max(update_values)

    return merged


def _compressed_variant(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _json_bytes(payload)
    compressed = zlib.compress(raw, level=9)
    return {
        "codec": "zlib-json-v1+base64",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_size": len(raw),
        "compressed_size": len(compressed),
        "data_b64": base64.b64encode(compressed).decode("ascii"),
    }


def _is_semantic_safe_divergence(plan: Any) -> bool:
    return bool(
        getattr(plan, "relation", None) == "divergent"
        and not tuple(getattr(plan, "changed_node_ids", ()) or ())
        and tuple(getattr(plan, "added_node_ids", ()) or ())
        and tuple(getattr(plan, "missing_from_incoming_node_ids", ()) or ())
    )


def _install_structural_variant_hotfix() -> None:
    from latka_jazn.tools.chat_export_dedupe import stable_node_hash
    from latka_jazn.tools.chat_export_reader import build_conversation_graph
    from latka_jazn.tools.chat_export_store import (
        ChatExportArchiveStore,
        PAYLOAD_CODEC,
    )

    if getattr(ChatExportArchiveStore, "_structural_variant_hotfix", None):
        return

    original_store_graph = ChatExportArchiveStore.store_graph

    def patched_store_graph(self, import_id, graph, plan):
        if not _is_semantic_safe_divergence(plan):
            return original_store_graph(self, import_id, graph, plan)

        try:
            active_payload = self.conversation_payload(graph.conversation_id)
            if active_payload is None:
                raise StructuralVariantUnsafe("active payload is missing")

            active_graph = build_conversation_graph(active_payload)
            active_nodes = active_graph.node_index()
            incoming_nodes = graph.node_index()
            shared = set(active_nodes) & set(incoming_nodes)

            # Fail closed on any real message/asset semantic change.
            changed = [
                node_id
                for node_id in shared
                if stable_node_hash(active_nodes[node_id])
                != stable_node_hash(incoming_nodes[node_id])
            ]
            if changed:
                raise StructuralVariantUnsafe(
                    "shared semantic node changed: "
                    + ",".join(sorted(changed)[:10])
                )

            merged_payload = _canonical_union_projection(
                active_payload,
                graph.source_payload,
            )
            merged_graph = build_conversation_graph(merged_payload)

            expected_ids = set(active_nodes) | set(incoming_nodes)
            merged_index = merged_graph.node_index()
            if set(merged_index) != expected_ids:
                raise StructuralVariantUnsafe(
                    "canonical projection does not contain exact node union"
                )

            # Every source-recorded semantic node must survive unchanged.
            for node_id in expected_ids:
                reference = (
                    incoming_nodes[node_id]
                    if node_id in incoming_nodes
                    else active_nodes[node_id]
                )
                if stable_node_hash(merged_index[node_id]) != stable_node_hash(
                    reference
                ):
                    raise StructuralVariantUnsafe(
                        f"canonical projection changed semantic node {node_id}"
                    )

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()

            canonical_raw = _json_bytes(merged_graph.source_payload)
            canonical_compressed = zlib.compress(canonical_raw, level=6)

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
                    PAYLOAD_CODEC,
                    canonical_compressed,
                    len(canonical_raw),
                    len(canonical_compressed),
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
                node
                for node in merged_graph.nodes
                if node.node_id not in existing_ids
            ]

            counters = {
                "conversations_inserted": 0,
                "conversations_updated": 1,
                "nodes_inserted": 0,
                "fts_inserted": 0,
                "assets_upserted": 0,
                "conflicts": 0,
                "structural_variant_merges": 1,
            }

            if new_nodes:
                inserted = self._insert_nodes(
                    import_id,
                    merged_graph,
                    new_nodes,
                )
                counters["nodes_inserted"] = int(
                    inserted.get("nodes_inserted", 0)
                )
                counters["fts_inserted"] = int(
                    inserted.get("fts_inserted", 0)
                )
                counters["assets_upserted"] = int(
                    inserted.get("assets_upserted", 0)
                )

            # Recalculate only derived structural fields for the union projection.
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

            # "last seen" is source evidence: only nodes actually present in the
            # incoming source get the incoming import ID.
            self.con.executemany(
                """UPDATE nodes SET last_seen_import_id=?
                   WHERE conversation_id=? AND node_id=?""",
                [
                    (
                        import_id,
                        merged_graph.conversation_id,
                        node_id,
                    )
                    for node_id in sorted(incoming_nodes)
                ],
            )
            self.con.execute(
                "UPDATE fts_docs SET title=? WHERE conversation_id=?",
                (merged_graph.title, merged_graph.conversation_id),
            )

            self.con.execute(
                """INSERT OR IGNORE INTO conversation_occurrences
                   (conversation_id,import_id,relation_to_active,
                    raw_tree_sha256,semantic_tree_sha256,node_count,
                    message_count,observed_at_utc)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    graph.conversation_id,
                    import_id,
                    "divergent_resolved_structural_variant",
                    graph.raw_tree_sha256,
                    graph.semantic_tree_sha256,
                    graph.node_count,
                    graph.message_count,
                    now,
                ),
            )

            # Preserve both exact source variants in a table already copied by the
            # canonical unified-memory migration.  This keeps the derived union
            # separate from the raw evidence.
            details = {
                "added_node_ids": list(plan.added_node_ids),
                "changed_node_ids": [],
                "missing_from_incoming_node_ids": list(
                    plan.missing_from_incoming_node_ids
                ),
                "original_reason": plan.reason,
                "resolution": "resolved_semantic_safe_structural_divergence",
                "resolution_hotfix": HOTFIX_VERSION,
                "active_variant": _compressed_variant(active_payload),
                "incoming_variant": _compressed_variant(graph.source_payload),
                "canonical_projection": {
                    "semantic_tree_sha256": (
                        merged_graph.semantic_tree_sha256
                    ),
                    "raw_tree_sha256": merged_graph.raw_tree_sha256,
                    "node_count": merged_graph.node_count,
                    "message_count": merged_graph.message_count,
                    "projection_policy": (
                        "semantic node union; preferred source topology for "
                        "shared nodes; children recomputed from chosen parents"
                    ),
                },
                "truth_boundary": (
                    "Both exact source payloads are preserved as compressed "
                    "evidence. Canonical payload is a derived structural "
                    "projection; no message semantics or memory tiers are "
                    "promoted or invented."
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
                    "divergent_resolved_structural_variant",
                    graph.raw_tree_sha256,
                    graph.semantic_tree_sha256,
                    graph.node_count,
                    json.dumps(
                        details,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    now,
                ),
            )

            return counters

        except StructuralVariantUnsafe:
            # Fail closed: canonical importer records the unresolved conflict.
            return original_store_graph(self, import_id, graph, plan)

    ChatExportArchiveStore.store_graph = patched_store_graph
    ChatExportArchiveStore._structural_variant_hotfix = HOTFIX_VERSION


def _structural_variant_self_test() -> int:
    # Realistic case: shared semantic node X is re-parented between exports.
    active = {
        "id": "conv-1",
        "title": "test",
        "create_time": 1,
        "update_time": 10,
        "current_node": "x",
        "mapping": {
            "root": {"parent": None, "children": ["old-parent"]},
            "old-parent": {
                "parent": "root",
                "children": ["x", "old-only"],
            },
            "old-only": {"parent": "old-parent", "children": []},
            "x": {
                "parent": "old-parent",
                "children": [],
                "message": {"id": "same-message"},
            },
        },
    }
    incoming = {
        "id": "conv-1",
        "title": "test",
        "create_time": 1,
        "update_time": 11,
        "current_node": "x",
        "mapping": {
            "root": {"parent": None, "children": ["new-parent"]},
            "new-parent": {
                "parent": "root",
                "children": ["x", "new-only"],
            },
            "new-only": {"parent": "new-parent", "children": []},
            "x": {
                "parent": "new-parent",
                "children": [],
                "message": {"id": "same-message"},
            },
        },
    }

    merged = _canonical_union_projection(active, incoming)
    mapping = merged["mapping"]
    assert set(mapping) == {
        "root",
        "old-parent",
        "old-only",
        "new-parent",
        "new-only",
        "x",
    }
    assert mapping["x"]["parent"] == "new-parent"
    assert "x" in mapping["new-parent"]["children"]
    assert "x" not in mapping["old-parent"]["children"]
    assert "old-only" in mapping["old-parent"]["children"]
    assert "new-only" in mapping["new-parent"]["children"]

    variant = _compressed_variant(active)
    decoded = json.loads(
        zlib.decompress(base64.b64decode(variant["data_b64"])).decode("utf-8")
    )
    assert decoded == active

    unsafe = deepcopy(incoming)
    unsafe["mapping"]["new-parent"]["parent"] = "x"
    try:
        _canonical_union_projection(active, unsafe)
    except StructuralVariantUnsafe:
        cycle_rejected = True
    else:
        cycle_rejected = False
    assert cycle_rejected

    print(
        json.dumps(
            {
                "ok": True,
                "hotfix_version": HOTFIX_VERSION,
                "checks": [
                    "shared_node_reparenting_reconciled",
                    "all_unique_nodes_preserved",
                    "children_rebuilt_from_canonical_parents",
                    "exact_source_variant_roundtrip",
                    "cycle_rejected_fail_closed",
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
        # Backward-compatible diagnostic alias from v1.
        return _structural_variant_self_test()
    if args == ["--structural-variant-self-test"]:
        return _structural_variant_self_test()

    if _legacy_requested(args):
        return _run_legacy(args)

    _install_structural_variant_hotfix()

    from latka_jazn.tools.memory_rebuild_app.cli import main as app_main
    return int(app_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
