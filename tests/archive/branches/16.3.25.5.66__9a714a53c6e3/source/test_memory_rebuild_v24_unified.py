from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from latka_jazn.tools.chat_export_importer import ChatExportImporter
from latka_jazn.tools.memory_rebuild_app.final_export import export_final_memory
from latka_jazn.tools.memory_rebuild_app.html_import import import_chat_html
from latka_jazn.tools.memory_rebuild_app.test_profiles import run_test_profile
from latka_jazn.tools.memory_rebuild_app.unified_memory import (
    CANONICAL_DATABASE_NAME,
    UNIFIED_SCHEMA_VERSION,
    UnifiedMemoryDatabase,
)
from latka_jazn.tools.memory_rebuild_journal import JournalReader, JournalStore


def _message(mid: str, role: str, text: str, timestamp: float) -> dict:
    return {
        "id": mid,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {},
    }


def _conversation(conversation_id: str, title: str, user_text: str, assistant_text: str) -> dict:
    root = f"{conversation_id}-root"
    user = f"{conversation_id}-user"
    assistant = f"{conversation_id}-assistant"
    return {
        "id": conversation_id,
        "title": title,
        "create_time": 100.0,
        "update_time": 102.0,
        "current_node": assistant,
        "mapping": {
            root: {"id": root, "parent": None, "children": [user], "message": None},
            user: {
                "id": user,
                "parent": root,
                "children": [assistant],
                "message": _message(f"{conversation_id}-m-user", "user", user_text, 101.0),
            },
            assistant: {
                "id": assistant,
                "parent": user,
                "children": [],
                "message": _message(f"{conversation_id}-m-assistant", "assistant", assistant_text, 102.0),
            },
        },
    }


def _write_conversations(path: Path, conversations: list[dict]) -> None:
    path.write_text(json.dumps(conversations, ensure_ascii=False), encoding="utf-8")


def _write_journal(path: Path) -> None:
    entry = {
        "id": "journal-1",
        "title": "Rozmowa o pamięci",
        "content": "Krzysztof potwierdził, że rozmowy historyczne i nowe mają należeć do jednej pamięci.",
        "data": "2026-07-30T20:00:00+02:00",
        "importance": 0.9,
        "granica_prawdy": "source_recorded",
    }
    path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_test04_acceptance(path: Path) -> Path:
    path.write_text(json.dumps({
        "final": {
            "structural_integrity": "passed",
            "source_completeness": "passed",
            "same_target_idempotence": "passed",
            "fresh_rebuild_reproducibility": "passed",
            "test03_reconciliation": "passed",
            "recall": "passed",
            "html_import_dry_run": "not_applicable",
            "multi_turn_review": "passed",
            "restart_continuity": "not_run",
        }
    }), encoding="utf-8")
    return path


def test_unified_database_imports_new_threads_and_dry_run_is_non_mutating(tmp_path: Path) -> None:
    database = tmp_path / CANONICAL_DATABASE_NAME
    first = tmp_path / "conversations-1.json"
    second = tmp_path / "conversations-2.json"
    journal = tmp_path / "journal.jsonl"
    _write_conversations(first, [_conversation("conv-1", "Pierwszy wątek", "Pamiętaj o Tayfie.", "Zachowuję źródło rozmowy.")])
    _write_conversations(second, [_conversation("conv-2", "Nowy wątek", "To jest nowa rozmowa.", "Zostanie dopisana przyrostowo.")])
    _write_journal(journal)

    store = UnifiedMemoryDatabase(database)
    initialized = store.initialize()
    assert initialized["schema_version"] == UNIFIED_SCHEMA_VERSION
    assert database.is_file()
    assert not any((tmp_path / name).exists() for name in ("archive_chats.sqlite3", "journal.sqlite3", "experience.sqlite3", "import_catalog.sqlite3"))

    first_result = store.import_sources([first, journal])
    assert first_result["ok"]
    initial_stats = store.stats()
    assert initial_stats["conversations"] == 1
    assert initial_stats["journal_entries"] == 1

    duplicate = store.import_sources([first])
    assert duplicate["ok"]
    assert store.stats()["conversations"] == 1

    preview = store.import_sources([second], dry_run=True)
    assert preview["ok"]
    assert preview["status"] == "plan_only"
    assert store.stats()["conversations"] == 1

    appended = store.import_sources([second])
    assert appended["ok"]
    assert store.stats()["conversations"] == 2
    assert store.validate(full=True)["ok"]


