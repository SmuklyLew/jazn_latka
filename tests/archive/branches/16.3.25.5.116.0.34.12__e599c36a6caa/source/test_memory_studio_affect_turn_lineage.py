"""ChatGPT export and affect turn provenance: synthetic regressions."""
from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from latka_jazn.tools.memory_rebuild_app.source_detection import probe_source
from latka_jazn.tools.memory_rebuild_app.source_inventory import inspect_source
from latka_jazn.tools.memory_rebuild_app.source_bundle import classify_source_role, SourceRole
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase
from latka_jazn.tools.memory_rebuild_app.schema_l0 import L0_SCHEMA_VERSION


def _conversation() -> dict:
    return {"id":"c1","title":"Syntetyczna","create_time":1,"mapping":{
        "root":{"id":"root","parent":None,"children":[],"message":None}},"current_node":"root"}


def test_numbered_zip_matches_studio_and_importer(tmp_path: Path) -> None:
    archive = tmp_path / "export.zip"
    with ZipFile(archive, "w") as z:
        z.writestr("wrapper/conversations-001.json",json.dumps([_conversation()]))
    assert probe_source(archive).kind == "chat"
    assert inspect_source(archive).role == "chatgpt_export"
    assert UnifiedMemoryDatabase(tmp_path / "db.sqlite3").import_source(archive).report["ok"]


@pytest.mark.parametrize(("path","expected"),[
    ("assets/a.png",SourceRole.SOURCE_ATTACHMENT),
    ("wrapper/assets/a.png",SourceRole.SOURCE_ATTACHMENT),
    ("wrapper/attachments/b.mp3",SourceRole.SOURCE_ATTACHMENT),
    ("wrapper/assets-named.png",SourceRole.UNKNOWN_SIDECAR),
])
def test_nested_assets_are_source_attachments(path: str,expected: SourceRole) -> None:
    assert classify_source_role(path) is expected


def test_single_file_preview_does_not_touch_target(tmp_path: Path, monkeypatch) -> None:
    from latka_jazn.tools.memory_rebuild_app import source_inventory
    src = tmp_path / "conversations.json"
    src.write_text(json.dumps([_conversation()]),encoding="utf-8")
    monkeypatch.setattr(source_inventory,"load_json_strict",lambda _: (_ for _ in ()).throw(AssertionError("eager read")))
    assert source_inventory._sniff_json(src)["streaming_probe"] is True
    target = tmp_path / "absent" / "db.sqlite3"
    assert UnifiedMemoryDatabase(target).import_source(src,dry_run=True).status == "planned"
    assert not target.exists()


def _accepted() -> dict:
    return {"finalization_status":"accepted","turn_id":"turn-1","trace_id":"trace-1",
        "conversation_id":"chat-1","message_id":"msg-1","event_time":"2026-10-09T05:00:00Z",
        "modelled_affect":{"labels":["ostrożna ciekawość"],"model":"operational"}}


def test_modelled_affect_has_single_versioned_lineage(tmp_path: Path) -> None:
    db = UnifiedMemoryDatabase(tmp_path / "db.sqlite3")
    assert db.record_accepted_turn_affect(_accepted())["inserted"] == 1
    assert db.record_accepted_turn_affect(_accepted())["linked_existing"] == 1
    with db.connect(read_only=True) as con:
        assert con.execute("SELECT value FROM unified_memory_meta WHERE key='l0_schema_version'").fetchone()[0] == L0_SCHEMA_VERSION
        row = con.execute("SELECT turn_id,trace_id,conversation_id,message_source_record_id,link_status,linked_message_record_id FROM memory_l0_affect_message_links").fetchone()
        assert tuple(row) == ("turn-1","trace-1","chat-1","msg-1","explicit_source",None)
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_affect_requires_accepted_evidence_and_labels(tmp_path: Path) -> None:
    db = UnifiedMemoryDatabase(tmp_path / "db.sqlite3")
    for update in ({"finalization_status":"pending"},{"turn_id":""},{"modelled_affect":{"labels":[]}},{"context_sha256":"bad"}):
        with pytest.raises(ValueError):
            db.record_accepted_turn_affect({**_accepted(),**update})
    assert not db.path.exists()


def test_historical_labels_without_source_ids_stay_unlinked(tmp_path: Path) -> None:
    from latka_jazn.tools.memory_rebuild_app.intermediate import PreparedSource, IntermediateRecord
    from latka_jazn.tools.memory_rebuild_app.l0_store import UnifiedL0Store
    db = UnifiedMemoryDatabase(tmp_path / "db.sqlite3")
    db.initialize()
    raw = {"__jazn_affect_claims__":[{"label":"spokój","source_field":"emotions","claim_kind":"source_label"}]}
    record = IntermediateRecord(logical_key="legacy:1",source_record_id="old:1",record_kind="affective_memory",content="record",raw=raw)
    prepared = PreparedSource(adapter_id="test/v1",source_kind="affective",source_sha256="a"*64,
        source_name="synthetic",source_member=None,metadata={},record_factory=lambda:iter([record]),native_projection="l0_only")
    UnifiedL0Store(db.path).ingest(prepared)
    with db.connect(read_only=True) as con:
        assert tuple(con.execute("SELECT link_status,turn_id,linked_message_record_id FROM memory_l0_affect_message_links").fetchone()) == ("source_only","",None)
