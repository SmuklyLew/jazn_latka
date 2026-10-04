from __future__ import annotations

from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys

import pytest

from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.chat_export_reader import sha256_file
from latka_jazn.tools.memory_rebuild_app.canonical_rebuild import (
    CanonicalMemoryRebuildPipeline,
    canonical_database_path,
)
from latka_jazn.tools.memory_rebuild_app import controller as controller_module
from latka_jazn.tools.memory_rebuild_app import final_export as final_export_module
from latka_jazn.tools.memory_rebuild_app import test_profiles as test_profiles_module
from latka_jazn.tools.memory_rebuild_app.controller import MemoryRebuildAppController
from latka_jazn.tools.memory_rebuild_app.models import RebuildProject, SourceSpec
from latka_jazn.tools.memory_rebuild_app.project_store import ProjectStore
from latka_jazn.tools.memory_rebuild_app.test_profiles import (
    baseline_record_reconciliation,
    semantic_database_fingerprint,
)
from latka_jazn.tools.memory_rebuild_app.test_spec import validate_test_layer_contracts
from latka_jazn.tools.memory_rebuild_coordinator import MemoryRebuildCoordinator
from latka_jazn.tools.memory_restore import confirmation_token
from latka_jazn.tools import memory_restore_types as memory_restore_types_module


def _message(mid: str, role: str, text: str, timestamp: float) -> dict:
    return {
        "id": mid,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {},
    }


def _conversation(conversation_id: str, title: str, marker: str) -> dict:
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
                "message": _message(
                    f"{conversation_id}-m-user",
                    "user",
                    f"Źródło pamięci {marker}",
                    101.0,
                ),
            },
            assistant: {
                "id": assistant,
                "parent": user,
                "children": [],
                "message": _message(
                    f"{conversation_id}-m-assistant",
                    "assistant",
                    f"Zachowuję źródło {marker}",
                    102.0,
                ),
            },
        },
    }


