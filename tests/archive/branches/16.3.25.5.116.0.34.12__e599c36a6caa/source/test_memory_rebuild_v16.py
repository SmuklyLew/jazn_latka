from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sqlite3
import subprocess
import sys
import zipfile

import pytest

from latka_jazn.tools.chat_export_importer import ChatExportImporter
from latka_jazn.tools.memory_rebuild_app.read_only_validation import (
    promotion_ledger_validation,
    validate_existing_database,
)
from latka_jazn.tools.memory_rebuild_app.report_sanitizer import sanitize_report
from latka_jazn.tools.memory_rebuild_app.runtime_sync import sync_runtime
from latka_jazn.tools.memory_rebuild_app.source_detection import probe_source
from latka_jazn.tools.memory_rebuild_app.test_profiles import run_test_profile
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase
from latka_jazn.tools.memory_rebuild_journal import JournalReader, JournalStore


def _message(mid: str, role: str, text: str, timestamp: float) -> dict:
    return {
        "id": mid,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {},
    }


def _conversation(conversation_id: str, user_text: str, assistant_text: str) -> dict:
    root = f"{conversation_id}-root"
    user = f"{conversation_id}-user"
    assistant = f"{conversation_id}-assistant"
    return {
        "id": conversation_id,
        "title": "Test pamięci",
        "create_time": 100.0,
        "update_time": 102.0,
        "current_node": assistant,
        "mapping": {
            root: {"id": root, "parent": None, "children": [user], "message": None},
            user: {
                "id": user, "parent": root, "children": [assistant],
                "message": _message(f"{conversation_id}-u", "user", user_text, 101.0),
            },
            assistant: {
                "id": assistant, "parent": user, "children": [],
                "message": _message(f"{conversation_id}-a", "assistant", assistant_text, 102.0),
            },
        },
    }


