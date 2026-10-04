from __future__ import annotations

from pathlib import Path
import json

from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.chat_export_reader import sha256_file
from latka_jazn.tools.memory_rebuild_app.canonical_rebuild import (
    CanonicalMemoryRebuildPipeline,
    canonical_database_path,
)
from latka_jazn.tools.memory_rebuild_app.controller import MemoryRebuildAppController
from latka_jazn.tools.memory_rebuild_app.models import RebuildProject, SourceSpec
from latka_jazn.tools.memory_rebuild_app.project_store import ProjectStore
from latka_jazn.tools.memory_rebuild_app.test_spec import validate_test_layer_contracts
from latka_jazn.tools.memory_rebuild_coordinator import MemoryRebuildCoordinator
from latka_jazn.tools.memory_restore import confirmation_token


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
    assert result["memory_search_ready"] is True
    assert result["full_autobiographical_recall_ready"] is True
    assert expected_database.is_file()

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
    contracts = {item["profile"]: item for item in report["contracts"]}
    assert contracts["test00"]["owner_layer"] == "source_fidelity_and_union"
    assert contracts["test01"]["required_predecessors"] == ("test00",)
    assert contracts["test02"]["required_predecessors"] == ("test01",)
    assert contracts["test03"]["required_predecessors"] == ("test02",)
    assert contracts["test04"]["required_predecessors"] == ("test03",)
    assert contracts["final"]["required_predecessors"] == ("test04",)
    assert contracts["final"]["gate_kind"] == "export_and_readiness"