def test_html_import_reports_exact_lossless_and_lossy_semantics(tmp_path: Path) -> None:
    embedded_database = tmp_path / "embedded.sqlite3"
    embedded_html = tmp_path / "chat-embedded.html"
    payload = [_conversation("conv-html", "HTML JSON", "Treść użytkownika", "Treść odpowiedzi")]
    embedded_html.write_text(
        "<html><body><script>var jsonData = " + json.dumps(payload, ensure_ascii=False) + ";</script></body></html>",
        encoding="utf-8",
    )
    embedded = import_chat_html(embedded_html, embedded_database)
    assert embedded.mode == "embedded_json_lossless"
    assert embedded.conversations_seen == 1
    assert UnifiedMemoryDatabase(embedded_database).stats()["conversations"] == 1

    fallback_database = tmp_path / "fallback.sqlite3"
    fallback_html = tmp_path / "chat-rendered.html"
    fallback_html.write_text(
        '<div class="conversation"><h4>Widoczna rozmowa</h4>'
        '<pre class="message">Pierwsza wiadomość</pre>'
        '<pre class="message">Druga wiadomość</pre></div>',
        encoding="utf-8",
    )
    fallback = import_chat_html(fallback_html, fallback_database)
    assert fallback.mode == "rendered_html_lossy"
    assert fallback.conversations_seen == 1
    assert UnifiedMemoryDatabase(fallback_database).stats()["nodes"] >= 2


def test_candidate_edit_revision_evidence_review_and_relations(tmp_path: Path) -> None:
    database = tmp_path / CANONICAL_DATABASE_NAME
    conversation = tmp_path / "conversations.json"
    journal = tmp_path / "journal.jsonl"
    _write_conversations(conversation, [_conversation("conv-c", "Pamięć relacyjna", "Tayfa jest moim kotem.", "To ważna informacja relacyjna.")])
    _write_journal(journal)
    store = UnifiedMemoryDatabase(database)
    assert store.import_sources([conversation, journal])["ok"]

    generated = store.generate_candidates(chats=False, journal=True)
    assert generated["ok"]
    candidates = store.list_candidates(status="pending_review")
    assert candidates
    candidate_id = str(candidates[0]["candidate_id"])

    edited = store.edit_candidate(
        candidate_id,
        {
            "title": "Jedna pamięć rozmów",
            "summary": "Rozmowy archiwalne i nowe są częścią tego samego magazynu pamięci.",
            "truth_status": "user_confirmed",
            "confidence": 0.95,
            "importance": 0.92,
            "domains_json": ["identity", "relationship"],
        },
        edited_by="Krzysztof",
        reason="Korekta znaczenia źródła",
    )
    assert edited["title"] == "Jedna pamięć rozmów"
    assert len(edited["revisions"]) == 1

    with_evidence = store.add_candidate_evidence(
        candidate_id,
        source_database=CANONICAL_DATABASE_NAME,
        source_type="conversation_message",
        source_record_id="conv-c-user",
        excerpt="Tayfa jest moim kotem.",
        context_before="",
        context_after="To ważna informacja relacyjna.",
    )
    assert len(with_evidence["evidence"]) == 1

    split = store.split_candidate(
        candidate_id,
        title="Osobny ślad o Tayfie",
        summary="Tayfa jest kotem Krzysztofa.",
        edited_by="Krzysztof",
        reason="Rozdzielenie dwóch znaczeń",
    )
    merged = store.merge_candidates(
        [candidate_id, str(split["candidate_id"])],
        title="Połączony ślad relacyjny",
        summary="Połączony kandydat zachowujący oba dowody.",
        edited_by="Krzysztof",
        reason="Test łączenia kandydatów",
    )
    assert merged["links"]

    review = store.review_candidate(
        str(merged["candidate_id"]),
        decision="approve",
        reviewed_by="Krzysztof",
        reason="Dowody potwierdzone ręcznie",
    )
    assert review["ok"]
    assert store.stats()["experiences"] == 1
    assert store.stats()["memory_records"] == 0