def _seed_unified(tmp_path: Path) -> tuple[Path, Path, Path]:
    database = tmp_path / "memory_jazn.sqlite3"
    chat = tmp_path / "conversations.json"
    journal = tmp_path / "dziennik.jsonl"
    chat.write_text(json.dumps([_conversation("conv-1", "Pamiętaj o źródle.", "Źródło pozostaje w pamięci.")], ensure_ascii=False), encoding="utf-8")
    journal.write_text(json.dumps({
        "id": "journal-1", "title": "Pamięć", "content": "Dziennik zachowuje źródło rozmowy.",
        "timestamp": "2026-08-25T10:00:00+02:00", "truth_status": "source_recorded",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    store = UnifiedMemoryDatabase(database)
    assert store.import_sources([chat, journal])["ok"]
    return database, chat, journal


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _acceptance_report(path: Path, *, restart: str = "not_run") -> Path:
    payload = {
        "final": {
            "structural_integrity": "passed",
            "source_completeness": "passed",
            "same_target_idempotence": "passed",
            "fresh_rebuild_reproducibility": "passed",
            "test03_reconciliation": "passed",
            "recall": "passed",
            "html_import_dry_run": "not_applicable",
            "multi_turn_review": "passed",
            "restart_continuity": restart,
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_v16_launcher_is_thin_and_has_no_runtime_monkeypatch() -> None:
    canonical = Path("tools/rebuild_memory.py").read_text(encoding="utf-8")
    compatibility = Path("tools/memory_rebuild.py").read_text(encoding="utf-8")
    config = Path("latka_jazn/tools/memory_rebuild_app/config.py").read_text(encoding="utf-8")
    assert 'TOOL_VERSION = "memory-rebuild/v16.1"' in config
    assert len(canonical.splitlines()) < 20
    assert len(compatibility.splitlines()) < 20
    assert "_install_chat_export_reader_hardening" not in canonical + compatibility
    assert "memory_rebuild_app.entrypoint import main" in canonical


@pytest.mark.parametrize("name", ("rebuild_memory.py", "memory_rebuild.py"))
def test_v16_launchers_bootstrap_repo_from_foreign_cwd(tmp_path: Path, name: str) -> None:
    launcher = Path(__file__).resolve().parents[1] / "tools" / name
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", str(launcher), "--version"],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "memory-rebuild/v16.1"


def test_read_only_validation_does_not_create_or_modify_database(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    result = validate_existing_database(missing, full=True)
    assert not result["ok"]
    assert result["reason"] == "database_missing"
    assert not missing.exists()

    database, _, _ = _seed_unified(tmp_path)
    before_sha = _sha(database)
    before_mtime = database.stat().st_mtime_ns
    report = run_test_profile(database, "test03")
    assert report["ok"], report
    assert report["read_only"] is True
    assert report["target_modified"] is False
    assert _sha(database) == before_sha
    assert database.stat().st_mtime_ns == before_mtime


def test_fts_integrity_and_real_match_smoke_are_required(tmp_path: Path) -> None:
    database, _, _ = _seed_unified(tmp_path)
    report = validate_existing_database(database, full=True, include_fts=True)
    assert report["ok"], report
    assert report["fts"]["missing_required_tables"] == []
    message = report["fts"]["smoke"]["message_fts"]
    journal = report["fts"]["smoke"]["journal_fts"]
    assert message["status"] == "passed" and message["matches"] > 0
    assert journal["status"] == "passed" and journal["matches"] > 0
    assert report["fts"]["integrity"]["message_fts"]["status"] == "passed"


def test_test04_profile_requires_baseline_and_full_acceptance_evidence(tmp_path: Path) -> None:
    database, _, _ = _seed_unified(tmp_path)
    without = run_test_profile(database, "test04")
    assert not without["ok"]
    names = {item["name"] for item in without["blocking_failures"]}
    assert "test03_record_level_reconciliation" in names
    assert "full_test04_acceptance" in names

    baseline = tmp_path / "baseline.sqlite3"
    UnifiedMemoryDatabase(database).backup(baseline)
    acceptance = _acceptance_report(tmp_path / "summary.sanitized.json")
    passed = run_test_profile(database, "test04", baselines=[baseline], acceptance_report=acceptance)
    assert passed["ok"], passed

    system = run_test_profile(
        database, "test04", baselines=[baseline], acceptance_report=acceptance, system_acceptance=True,
    )
    assert not system["ok"]
    acceptance_restart = _acceptance_report(tmp_path / "summary-system.sanitized.json", restart="passed")
    system_ok = run_test_profile(
        database, "test04", baselines=[baseline], acceptance_report=acceptance_restart, system_acceptance=True,
    )
    assert system_ok["ok"], system_ok


def test_final_profile_derives_l2_l3_from_persisted_ledger(tmp_path: Path) -> None:
    database, _, _ = _seed_unified(tmp_path)
    baseline = tmp_path / "baseline.sqlite3"
    UnifiedMemoryDatabase(database).backup(baseline)
    acceptance = _acceptance_report(tmp_path / "summary.sanitized.json")
    ledger = promotion_ledger_validation(database)
    assert ledger["ok"]
    assert ledger["automatic_l2"] is False
    assert ledger["automatic_l3"] is False
    report = run_test_profile(database, "final", baselines=[baseline], acceptance_report=acceptance)
    assert report["ok"], report
    assert report["automatic_l2"] is False
    assert report["automatic_l3"] is False


def test_source_detector_is_schema_aware_for_jsonl_and_zip(tmp_path: Path) -> None:
    episodic = tmp_path / "episodic.jsonl"
    episodic.write_text('{"episode_id":"e1","event_time":"2026-08-25T00:00:00Z","content":"wspomnienie"}\n', encoding="utf-8")
    semantic = tmp_path / "semantic.jsonl"
    semantic.write_text('{"fact_id":"f1","subject":"Tayfa","predicate":"is","object":"cat"}\n', encoding="utf-8")
    events = tmp_path / "runtime_events.jsonl"
    events.write_text('{"event_id":"r1","turn_id":"t1","trace_id":"x1","event_type":"turn"}\n', encoding="utf-8")
    journal = tmp_path / "dziennik.jsonl"
    journal.write_text('{"entry_id":"j1","title":"Dziennik","content":"wpis"}\n', encoding="utf-8")
    assert probe_source(episodic).kind == "episodic"
    assert probe_source(semantic).kind == "semantic"
    assert probe_source(events).kind == "runtime_events"
    assert probe_source(journal).kind == "journal"

    unknown = tmp_path / "unknown.zip"
    with zipfile.ZipFile(unknown, "w") as archive:
        archive.writestr("data.json", "{}")
    assert probe_source(unknown).kind == "reference"

    chat = tmp_path / "chat.zip"
    with zipfile.ZipFile(chat, "w") as archive:
        archive.writestr("conversations.json", "[]")
    assert probe_source(chat).kind == "chat"


def test_journal_jsonl_import_is_streaming_and_does_not_call_items(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    UnifiedMemoryDatabase(database).initialize()
    journal = tmp_path / "large-shape.jsonl"
    journal.write_text(
        "\n".join(json.dumps({"id": f"j-{i}", "title": "Wpis", "content": f"Treść {i}"}, ensure_ascii=False) for i in range(30)) + "\n",
        encoding="utf-8",
    )

    class StreamingOnlyReader(JournalReader):
        def items(self):  # pragma: no cover - must never be used
            raise AssertionError("JSONL importer materialized the whole file")

    reader = StreamingOnlyReader(journal)
    with JournalStore(database) as store:
        result = store.import_reader(reader)
    assert result["ok"]
    assert result["streaming_jsonl"] is True
    assert result["entries_seen"] == 30


def test_runtime_sync_separates_kinds_and_publishes_atomically(tmp_path: Path) -> None:
    database, _, _ = _seed_unified(tmp_path)
    runtime = tmp_path / "runtime"
    layered = runtime / "memory" / "layered"
    layered.mkdir(parents=True)
    (layered / "episodic.jsonl").write_text('{"episode_id":"e1","content":"Epizod"}\n', encoding="utf-8")
    (layered / "semantic.jsonl").write_text('{"fact_id":"f1","subject":"A","predicate":"B","object":"C"}\n', encoding="utf-8")
    (layered / "affective.jsonl").write_text('{"id":"a1","emotions":["spokój"],"reflection":"Refleksja"}\n', encoding="utf-8")
    (layered / "procedural.jsonl").write_text('{"id":"p1","procedure":"Krok po kroku"}\n', encoding="utf-8")
    (layered / "source_origin_ledger.jsonl").write_text('{"ledger_id":"l1","source_type":"chat","source_sha256":"abc"}\n', encoding="utf-8")
    (layered / "runtime_events.jsonl").write_text('{"event_id":"r1","turn_id":"t1","trace_id":"x1","event_type":"turn"}\n', encoding="utf-8")
    before = _sha(database)
    result = sync_runtime(database, runtime, full_validation=True)
    assert result["ok"], result
    assert result["status"] == "published"
    assert result["target_sha256_before"] == before
    assert result["target_sha256_after"] == _sha(database)
    assert set(result["source_kind_counts"]) >= {
        "episodic", "semantic", "affective", "procedural", "provenance_ledger", "runtime_events",
    }
    with sqlite3.connect(database) as con:
        kinds = dict(con.execute(
            "SELECT source_kind,COUNT(*) FROM runtime_memory_records_l0 WHERE active=1 GROUP BY source_kind"
        ).fetchall())
    for kind in ("episodic", "semantic", "affective", "procedural", "provenance_ledger", "runtime_events"):
        assert kinds[kind] == 1


def test_runtime_sync_failure_keeps_target_byte_identical(tmp_path: Path) -> None:
    database, _, _ = _seed_unified(tmp_path)
    runtime = tmp_path / "runtime"
    layered = runtime / "memory" / "layered"
    layered.mkdir(parents=True)
    rows = [json.dumps({"event_id": f"r{i}", "turn_id": f"t{i}", "event_type": "turn"}) for i in range(9)]
    rows.append("{not-json}")
    (layered / "runtime_events.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    before = _sha(database)
    result = sync_runtime(database, runtime, full_validation=False)
    assert not result["ok"]
    assert result["status"] == "staging_rejected"
    assert result["target_modified"] is False
    assert _sha(database) == before


def test_legacy_migration_conflict_is_explicit_and_target_is_not_replaced(tmp_path: Path) -> None:
    target = tmp_path / "memory_jazn.sqlite3"
    first = tmp_path / "first.json"
    first.write_text(json.dumps([_conversation("same-id", "wersja A", "odpowiedź A")], ensure_ascii=False), encoding="utf-8")
    store = UnifiedMemoryDatabase(target)
    assert store.import_sources([first])["ok"]
    before = _sha(target)

    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    archive = legacy_root / "archive_chats.sqlite3"
    second = tmp_path / "second.json"
    second.write_text(json.dumps([_conversation("same-id", "wersja B", "odpowiedź B")], ensure_ascii=False), encoding="utf-8")
    ChatExportImporter().import_one(second, archive)

    with pytest.raises(sqlite3.IntegrityError):
        store.migrate_legacy_root(legacy_root)
    assert _sha(target) == before
    migration_source = Path("latka_jazn/tools/memory_rebuild_app/unified_migration.py").read_text(encoding="utf-8")
    assert "INSERT OR IGNORE" not in migration_source.upper()


def test_sanitized_report_never_contains_absolute_source_path(tmp_path: Path) -> None:
    secret = (tmp_path / "PRIVATE" / "chat.json").resolve()
    payload = {"source": str(secret), "nested": {"sources": [str(secret)]}}
    sanitized = sanitize_report(payload)
    text = json.dumps(sanitized, ensure_ascii=False)
    assert str(secret) not in text
    assert "locator_sha256" in text
