from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sqlite3
import zipfile

from latka_jazn.tools.memory_rebuild_app.source_fidelity import CHUNK_SIZE, run_test00_source_fidelity
from latka_jazn.tools.memory_rebuild_app.test_spec import TEST_PROTOCOL_ORDER, TestOutcome, get_test_spec


def _message(message_id: str, role: str, content_type: str, text: str) -> dict:
    return {
        "id": message_id,
        "author": {"role": role},
        "create_time": 100.0,
        "content": {"content_type": content_type, "parts": [text]},
        "metadata": {},
    }


def _conversation() -> dict:
    roles = ("user", "assistant", "system", "tool", "future_role")
    mapping: dict[str, dict] = {}
    parent = None
    for index, role in enumerate(roles):
        node_id = f"n-{index}"
        mapping[node_id] = {
            "id": node_id,
            "parent": parent,
            "children": [],
            "message": _message(f"m-{index}", role, "text" if role != "tool" else "execution_output", f"tekst {role}"),
        }
        if parent is not None:
            mapping[parent]["children"].append(node_id)
        parent = node_id
    return {
        "id": "conv-test00",
        "title": "Source fidelity",
        "create_time": 100.0,
        "update_time": 105.0,
        "current_node": parent,
        "mapping": mapping,
    }


def _read_mirrored_blob(database: Path) -> bytes:
    with sqlite3.connect(database) as con:
        source_id = con.execute("SELECT source_id FROM source_mirror_sources ORDER BY source_pk LIMIT 1").fetchone()[0]
        rows = con.execute(
            "SELECT data FROM source_mirror_chunks WHERE source_id=? ORDER BY chunk_index",
            (source_id,),
        ).fetchall()
    return b"".join(bytes(row[0]) for row in rows)


def test_protocol_order_starts_with_test00_and_has_final() -> None:
    assert TEST_PROTOCOL_ORDER == ("test00", "test01", "test02", "test03", "test04", "final")
    spec = get_test_spec("test00")
    assert "Source Fidelity" in spec.label
    assert spec.writes_test_artifacts is True
    assert spec.validator_profile is None
    assert any("nie aktywną" in value or "nie aktyw" in value for value in spec.truth_boundary)


def test_json_source_is_mirrored_byte_exact_and_preserves_all_observed_roles(tmp_path: Path) -> None:
    source = tmp_path / "conversations.json"
    source.write_text(json.dumps([_conversation()], ensure_ascii=False), encoding="utf-8")
    result = run_test00_source_fidelity([source], output_root=tmp_path / "test00", run_id="json")
    assert result["ok"] is True
    assert result["outcome"] == TestOutcome.PASSED.value
    item = result["results"][0]
    assert item["role_counts"] == {
        "assistant": 1,
        "future_role": 1,
        "system": 1,
        "tool": 1,
        "user": 1,
    }
    assert item["content_type_counts"] == {"execution_output": 1, "text": 4}
    assert item["raw_chunk_count"] == 1
    database = Path(result["database"])
    mirrored = _read_mirrored_blob(database)
    original = source.read_bytes()
    assert mirrored == original
    assert hashlib.sha256(mirrored).hexdigest() == hashlib.sha256(original).hexdigest()
    with sqlite3.connect(database) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("SELECT COUNT(*) FROM source_mirror_roles WHERE role='future_role'").fetchone()[0] == 1
        assert not any(
            name in {"memory_records", "promotion_requests", "promotion_decisions", "promotion_ledger"}
            for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )


def test_chunked_mirror_reconstructs_source_larger_than_one_chunk(tmp_path: Path) -> None:
    source = tmp_path / "large.json"
    payload = b"[" + (b" " * (CHUNK_SIZE + 137)) + b"]"
    source.write_bytes(payload)
    result = run_test00_source_fidelity([source], output_root=tmp_path / "test00", run_id="chunks")
    assert result["outcome"] == TestOutcome.PASSED.value
    assert result["results"][0]["raw_chunk_count"] == 2
    assert _read_mirrored_blob(Path(result["database"])) == payload


def test_embedded_html_is_structural_pass_and_rendered_fallback_is_lossy(tmp_path: Path) -> None:
    embedded = tmp_path / "embedded.html"
    embedded.write_text(
        "<html><body><script>const jsonData = " + json.dumps([_conversation()], ensure_ascii=False) + ";</script></body></html>",
        encoding="utf-8",
    )
    embedded_result = run_test00_source_fidelity([embedded], output_root=tmp_path / "test00", run_id="embedded")
    assert embedded_result["ok"] is True
    assert embedded_result["results"][0]["parse_mode"] == "embedded_json"
    assert embedded_result["results"][0]["role_counts"]["tool"] == 1

    fallback = tmp_path / "fallback.html"
    fallback.write_text(
        '<div class="conversation"><h4>Widoczny chat</h4>'
        '<pre class="message">Pierwsza</pre><pre class="message">Druga</pre></div>',
        encoding="utf-8",
    )
    fallback_result = run_test00_source_fidelity([fallback], output_root=tmp_path / "test00", run_id="fallback")
    assert fallback_result["ok"] is False
    assert fallback_result["outcome"] == TestOutcome.LOSSY.value
    assert fallback_result["results"][0]["parse_mode"] == "rendered_html_fallback"
    assert _read_mirrored_blob(Path(fallback_result["database"])) == fallback.read_bytes()


def test_zip_reads_every_member_and_keeps_exact_container_bytes(tmp_path: Path) -> None:
    source = tmp_path / "chat-export.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("conversations.json", json.dumps([_conversation()], ensure_ascii=False))
        archive.writestr("message_feedback.json", json.dumps([{"conversation_id": "conv-test00", "rating": "thumbs_up"}]))
        archive.writestr("user.json", json.dumps({"id": "private-user"}))
        archive.writestr("assets/example.txt", "załącznik")
    result = run_test00_source_fidelity([source], output_root=tmp_path / "test00", run_id="zip")
    assert result["outcome"] == TestOutcome.PASSED.value
    item = result["results"][0]
    assert item["zip_member_count"] == 4
    database = Path(result["database"])
    assert _read_mirrored_blob(database) == source.read_bytes()
    with sqlite3.connect(database) as con:
        members = dict(con.execute("SELECT member_name,member_sha256 FROM source_mirror_zip_members"))
    assert set(members) == {
        "conversations.json",
        "message_feedback.json",
        "user.json",
        "assets/example.txt",
    }
    with zipfile.ZipFile(source, "r") as archive:
        for name, expected_sha in members.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected_sha


def test_generic_json_sidecar_is_fully_validated_without_becoming_conversation(tmp_path: Path) -> None:
    sidecar = tmp_path / "message_feedback.json"
    payload = [
        {"conversation_id": "a", "rating": "thumbs_up"},
        {"conversation_id": "b", "rating": "thumbs_down"},
    ]
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    result = run_test00_source_fidelity([sidecar], output_root=tmp_path / "test00", run_id="sidecar")
    assert result["outcome"] == TestOutcome.PASSED.value
    item = result["results"][0]
    assert item["conversation_count"] == 0
    assert item["parse_mode"].startswith("sidecar_json:")
    assert _read_mirrored_blob(Path(result["database"])) == sidecar.read_bytes()


def test_unsupported_source_is_byte_preserved_but_blocked(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_bytes(b"raw evidence remains exact\x00even when unsupported")
    result = run_test00_source_fidelity([source], output_root=tmp_path / "test00", run_id="blocked")
    assert result["outcome"] == TestOutcome.BLOCKED.value
    assert _read_mirrored_blob(Path(result["database"])) == source.read_bytes()