def _write_conversations(path: Path, conversation_id: str, marker: str) -> Path:
    path.write_text(
        json.dumps(
            [_conversation(conversation_id, f"Rozmowa {marker}", marker)],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _write_benchmark(path: Path) -> Path:
    categories = (
        "direct",
        "paraphrase",
        "referential_followup",
        "temporal",
        "update",
        "conflict",
        "provenance",
        "sensitive_boundary",
    )
    cases: list[dict[str, object]] = []
    for category in categories:
        case: dict[str, object] = {
            "id": f"case-{category}",
            "query": "Źródło",
            "category": category,
            "expected_any": ["Źródło"],
            "limit": 20,
        }
        if category == "referential_followup":
            case["context_turns"] = ["Źródło"]
        if category == "temporal":
            case["temporal_start"] = "1970-01-01T00:00:00+00:00"
            case["temporal_end"] = "2100-01-01T00:00:00+00:00"
        if category == "provenance":
            case["expected_source_kinds"] = ["chatgpt_conversation"]
        if category == "sensitive_boundary":
            case["forbidden_any"] = ["never-present-sensitive-marker"]
        cases.append(case)
    cases.append(
        {
            "id": "case-negative",
            "query": "term-that-cannot-possibly-exist-studio-104",
            "category": "negative",
            "expected_abstain": True,
            "minimum_hits": 0,
        }
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": "jazn_memory_recall_benchmark/v2",
                "suite_id": "studio-reconstruction-104",
                "cases": cases,
                "minimums": {
                    "recall_at_20": 1.0,
                    "mrr": 1.0,
                    "ndcg": 1.0,
                    "abstention_accuracy": 1.0,
                    "provenance_accuracy": 1.0,
                    "temporal_accuracy": 1.0,
                    "max_sensitive_leakage_rate": 0.0,
                    "max_false_memory_rate": 0.0,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _source(path: Path, *, order: int = 1) -> SourceSpec:
    return SourceSpec.create(
        path,
        role="chatgpt_export",
        truth_domain="conversation_event",
        pipeline="memory_rebuild",
        approved=True,
        status="ready",
        order=order,
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
    )


def _project(tmp_path: Path, source: Path, *, name: str = "Rebuild") -> RebuildProject:
    project = RebuildProject.create(name, tmp_path / "target")
    project.sources = [_source(source)]
    project.settings["test04_benchmark"] = str(
        _write_benchmark(tmp_path / "test04-benchmark.private.json")
    )
    return project.normalized()


def test_studio_rebuild_publishes_only_runtime_ready_unified_database(tmp_path: Path) -> None:
    source = _write_conversations(tmp_path / "conversations.json", "conv-new", "nowe")
    project = _project(tmp_path, source)
    store = ProjectStore(tmp_path / "projects")
    controller = MemoryRebuildAppController(
        project,
        store=store,
        tool_root=Path.cwd(),
    )

    plan = controller.plan()
    engine = plan["engine_plan"]
    expected_database = tmp_path / "target" / "memory" / "sqlite" / "memory_jazn.sqlite3"
    assert engine["pipeline_owner"] == "UnifiedMemoryDatabase"
    assert Path(engine["canonical_database"]) == expected_database
    assert canonical_database_path(project.target_root) == expected_database
    assert engine["memory_generation"] == "alpha"
    assert engine["source_union_sha256"]

    result = controller.run(
        confirmation=confirmation_token(controller.settings()),
        prepared_plan=plan,
    )["engine_result"]

    assert result["ok"], result
    assert result["status"] == "native_unified_published"
    assert result["memory_generation"] == "alpha"
    assert result["memory_readiness_class"] == "native_unified"
    assert result["protocol_gate"]["ok"] is True
    assert result["protocol_gate"]["test00"] == "PASSED"
    assert result["protocol_gate"]["test04"] == "PASSED"
    assert result["protocol_gate"]["final"] == "PASSED"
    assert result["protocol_gate"]["test04_candidate_transition"] is True
    assert result["protocol_gate"]["test04_database_sha256"]
    assert result["protocol_gate"]["test04_database_fingerprint"]
    assert result["memory_search_ready"] is True
    assert result["full_autobiographical_recall_ready"] is True
    assert expected_database.is_file()
    assert result["candidate_test04_validation"]["ok"] is True
    acceptance = json.loads(
        Path(result["test04_acceptance_report"]).read_text(encoding="utf-8")
    )
    assert acceptance["binding"]["database_semantic_fingerprint"] == (
        semantic_database_fingerprint(expected_database)
    )
    assert acceptance["binding"]["source_union_sha256"] == result["source_union_sha256"]
    assert acceptance["binding"]["restore_run_id"] == result["run_id"]
    assert acceptance["binding"]["protocol_run_id"] == result["protocol_gate"]["run_id"]

    probe = probe_unified_memory_database(expected_database, full_integrity=True)
    assert probe["status"] == "ready_native_unified"
    assert probe["full_autobiographical_recall_ready"] is True
    siblings = {
        "archive_chats.sqlite3",
        "journal.sqlite3",
        "experience.sqlite3",
        "import_catalog.sqlite3",
    }
    assert not any((expected_database.parent / name).exists() for name in siblings)


def test_existing_alpha_layout_is_snapshotted_then_converged_to_beta(tmp_path: Path) -> None:
    source = _write_conversations(tmp_path / "conversations.json", "conv-beta", "beta")
    project = _project(tmp_path, source, name="Alpha to Beta")
    target = Path(project.target_root)

    legacy = MemoryRebuildCoordinator(target)
    initialized = legacy.init()
    assert initialized["ok"]
    alpha_database = legacy.paths.memory_jazn
    alpha_file_sha = sha256_file(alpha_database)

    controller = MemoryRebuildAppController(
        project,
        store=ProjectStore(tmp_path / "projects"),
        tool_root=Path.cwd(),
    )
    plan = controller.plan()
    assert plan["engine_plan"]["memory_generation"] == "beta"
    assert plan["engine_plan"]["existing_database_count"] == 5

    result = controller.run(
        confirmation=confirmation_token(controller.settings()),
        prepared_plan=plan,
    )["engine_result"]

    assert result["ok"], result
    assert result["memory_generation"] == "beta"
    assert result["baseline_snapshot_count"] == 5
    assert result["parent_database_sha256"]
    assert result["protocol_gate"]["ok"] is True
    assert result["baseline_reconciliation"]["ok"] is True

    baseline_root = Path(result["baseline_root"])
    manifest = json.loads((baseline_root / "baseline-manifest.json").read_text(encoding="utf-8"))
    alpha = [
        item
        for item in manifest["snapshots"]
        if item.get("baseline_role") == "alpha_parent"
    ]
    assert len(alpha) == 1
    assert alpha[0]["source_file_sha256"] == alpha_file_sha
    assert (baseline_root / "sqlite" / "memory_jazn.sqlite3").is_file()

    final_database = canonical_database_path(target)
    assert final_database.is_file()
    assert probe_unified_memory_database(
        final_database,
        full_integrity=True,
    )["full_autobiographical_recall_ready"] is True
    for name in (
        "archive_chats.sqlite3",
        "journal.sqlite3",
        "experience.sqlite3",
        "import_catalog.sqlite3",
    ):
        assert not (final_database.parent / name).exists()


def test_source_union_fingerprint_is_independent_of_project_order_and_source_ids(
    tmp_path: Path,
) -> None:
    first = _write_conversations(tmp_path / "a.json", "conv-a", "A")
    second = _write_conversations(tmp_path / "b.json", "conv-b", "B")

    benchmark = _write_benchmark(tmp_path / "union-benchmark.private.json")
    left = RebuildProject.create("left", tmp_path / "left-target")
    left.sources = [_source(first, order=1), _source(second, order=2)]
    left.settings["test04_benchmark"] = str(benchmark)
    right = RebuildProject.create("right", tmp_path / "right-target")
    right.sources = [_source(second, order=1), _source(first, order=2)]
    right.settings["test04_benchmark"] = str(benchmark)

    left_plan = CanonicalMemoryRebuildPipeline(left).plan()
    right_plan = CanonicalMemoryRebuildPipeline(right).plan()

    assert left_plan["ok"] and right_plan["ok"]
    assert left_plan["source_union_sha256"] == right_plan["source_union_sha256"]


def test_each_memory_protocol_test_has_one_layer_owner_and_ordered_gate() -> None:
    report = validate_test_layer_contracts()
    assert report["ok"], report
    raw_contracts = report.get("contracts")
    assert isinstance(raw_contracts, tuple)
    contracts: dict[str, dict[str, object]] = {}
    for item in raw_contracts:
        assert isinstance(item, dict)
        profile = item.get("profile")
        assert isinstance(profile, str)
        contracts[profile] = item
    assert contracts["test00"]["owner_layer"] == "source_fidelity_and_union"
    assert contracts["test01"]["required_predecessors"] == ("test00",)
    assert contracts["test02"]["required_predecessors"] == ("test01",)
    assert contracts["test03"]["required_predecessors"] == ("test02",)
    assert contracts["test04"]["required_predecessors"] == ("test03",)
    assert contracts["final"]["required_predecessors"] == ("test04",)
    assert contracts["final"]["gate_kind"] == "export_and_readiness"



def test_prepared_plan_is_stale_when_test04_benchmark_changes(tmp_path: Path) -> None:
    source = _write_conversations(tmp_path / "conversations.json", "conv-plan", "plan")
    project = _project(tmp_path, source, name="Plan binding")
    pipeline = CanonicalMemoryRebuildPipeline(project, tool_root=Path.cwd())
    prepared = pipeline.plan()
    assert prepared["ok"], prepared
    assert prepared["execution_plan_sha256"]

    benchmark = Path(project.settings["test04_benchmark"])
    benchmark.write_text(
        benchmark.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    result = pipeline.run(prepared_plan=prepared)
    assert result["ok"] is False
    assert result["status"] == "prepared_plan_stale"
    assert result["field"] == "execution_plan_sha256"
    assert result["expected"] == prepared["execution_plan_sha256"]
    assert result["actual"] != prepared["execution_plan_sha256"]


def test_baseline_reconciliation_detects_same_key_content_change(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.sqlite3"
    target = tmp_path / "target.sqlite3"
    for path, title in ((baseline, "before"), (target, "after")):
        with sqlite3.connect(path) as con:
            con.execute(
                "CREATE TABLE conversations("
                "conversation_id TEXT PRIMARY KEY,"
                "title TEXT NOT NULL"
                ")"
            )
            con.execute(
                "INSERT INTO conversations(conversation_id,title) VALUES(?,?)",
                ("conv-1", title),
            )
            con.commit()

    report = baseline_record_reconciliation(target, [baseline])
    assert report["ok"] is False
    assert report["tables"]["conversations"]["missing_record_count"] == 0
    assert report["tables"]["conversations"]["content_mismatch_count"] == 1


def test_memory_evidence_resolver_rejects_paths_outside_memory_root(
    tmp_path: Path,
) -> None:
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    inside = memory_root / "rebuild_baselines" / "report.json"
    inside.parent.mkdir(parents=True)
    inside.write_text("{}", encoding="utf-8")

    resolved = final_export_module._resolve_memory_evidence(
        memory_root,
        "rebuild_baselines/report.json",
    )
    assert resolved == inside.resolve()

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inside canonical memory root"):
        final_export_module._resolve_memory_evidence(memory_root, outside)


def test_final_publish_restores_old_target_when_second_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "final"
    staging = tmp_path / "final.staging"
    target.mkdir()
    staging.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    (staging / "new.txt").write_text("new", encoding="utf-8")

    original_replace = os.replace
    calls = 0

    def fail_second_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic publish failure")
        original_replace(src, dst)

    monkeypatch.setattr(final_export_module.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="synthetic publish failure"):
        final_export_module._publish_directory_atomically(
            staging,
            target,
            overwrite=True,
        )

    assert target.is_dir()
    assert (target / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (target / "new.txt").exists()


def test_system_mode_preflight_rejects_active_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_conversations(tmp_path / "conversations.json", "conv-system", "system")
    project = _project(tmp_path, source, name="System gate")
    project.mode = "system"

    monkeypatch.setattr(
        controller_module,
        "target_preflight",
        lambda settings, tool_root=None: {
            "ok": False,
            "mode": "system",
            "target_root": settings.target_root,
            "blocking_errors": ["system_runtime_must_be_stopped"],
            "warnings": [],
            "evidence": {"daemon": {"pid_alive": True}},
        },
    )
    controller = MemoryRebuildAppController(
        project,
        store=ProjectStore(tmp_path / "projects"),
        tool_root=Path.cwd(),
    )

    report = controller.preflight()
    assert report["ok"] is False
    assert "system_runtime_must_be_stopped" in report["errors"]
    assert report["runtime_target_preflight"]["ok"] is False



def test_test04_acceptance_binding_rejects_report_from_different_candidate(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "acceptance.json"
    final = {
        "structural_integrity": "passed",
        "source_completeness": "passed",
        "same_target_idempotence": "passed",
        "fresh_rebuild_reproducibility": "passed",
        "test03_reconciliation": "passed",
        "recall": "passed",
        "multi_turn_review": "passed",
        "html_import_dry_run": "not_applicable",
        "restart_continuity": "not_run",
    }
    payload = {
        "schema_version": "jazn_memory_rebuild_acceptance/v3.1",
        "final": final,
        "binding": {
            "database_semantic_fingerprint": "candidate-fingerprint",
            "source_union_sha256": "source-union",
            "restore_run_id": "restore-run",
            "protocol_run_id": "protocol-run",
        },
    }
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    accepted = test_profiles_module._load_acceptance_report(
        report_path,
        expected_database_fingerprint="candidate-fingerprint",
        expected_source_union_sha256="source-union",
        expected_restore_run_id="restore-run",
        expected_protocol_run_id="protocol-run",
    )
    assert accepted["ok"] is True
    assert accepted["binding_ok"] is True

    payload["binding"]["source_union_sha256"] = "different-union"
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    rejected = test_profiles_module._load_acceptance_report(
        report_path,
        expected_database_fingerprint="candidate-fingerprint",
        expected_source_union_sha256="source-union",
        expected_restore_run_id="restore-run",
        expected_protocol_run_id="protocol-run",
    )
    assert rejected["ok"] is False
    assert rejected["binding_ok"] is False
    assert rejected["binding_checks"]["source_union_sha256"]["passed"] is False



def test_runtime_probe_import_does_not_cycle_through_memory_rebuild_package() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            (
                "import latka_jazn.memory.unified_memory_runtime; "
                "import latka_jazn.tools.memory_rebuild_app; "
                "from latka_jazn.tools.memory_rebuild_app import ProtocolEngine"
            ),
        ],
        cwd=Path.cwd(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert completed.returncode == 0, completed.stderr
    assert "partially initialized module" not in completed.stderr



def test_baseline_reconciliation_ignores_target_only_schema_columns(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline-schema.sqlite3"
    target = tmp_path / "target-schema.sqlite3"
    with sqlite3.connect(baseline) as con:
        con.execute(
            "CREATE TABLE conversations("
            "conversation_id TEXT PRIMARY KEY,"
            "title TEXT NOT NULL"
            ")"
        )
        con.execute(
            "INSERT INTO conversations(conversation_id,title) VALUES(?,?)",
            ("conv-schema", "same"),
        )
        con.commit()
    with sqlite3.connect(target) as con:
        con.execute(
            "CREATE TABLE conversations("
            "conversation_id TEXT PRIMARY KEY,"
            "title TEXT NOT NULL,"
            "new_target_only_column TEXT"
            ")"
        )
        con.execute(
            "INSERT INTO conversations("
            "conversation_id,title,new_target_only_column"
            ") VALUES(?,?,?)",
            ("conv-schema", "same", "derived"),
        )
        con.commit()

    report = baseline_record_reconciliation(target, [baseline])
    assert report["ok"] is True
    assert report["tables"]["conversations"]["missing_record_count"] == 0
    assert report["tables"]["conversations"]["content_mismatch_count"] == 0



def test_prepublish_system_gate_rechecks_runtime_after_long_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_conversations(tmp_path / "conversations.json", "conv-race", "race")
    project = _project(tmp_path, source, name="Prepublish gate")
    project.mode = "system"
    pipeline = CanonicalMemoryRebuildPipeline(project, tool_root=Path.cwd())

    monkeypatch.setattr(
        memory_restore_types_module,
        "target_preflight",
        lambda settings, tool_root=None: {
            "ok": False,
            "mode": "system",
            "target_root": settings.target_root,
            "blocking_errors": ["system_runtime_must_be_stopped"],
            "warnings": [],
            "evidence": {"daemon": {"pid_alive": True}},
        },
    )

    report = pipeline.prepublish_runtime_gate()
    assert report["ok"] is False
    assert "system_runtime_must_be_stopped" in report["blocking_errors"]



def test_prepared_plan_is_stale_when_existing_sqlite_wal_changes(
    tmp_path: Path,
) -> None:
    source = _write_conversations(
        tmp_path / "conversations-wal.json",
        "conv-wal",
        "wal",
    )
    project = _project(tmp_path, source, name="WAL plan binding")
    target = Path(project.target_root)
    legacy = MemoryRebuildCoordinator(target)
    initialized = legacy.init()
    assert initialized["ok"]

    pipeline = CanonicalMemoryRebuildPipeline(project, tool_root=Path.cwd())
    prepared = pipeline.plan()
    assert prepared["ok"], prepared
    assert prepared["execution_plan_sha256"]

    wal = Path(str(legacy.paths.memory_jazn) + "-wal")
    wal.write_bytes(b"synthetic-wal-state-change")

    result = pipeline.run(prepared_plan=prepared)
    assert result["ok"] is False
    assert result["status"] == "prepared_plan_stale"
    assert result["field"] == "execution_plan_sha256"
    assert result["actual"] != prepared["execution_plan_sha256"]



def test_prepared_plan_is_stale_when_existing_sqlite_rollback_journal_changes(
    tmp_path: Path,
) -> None:
    source = _write_conversations(
        tmp_path / "conversations-journal.json",
        "conv-journal",
        "journal-sidecar",
    )
    project = _project(tmp_path, source, name="Rollback journal plan binding")
    target = Path(project.target_root)
    legacy = MemoryRebuildCoordinator(target)
    initialized = legacy.init()
    assert initialized["ok"]

    pipeline = CanonicalMemoryRebuildPipeline(project, tool_root=Path.cwd())
    prepared = pipeline.plan()
    assert prepared["ok"], prepared
    assert prepared["execution_plan_sha256"]

    rollback_journal = Path(str(legacy.paths.memory_jazn) + "-journal")
    rollback_journal.write_bytes(b"synthetic-hot-journal-state-change")

    result = pipeline.run(prepared_plan=prepared)
    assert result["ok"] is False
    assert result["status"] == "prepared_plan_stale"
    assert result["field"] == "execution_plan_sha256"
    assert result["actual"] != prepared["execution_plan_sha256"]


def test_publish_rollback_tracks_sqlite_rollback_journal_sidecar(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    sidecars = CanonicalMemoryRebuildPipeline._sidecars(database)
    assert Path(str(database) + "-journal") in sidecars
    assert Path(str(database) + "-wal") in sidecars
    assert Path(str(database) + "-shm") in sidecars
