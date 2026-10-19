from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import zipfile

from latka_jazn.tools.memory_rebuild_app.baseline_registry import discover_baseline_roots
from latka_jazn.tools.memory_rebuild_app.controller import MemoryRebuildAppController
from latka_jazn.tools.memory_rebuild_app.models import BaselineSpec, RebuildProject, SourceSpec
from latka_jazn.tools.memory_rebuild_app.project_store import ProjectStore
from latka_jazn.tools.memory_rebuild_app.source_inventory import inspect_source
from latka_jazn.tools.memory_rebuild_app.sqlite_inspector import DATABASE_FILENAMES, compare_database_summaries, inspect_database_set


def _create_database_set(root: Path, *, conversations: int = 1, journals: int = 1) -> Path:
    db_root = root / "memory" / "sqlite"
    db_root.mkdir(parents=True)
    schemas = {
        "archive_chats": "CREATE TABLE conversations(id TEXT PRIMARY KEY); CREATE TABLE nodes(id TEXT PRIMARY KEY);",
        "journal": "CREATE TABLE journal_entries(id TEXT PRIMARY KEY);",
        "experience": "CREATE TABLE experience_candidates(id TEXT PRIMARY KEY); CREATE TABLE experiences(id TEXT PRIMARY KEY);",
        "memory_jazn": "CREATE TABLE memory_records(id TEXT PRIMARY KEY);",
        "import_catalog": "CREATE TABLE sources(id TEXT PRIMARY KEY);",
    }
    for name, filename in DATABASE_FILENAMES.items():
        with sqlite3.connect(db_root / filename) as connection:
            connection.executescript(schemas[name])
            if name == "archive_chats":
                connection.executemany("INSERT INTO conversations(id) VALUES (?)", [(f"c-{i}",) for i in range(conversations)])
            if name == "journal":
                connection.executemany("INSERT INTO journal_entries(id) VALUES (?)", [(f"j-{i}",) for i in range(journals)])
    return root


def test_project_roundtrip_preserves_source_order_and_forces_promotion_off(tmp_path: Path) -> None:
    project = RebuildProject.create("Pełna pamięć", tmp_path / "target")
    project.settings["automatic_l2"] = True
    project.add_source(SourceSpec.create(tmp_path / "b.json", role="journal", pipeline="memory_rebuild"))
    project.add_source(SourceSpec.create(tmp_path / "a.zip", role="chatgpt_export", pipeline="memory_rebuild"))
    project.move_source(project.sources[1].source_id, -1)
    restored = RebuildProject.from_dict(project.to_dict())
    assert [Path(item.path).name for item in restored.sources] == ["a.zip", "b.json"]
    assert [item.order for item in restored.sources] == [1, 2]
    assert restored.settings["automatic_l2"] is False
    assert restored.settings["automatic_l3"] is False


def test_project_store_is_atomic_and_keeps_history(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = RebuildProject.create("Projekt", tmp_path / "target")
    path = store.create(project)
    project.notes = "druga rewizja"
    project.touch()
    store.save(project)
    assert path.is_file()
    assert store.load(project.project_id).notes == "druga rewizja"
    assert list((store.history_root / project.project_id).glob("*.json"))


def test_source_inventory_detects_chat_export_and_zip_hazards(tmp_path: Path) -> None:
    safe = tmp_path / "chatgpt-export-2026-07-17.zip"
    with zipfile.ZipFile(safe, "w") as archive:
        archive.writestr("conversations.json", json.dumps([{"id": "c", "mapping": {"r": {}}}]))
        archive.writestr("chat.html", "<html></html>")
    inspection = inspect_source(safe, verify_zip_crc=True)
    assert inspection.ok
    assert inspection.role == "chatgpt_export"
    assert inspection.pipeline == "memory_rebuild"
    assert inspection.source_family == "chatgpt-2026-07-17"
    assert inspection.metadata["zip"]["conversation_members"] == ["conversations.json"]

    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.json", "{}")
    blocked = inspect_source(unsafe)
    assert not blocked.ok
    assert "blocking:zip_unsafe_paths" in blocked.warnings


def test_journal_and_layered_sources_are_separated(tmp_path: Path) -> None:
    journal = tmp_path / "journal_from_sqlite.jsonl"
    journal.write_text('{"journal_id":"1","text":"Wpis"}\n', encoding="utf-8")
    layered = tmp_path / "affective.jsonl"
    layered.write_text('{"emotion":"calm"}\n', encoding="utf-8")
    assert inspect_source(journal).pipeline == "memory_rebuild"
    assert inspect_source(layered).pipeline == "catalog_only"


def test_sqlite_baselines_are_read_only_and_comparable(tmp_path: Path) -> None:
    baseline_root = _create_database_set(tmp_path / "test03", conversations=2, journals=1)
    candidate_root = _create_database_set(tmp_path / "test05", conversations=3, journals=2)
    baseline = inspect_database_set(baseline_root, full_integrity=True)
    candidate = inspect_database_set(candidate_root, full_integrity=True)
    comparison = compare_database_summaries(baseline, candidate)
    assert baseline["ok"]
    assert candidate["ok"]
    assert comparison["ok"]
    assert not comparison["declines"]
    with sqlite3.connect(baseline_root / "memory" / "sqlite" / DATABASE_FILENAMES["archive_chats"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 2


def test_discover_baseline_roots_finds_nested_memory_sqlite(tmp_path: Path) -> None:
    root = _create_database_set(tmp_path / "tests" / "jazn_memory_test_04", conversations=1)
    assert root / "memory" / "sqlite" in discover_baseline_roots([tmp_path], max_depth=5)


def test_test04_export_keeps_journal_last_and_excludes_catalog_only(tmp_path: Path) -> None:
    chat = tmp_path / "chatgpt-export-2026-07-17.zip"
    journal = tmp_path / "journal.jsonl"
    layered = tmp_path / "semantic.jsonl"
    for path in (chat, journal, layered):
        path.write_text("{}\n", encoding="utf-8")
    project = RebuildProject.create("Test 04 R", tmp_path / "target")
    project.add_source(SourceSpec.create(chat, role="chatgpt_export", pipeline="memory_rebuild", approved=True))
    project.add_source(SourceSpec.create(layered, role="layered_memory", pipeline="catalog_only", approved=False))
    project.add_source(SourceSpec.create(journal, role="journal", pipeline="memory_rebuild", approved=True))
    store = ProjectStore(tmp_path / "projects")
    store.create(project)
    controller = MemoryRebuildAppController(project, store=store, tool_root=tmp_path / "repo")
    output = tmp_path / "source-manifest.private.json"
    controller.export_test04_manifest(output, baseline_test03_root=tmp_path / "test03", legacy_memory_root=tmp_path / "legacy")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [item["role"] for item in payload["sources"]] == ["chatgpt_export", "journal"]
    assert payload["sources"][-1]["role"] == "journal"
    assert payload["app_metadata"]["excluded_sources"][0]["role"] == "layered_memory"
    assert payload["operator_attestation"]["source_order_reviewed"] is False


def test_baseline_spec_is_always_immutable(tmp_path: Path) -> None:
    baseline = BaselineSpec.create(tmp_path / "test")
    baseline.immutable = False
    assert baseline.normalized().immutable is True