def test_legacy_databases_migrate_into_single_database(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    archive = legacy_root / "archive_chats.sqlite3"
    journal_database = legacy_root / "journal.sqlite3"
    source = tmp_path / "legacy-conversations.json"
    journal_file = tmp_path / "legacy-journal.jsonl"
    _write_conversations(source, [_conversation("legacy-conv", "Stara rozmowa", "Stare źródło", "Zachowane")])
    _write_journal(journal_file)
    ChatExportImporter().import_one(source, archive)
    with JournalStore(journal_database) as journal_store:
        journal_store.import_reader(JournalReader(journal_file))

    target = tmp_path / CANONICAL_DATABASE_NAME
    store = UnifiedMemoryDatabase(target)
    preview = store.migrate_legacy_root(legacy_root, dry_run=True)
    assert preview["ok"]
    assert not target.exists()

    migrated = store.migrate_legacy_root(legacy_root)
    assert migrated["ok"]
    assert store.stats()["conversations"] == 1
    assert store.stats()["journal_entries"] == 1
    assert store.validate(full=True)["ok"]


def test_profiles_and_final_export_build_verified_staging_copy(tmp_path: Path) -> None:
    database = tmp_path / CANONICAL_DATABASE_NAME
    source = tmp_path / "final-conversations.json"
    journal = tmp_path / "final-journal.jsonl"
    _write_conversations(source, [_conversation("final-conv", "Finalny wątek", "Źródło finalne", "Odpowiedź finalna")])
    _write_journal(journal)
    store = UnifiedMemoryDatabase(database)
    assert store.import_sources([source, journal])["ok"]

    for profile in ("test01", "test02", "test03"):
        report = run_test_profile(database, profile)
        assert report["ok"], report

    # v16.0 contract: Test04/final cannot pass without an immutable baseline and
    # evidence from the canonical full Test04 acceptance protocol.
    assert not run_test_profile(database, "test04")["ok"]
    baseline = tmp_path / "baseline.sqlite3"
    store.backup(baseline)
    acceptance = _write_test04_acceptance(tmp_path / "summary.sanitized.json")
    for profile in ("test04", "final"):
        report = run_test_profile(database, profile, baselines=[baseline], acceptance_report=acceptance)
        assert report["ok"], report

    output = tmp_path / "final-export"
    result = export_final_memory(
        database, output, baselines=[baseline], sources=[source, journal],
        acceptance_report=acceptance,
    )
    assert result["ok"]
    assert (output / CANONICAL_DATABASE_NAME).is_file()
    assert (output / "source-manifest.private.json").is_file()
    assert (output / "source-manifest.sanitized.json").is_file()
    assert (output / "test-profile-final.private.json").is_file()
    assert (output / "test-profile-final.sanitized.json").is_file()
    assert (output / "candidate-review-ledger.json").is_file()
    assert (output / "database-manifest.json").is_file()
    assert (output / "final-export-summary.json").is_file()
    assert UnifiedMemoryDatabase(output / CANONICAL_DATABASE_NAME).validate(full=True)["ok"]
    with sqlite3.connect(output / CANONICAL_DATABASE_NAME) as con:
        assert con.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1
