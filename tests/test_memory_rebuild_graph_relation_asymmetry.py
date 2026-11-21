from __future__ import annotations

"""Synthetic regression fixtures for raw versus projected conversation links."""

import json
from pathlib import Path

from latka_jazn.tools.memory_rebuild_app.source_union import build_source_union_manifest


CONVERSATION_ID = "graph-asymmetry-fixture"


def _message(text: str) -> dict:
    return {
        "id": "message-1",
        "author": {"role": "user"},
        "create_time": 1.0,
        "content": {"content_type": "text", "parts": [text]},
    }


def _conversation(
    *,
    children_state: str,
    parent: str = "root",
    text: str = "same message",
) -> dict:
    root: dict = {"id": "root", "parent": None, "message": None}
    alternative = {"id": "other-root", "parent": None, "message": None, "children": []}
    if children_state == "present":
        root["children"] = ["child"]
    elif children_state == "empty":
        root["children"] = []
    elif children_state == "null":
        root["children"] = None
    elif children_state != "missing":
        raise ValueError(children_state)
    if parent == "other-root":
        alternative["children"] = ["child"]
    return {
        "id": CONVERSATION_ID,
        "title": "graph relationship regression",
        "current_node": "child",
        "mapping": {
            "root": root,
            "other-root": alternative,
            "child": {
                "id": "child",
                "parent": parent,
                "children": [],
                "message": _message(text),
            },
        },
    }


def _save(path: Path, conversation: dict) -> Path:
    path.write_text(json.dumps([conversation], ensure_ascii=False), encoding="utf-8")
    return path


def _audits(report: dict) -> dict[str, dict]:
    variants = report["conversations"][0]["raw_source_variants"]
    return {item["source_sha256"]: item["reverse_link_audit"] for item in variants}


def test_missing_children_is_derived_not_a_message_loss(tmp_path: Path) -> None:
    a = _save(tmp_path / "a.json", _conversation(children_state="missing"))
    b = _save(tmp_path / "b.json", _conversation(children_state="present"))
    report = build_source_union_manifest([a, b])
    reverse = build_source_union_manifest([b, a])

    assert report["ok"] is True
    assert report["projection_conflict_conversation_count"] == 0
    assert report["changed_message_node_count"] == 0
    assert report["changed_parent_node_count"] == 0
    assert report["raw_source_variant_count"] == 2
    assert report["union_message_node_count"] == 1
    assert report["union_fingerprint_sha256"] == reverse["union_fingerprint_sha256"]
    assert report["conversations"][0]["raw_source_variants"] == reverse["conversations"][0]["raw_source_variants"]

    audit_by_hash = _audits(report)
    from latka_jazn.tools.chat_export_reader import sha256_file
    absent = audit_by_hash[sha256_file(a)]
    explicit = audit_by_hash[sha256_file(b)]
    assert absent["parent_missing_children_key"] == 1
    assert absent["reconstructed_children_count"] == 1
    assert absent["reciprocal_confirmed"] == 0
    assert explicit["reciprocal_confirmed"] == 1
    assert explicit["reconstructed_children_count"] == 0
    assert all(
        item["source_relationships_mutated"] is False
        and item["working_children_origin"] == "derived_from_parent_not_source"
        for item in report["conversations"][0]["raw_source_variants"]
    )


def test_explicit_null_and_missing_are_distinct_raw_versions(tmp_path: Path) -> None:
    missing = _save(tmp_path / "missing.json", _conversation(children_state="missing"))
    null = _save(tmp_path / "null.json", _conversation(children_state="null"))
    report = build_source_union_manifest([missing, null])
    assert report["raw_source_variant_count"] == 2
    # Legacy logical fingerprints may coincide because the normalized graph
    # treats both as empty children; source/raw evidence must not be collapsed.
    variants = report["conversations"][0]["raw_source_variants"]
    assert len({item["raw_tree_sha256"] for item in variants}) == 2
    assert len({item["raw_relation_sha256"] for item in variants}) == 2
    audits = _audits(report)
    from latka_jazn.tools.chat_export_reader import sha256_file
    assert audits[sha256_file(missing)]["parent_missing_children_key"] == 1
    assert audits[sha256_file(null)]["parent_null_children"] == 1
    assert audits[sha256_file(null)]["reconstructed_children_count"] == 0
    assert report["projection_conflict_conversation_count"] == 0


def test_explicit_empty_children_is_not_a_missing_key(tmp_path: Path) -> None:
    source = _save(tmp_path / "empty.json", _conversation(children_state="empty"))
    report = build_source_union_manifest([source])
    audit = report["conversations"][0]["raw_source_variants"][0]["reverse_link_audit"]
    assert audit["parent_missing_children_key"] == 0
    assert audit["parent_null_children"] == 0
    assert audit["parent_empty_children"] == 1
    assert audit["parent_children_without_backref"] == 1
    assert audit["reconstructed_children_count"] == 0


def test_changed_parent_remains_a_real_unresolved_conflict(tmp_path: Path) -> None:
    a = _save(tmp_path / "a.json", _conversation(children_state="missing"))
    b = _save(
        tmp_path / "b.json",
        _conversation(children_state="present", parent="other-root"),
    )
    report = build_source_union_manifest([a, b])
    row = report["conversations"][0]
    assert row["relation"] == "conflict"
    assert row["changed_parent_node_ids"] == ["child"]
    assert row["changed_message_node_ids"] == []
    assert report["requires_projection_resolution"] is True


def test_changed_message_content_is_not_silently_merged(tmp_path: Path) -> None:
    a = _save(tmp_path / "a.json", _conversation(children_state="missing"))
    b = _save(
        tmp_path / "b.json",
        _conversation(children_state="present", text="changed message"),
    )
    report = build_source_union_manifest([a, b])
    row = report["conversations"][0]
    assert row["relation"] == "conflict"
    assert row["changed_message_node_ids"] == ["child"]
    assert report["changed_message_node_count"] == 1
    assert report["requires_projection_resolution"] is True
