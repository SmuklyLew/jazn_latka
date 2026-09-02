from __future__ import annotations

from pathlib import Path
import json
import sqlite3

import pytest

from latka_jazn.tools.memory_rebuild_app import build_source_union_manifest
from latka_jazn.tools.memory_rebuild_app import studio
from latka_jazn.tools.memory_rebuild_app.application import MemoryRebuildApplicationService
from latka_jazn.tools.memory_rebuild_app.cli import build_parser, main as cli_main
from latka_jazn.tools.memory_rebuild_app.protocol_engine import ProtocolEngine


BASE_COMMIT = "b" * 40


def _message(message_id: str, role: str, text: str, timestamp: float) -> dict:
    return {
        "id": message_id,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {},
        "recipient": "all",
        "channel": None,
    }


def _conversation(conversation_id: str, text: str) -> dict:
    return {
        "id": conversation_id,
        "title": "Synthetic protocol fixture",
        "create_time": 100.0,
        "update_time": 104.0,
        "current_node": "assistant",
        "mapping": {
            "root": {"id": "root", "parent": None, "children": ["user"], "message": None},
            "user": {
                "id": "user",
                "parent": "root",
                "children": ["tool", "assistant"],
                "message": _message("message-user", "user", text, 101.0),
            },
            "tool": {
                "id": "tool",
                "parent": "user",
                "children": [],
                "message": _message("message-tool", "tool", "technical payload", 102.0),
            },
            "assistant": {
                "id": "assistant",
                "parent": "user",
                "children": [],
                "message": _message("message-assistant", "assistant", "Tayfa remains remembered", 103.0),
            },
        },
    }


def _write_source(path: Path, conversation_id: str, text: str) -> Path:
    path.write_text(json.dumps([_conversation(conversation_id, text)], ensure_ascii=False), encoding="utf-8")
    return path


def _engine(tmp_path: Path, run_id: str) -> ProtocolEngine:
    return ProtocolEngine(
        tmp_path / "protocols",
        system_version="16.5.0-test",
        base_commit=BASE_COMMIT,
        run_id=run_id,
    )


def _build_test01_database(tmp_path: Path) -> tuple[Path, Path, dict, dict]:
    source = _write_source(
        tmp_path / "dependency-conversations.json",
        "dependency-conversation",
        "Tayfa dependency graph fixture",
    )
    builder = _engine(tmp_path, "dependency-setup")
    test00 = builder.run_test00([source])
    database = tmp_path / "dependency-memory.sqlite3"
    test01 = builder.run_test01([source], database=database, test00_result=test00)
    assert test01["ok"] is True, test01
    return source, database, test00, test01


def test_protocol_engine_runs_real_test00_test01_test02_and_test03(tmp_path: Path) -> None:
    first = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa is important")
    second = _write_source(tmp_path / "conversations-1.json", "conversation-b", "Tayfa likes the window")
    engine = _engine(tmp_path, "pipeline")

    test00 = engine.run_test00([first, second])
    assert test00["ok"] is True, test00
    assert test00["outcome"] == "PASSED"
    assert test00["details"]["source_union"]["unique_conversation_count"] == 2

    database = tmp_path / "test01" / "memory_jazn.sqlite3"
    test01 = engine.run_test01([first, second], database=database, test00_result=test00)
    assert test01["ok"] is True, test01
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT COUNT(*) FROM memory_l0_records WHERE role='tool'").fetchone()[0] == 2
        assert con.execute(
            "SELECT COUNT(*) FROM memory_l0_records WHERE role='tool' AND memory_eligible<>0"
        ).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0] == 0

    test02 = engine.run_test02(database, test01_result=test01)
    assert test02["ok"] is True, test02
    assert test02["details"]["projection"]["raw_l0_unchanged"] is True

    test03 = engine.run_test03([first, second], test02_result=test02)
    assert test03["ok"] is True, test03
    assert test03["details"]["semantic_reconciliation"] is True

    checkpoint = engine.checkpoint_manifest()
    private = json.loads(Path(checkpoint["draft_private"]).read_text(encoding="utf-8"))
    sanitized = json.loads(Path(checkpoint["draft_sanitized"]).read_text(encoding="utf-8"))
    assert private["results"]["test00"]["outcome"] == "PASSED"
    assert private["results"]["test03"]["outcome"] == "PASSED"
    assert private["completed_at"] is None
    assert sanitized["source_bundle_inventory"][0].get("path") is None
    with pytest.raises(RuntimeError, match="Final"):
        engine.seal_manifest()


def test_dependency_graph_blocks_test01_without_test00(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa")
    engine = _engine(tmp_path, "missing-test00")

    result = engine.run_test01([source], database=tmp_path / "blocked-test01.sqlite3")

    assert result["outcome"] == "BLOCKED"
    assert "prerequisite_artifact_present" in result["blockers"]


def test_dependency_graph_blocks_test02_without_test01(tmp_path: Path) -> None:
    _source, database, _test00, _test01 = _build_test01_database(tmp_path)
    engine = _engine(tmp_path, "missing-test01")

    result = engine.run_test02(database)

    assert result["outcome"] == "BLOCKED"
    assert "prerequisite_artifact_present" in result["blockers"]


def test_dependency_graph_blocks_test03_without_test02(tmp_path: Path) -> None:
    source, _database, _test00, _test01 = _build_test01_database(tmp_path)
    engine = _engine(tmp_path, "missing-test02")

    result = engine.run_test03([source])

    assert result["outcome"] == "BLOCKED"
    assert "prerequisite_artifact_present" in result["blockers"]


def test_dependency_graph_blocks_test04_without_test03(tmp_path: Path) -> None:
    _source, database, _test00, _test01 = _build_test01_database(tmp_path)
    engine = _engine(tmp_path, "missing-test03")

    result = engine.run_test04(database, _benchmark(tmp_path / "benchmark.private.json"))

    assert result["outcome"] == "BLOCKED"
    assert "prerequisite_artifact_present" in result["blockers"]


def test_dependency_graph_blocks_final_without_authentic_test04(tmp_path: Path) -> None:
    _source, database, _test00, _test01 = _build_test01_database(tmp_path)
    engine = _engine(tmp_path, "missing-test04")
    forged_test04 = {
        "schema_version": "jazn_memory_rebuild_protocol_engine/v4",
        "profile": "test04",
        "outcome": "PASSED",
        "ok": True,
        "run_id": engine.run_id,
    }

    result = engine.run_final(
        database,
        tmp_path / "forged-final",
        test04_result=forged_test04,
    )

    assert result["outcome"] == "BLOCKED"
    assert "prerequisite_dependency_chain" in result["blockers"]


def test_dependency_graph_blocks_cross_run_test00_artifact(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa")
    producer = _engine(tmp_path, "producer-run")
    test00 = producer.run_test00([source])
    consumer = _engine(tmp_path, "consumer-run")

    result = consumer.run_test01(
        [source],
        database=tmp_path / "cross-run.sqlite3",
        test00_result=test00,
    )

    assert result["outcome"] == "BLOCKED"
    assert "prerequisite_run_id" in result["blockers"]


def test_dependency_graph_blocks_source_changed_after_test00(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa")
    engine = _engine(tmp_path, "stale-source")
    test00 = engine.run_test00([source])
    _write_source(source, "conversation-a", "Tayfa changed after Test00")

    result = engine.run_test01(
        [source],
        database=tmp_path / "stale-source.sqlite3",
        test00_result=test00,
    )

    assert result["outcome"] == "BLOCKED"
    assert "prerequisite_source_inventory_fingerprint" in result["blockers"]


def test_dependency_graph_blocks_database_changed_after_test01(tmp_path: Path) -> None:
    _source, database, _test00, _test01 = _build_test01_database(tmp_path)
    engine = _engine(tmp_path, "dependency-setup")
    engine.results["test01"] = dict(_test01)
    with sqlite3.connect(database) as con:
        con.execute(
            "UPDATE memory_l0_records "
            "SET content = content || ' changed after Test01' "
            "WHERE rowid = (SELECT MIN(rowid) FROM memory_l0_records)"
        )

    result = engine.run_test02(database)

    assert result["outcome"] == "BLOCKED"
    assert "prerequisite_database_fingerprint" in result["blockers"]


def test_source_union_fails_closed_for_changed_same_node_payload(tmp_path: Path) -> None:
    first = _write_source(tmp_path / "conversations.json", "conversation-a", "payload one")
    second = _write_source(tmp_path / "conversations-1.json", "conversation-a", "payload two")

    result = build_source_union_manifest([first, second])

    assert result["ok"] is True
    assert result["projection_conflict_conversation_count"] == 1
    assert result["requires_projection_resolution"] is True


def test_application_service_keeps_one_manifest_open_across_stages(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa")
    service = MemoryRebuildApplicationService(
        tmp_path / "service",
        tool_root=Path.cwd(),
        base_commit=BASE_COMMIT,
        run_id="service-run",
    )

    test00 = service.run_protocol("test00", sources=[source])

    assert isinstance(service.engine, ProtocolEngine)
    assert test00["ok"] is True
    assert test00["run_manifest"]["sealed"] is False
    assert test00["run_manifest"]["completed_profiles"] == ["test00"]
    assert test00["run_manifest"]["private"] is None
    assert test00["run_manifest"]["sanitized"] is None
    assert Path(test00["run_manifest"]["draft_private"]).is_file()
    assert Path(test00["run_manifest"]["draft_sanitized"]).is_file()
    assert service.engine._manifest.completed_at is None

    test01 = service.run_protocol(
        "test01",
        sources=[source],
        database=tmp_path / "service-memory.sqlite3",
        test00_result=test00,
    )

    assert test01["ok"] is True
    assert test01["run_manifest"]["sealed"] is False
    assert test01["run_manifest"]["completed_profiles"] == ["test00", "test01"]
    assert service.engine._manifest.completed_at is None


def test_application_service_resumes_interrupted_draft_after_test02(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa")
    output_root = tmp_path / "resume-service"
    database = tmp_path / "resume-memory.sqlite3"
    first = MemoryRebuildApplicationService(
        output_root,
        tool_root=Path.cwd(),
        base_commit=BASE_COMMIT,
        run_id="resumable-run",
    )
    test00 = first.run_protocol("test00", sources=[source])
    test01 = first.run_protocol(
        "test01",
        sources=[source],
        database=database,
        test00_result=test00,
    )
    test02 = first.run_protocol("test02", database=database, test01_result=test01)
    assert test02["run_manifest"]["completed_profiles"] == ["test00", "test01", "test02"]

    with pytest.raises(FileExistsError, match="explicit resume"):
        MemoryRebuildApplicationService(
            output_root,
            tool_root=Path.cwd(),
            base_commit=BASE_COMMIT,
            run_id="resumable-run",
        )

    resumed = MemoryRebuildApplicationService(
        output_root,
        tool_root=Path.cwd(),
        base_commit=BASE_COMMIT,
        run_id="resumable-run",
        resume=True,
    )

    assert resumed.engine.run_id == first.engine.run_id
    assert list(resumed.engine.results) == ["test00", "test01", "test02"]
    test03 = resumed.run_protocol("test03", sources=[source])
    assert test03["ok"] is True, test03
    assert test03["run_manifest"]["completed_profiles"] == [
        "test00",
        "test01",
        "test02",
        "test03",
    ]
    test04 = resumed.run_protocol(
        "test04",
        database=database,
        benchmark=_benchmark(tmp_path / "resume-benchmark.private.json"),
        test03_result=test03,
    )
    final = resumed.run_protocol(
        "final",
        database=database,
        output=tmp_path / "resumed-final-memory",
        test04_result=test04,
        sources=[source],
    )
    assert final["ok"] is True, final
    assert final["run_manifest"]["sealed"] is True
    assert final["run_manifest"]["completed_profiles"] == [
        "test00",
        "test01",
        "test02",
        "test03",
        "test04",
        "final",
    ]
    assert Path(final["run_manifest"]["private"]).is_file()
    assert Path(final["run_manifest"]["sanitized"]).is_file()
    assert final["run_manifest"]["draft_private"] is None
    assert final["run_manifest"]["draft_sanitized"] is None
    assert not Path(test02["run_manifest"]["draft_private"]).exists()
    assert not Path(test02["run_manifest"]["draft_sanitized"]).exists()
    sanitized_text = Path(final["run_manifest"]["sanitized"]).read_text(encoding="utf-8")
    assert str(source) not in sanitized_text
    assert "conversation-a" not in sanitized_text
    assert "Tayfa" not in sanitized_text
    with pytest.raises(RuntimeError, match="sealed"):
        MemoryRebuildApplicationService(
            output_root,
            tool_root=Path.cwd(),
            base_commit=BASE_COMMIT,
            run_id="resumable-run",
            resume=True,
        )


def test_application_service_resume_rejects_invalid_draft_recovery_contract(
    tmp_path: Path,
) -> None:
    source = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa")
    output_root = tmp_path / "invalid-resume-service"
    service = MemoryRebuildApplicationService(
        output_root,
        tool_root=Path.cwd(),
        base_commit=BASE_COMMIT,
        run_id="invalid-resume-run",
    )
    test00 = service.run_protocol("test00", sources=[source])
    draft_private = Path(test00["run_manifest"]["draft_private"])
    draft_sanitized = Path(test00["run_manifest"]["draft_sanitized"])

    with pytest.raises(ValueError, match="base_commit"):
        MemoryRebuildApplicationService(
            output_root,
            tool_root=Path.cwd(),
            base_commit="c" * 40,
            run_id="invalid-resume-run",
            resume=True,
        )

    draft_sanitized.unlink()
    with pytest.raises(FileNotFoundError, match="complete RunManifest draft pair"):
        MemoryRebuildApplicationService(
            output_root,
            tool_root=Path.cwd(),
            base_commit=BASE_COMMIT,
            run_id="invalid-resume-run",
            resume=True,
        )

    service.engine.checkpoint_manifest()
    tampered = json.loads(draft_sanitized.read_text(encoding="utf-8"))
    tampered["run_id"] = "tampered-run"
    draft_sanitized.write_text(json.dumps(tampered), encoding="utf-8")
    assert draft_private.is_file()
    with pytest.raises(ValueError, match="private/sanitized pair mismatch"):
        MemoryRebuildApplicationService(
            output_root,
            tool_root=Path.cwd(),
            base_commit=BASE_COMMIT,
            run_id="invalid-resume-run",
            resume=True,
        )


def _benchmark(path: Path) -> Path:
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
    cases = []
    for category in categories:
        case = {
            "id": f"case-{category}",
            "query": "Tayfa",
            "category": category,
            "expected_any": ["Tayfa"],
            "limit": 20,
        }
        if category == "referential_followup":
            case["context_turns"] = ["Tayfa"]
        if category == "temporal":
            case["temporal_start"] = "1970-01-01T00:00:00+00:00"
            case["temporal_end"] = "2100-01-01T00:00:00+00:00"
        if category == "provenance":
            case["expected_source_kinds"] = ["chatgpt_conversation"]
        if category == "sensitive_boundary":
            case["forbidden_any"] = ["technical payload"]
        cases.append(case)
    cases.append(
        {
            "id": "case-negative",
            "query": "term-that-cannot-possibly-exist-77f3",
            "category": "negative",
            "expected_abstain": True,
            "minimum_hits": 0,
        }
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": "jazn_memory_recall_benchmark/v2",
                "suite_id": "synthetic-v4-protocol",
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


def test_test04_runs_recall_categories_and_final_uses_sqlite_backup_api(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa is important")
    engine = _engine(tmp_path, "acceptance")
    test00 = engine.run_test00([source])
    database = tmp_path / "acceptance.sqlite3"
    test01 = engine.run_test01([source], database=database, test00_result=test00)
    assert test01["ok"] is True
    test02 = engine.run_test02(database, test01_result=test01)
    assert test02["ok"] is True
    test03 = engine.run_test03([source], test02_result=test02)
    assert test03["ok"] is True

    test04 = engine.run_test04(
        database,
        _benchmark(tmp_path / "benchmark.private.json"),
        test03_result=test03,
    )
    assert test04["ok"] is True, test04
    assert test04["details"]["validation"]["developer_acceptance"] is True

    output = tmp_path / "final-memory"
    final = engine.run_final(database, output, test04_result=test04, sources=[source])
    assert final["ok"] is True, final
    assert (output / "memory_jazn.sqlite3").is_file()
    assert (output / "final.private.json").is_file()
    assert (output / "final.sanitized.json").is_file()
    assert final["details"]["validation"]["integrity"] == ["ok"]
    assert final["details"]["validation"]["foreign_key_error_count"] == 0
    assert final["details"]["validation"]["fts"]["ok"] is True
    manifests = engine.seal_manifest()
    assert Path(manifests["private"]).is_file()
    assert Path(manifests["sanitized"]).is_file()
    with pytest.raises(RuntimeError, match="sealed"):
        engine.seal_manifest()
    with pytest.raises(RuntimeError, match="sealed"):
        engine.run_test00([source])


def test_cli_protocol_run_and_validate_use_application_service(tmp_path: Path, capsys) -> None:
    source = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa")
    parser = build_parser()
    parsed = parser.parse_args(
        [
            "protocol-run",
            "--profile", "test00",
            "--output-root", str(tmp_path / "cli"),
            "--source", str(source),
            "--base-commit", BASE_COMMIT,
            "--run-id", "cli-run",
        ]
    )
    assert parsed.command == "protocol-run"

    output_root = tmp_path / "cli"
    database = tmp_path / "cli-memory.sqlite3"
    common = [
        "--output-root", str(output_root),
        "--base-commit", BASE_COMMIT,
        "--run-id", "cli-run",
    ]

    def run_cli(profile: str, *extra: str, resume: bool = False) -> dict:
        arguments = ["protocol-run", "--profile", profile, *common]
        if resume:
            arguments.append("--resume")
        arguments.extend(extra)
        assert cli_main(arguments) == 0
        return json.loads(capsys.readouterr().out)

    test00 = run_cli("test00", "--source", str(source))
    assert test00["ok"] is True
    assert test00["run_manifest"]["sealed"] is False
    assert test00["run_manifest"]["sanitized"] is None
    assert Path(test00["run_manifest"]["draft_sanitized"]).is_file()

    test01 = run_cli(
        "test01",
        "--source", str(source),
        "--database", str(database),
        resume=True,
    )
    assert test01["ok"] is True, test01
    assert test01["run_id"] == test00["run_id"]
    assert test01["run_manifest"]["completed_profiles"] == ["test00", "test01"]

    test02 = run_cli("test02", "--database", str(database), resume=True)
    assert test02["ok"] is True, test02
    assert test02["run_manifest"]["completed_profiles"] == ["test00", "test01", "test02"]

    test03 = run_cli("test03", "--source", str(source), resume=True)
    assert test03["ok"] is True, test03
    assert test03["run_manifest"]["completed_profiles"] == [
        "test00", "test01", "test02", "test03",
    ]

    test04 = run_cli(
        "test04",
        "--database", str(database),
        "--benchmark", str(_benchmark(tmp_path / "cli-benchmark.private.json")),
        resume=True,
    )
    assert test04["ok"] is True, test04
    assert test04["run_manifest"]["completed_profiles"] == [
        "test00", "test01", "test02", "test03", "test04",
    ]

    final = run_cli(
        "final",
        "--database", str(database),
        "--final-output", str(tmp_path / "cli-final-memory"),
        "--source", str(source),
        resume=True,
    )
    assert final["ok"] is True, final
    assert final["run_id"] == test00["run_id"]
    assert final["run_manifest"]["sealed"] is True
    assert final["run_manifest"]["completed_profiles"] == [
        "test00", "test01", "test02", "test03", "test04", "final",
    ]

    resume_parsed = parser.parse_args(
        [
            "protocol-run",
            "--profile", "test03",
            "--output-root", str(output_root),
            "--base-commit", BASE_COMMIT,
            "--run-id", "cli-run",
            "--resume",
        ]
    )
    assert resume_parsed.resume is True


def test_studio_runner_reuses_one_application_service_and_authentic_chain(
    monkeypatch,
    tmp_path: Path,
) -> None:
    constructors = []
    calls: list[tuple[str, dict]] = []

    class FakeService:
        def __init__(self, output_root, **kwargs):
            constructors.append((self, Path(output_root), kwargs))

        def run_protocol(self, profile, **kwargs):
            calls.append((profile, kwargs))
            return {
                "ok": True,
                "outcome": "PASSED",
                "profile": profile,
                "run_id": "studio-one-run",
                "downstream_ready": True,
            }

    state = studio.StudioState(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=None,
        project=None,
        tool_root=Path.cwd(),
        settings_path=tmp_path / "settings.json",
    )
    dialogs = type("Dialogs", (), {"message": lambda self, *_args: None})()
    monkeypatch.setattr(studio, "MemoryRebuildApplicationService", FakeService)
    source = _write_source(tmp_path / "studio-conversations.json", "conversation-a", "Tayfa")
    monkeypatch.setattr(studio, "_project_sources", lambda _state: [source])

    studio._run_test(state, dialogs, "test00")
    studio._run_test(state, dialogs, "test01")
    studio._run_test(state, dialogs, "test02")
    studio._run_test(state, dialogs, "test03")

    assert len(constructors) == 1
    assert state.protocol_service is constructors[0][0]
    assert [profile for profile, _kwargs in calls] == ["test00", "test01", "test02", "test03"]
    assert calls[1][1]["test00_result"] == state.test_results["test00"]
    assert calls[2][1]["test01_result"] == state.test_results["test01"]
    assert calls[3][1]["test02_result"] == state.test_results["test02"]


def test_test00_accepts_classified_bundle_attachments_as_opaque_raw_evidence(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    _write_source(bundle / "conversations.json", "conversation-a", "Tayfa")
    (bundle / "message_feedback.json").write_text("[]", encoding="utf-8")
    (bundle / "user.json").write_text('{"id":"private-account"}', encoding="utf-8")
    assets = bundle / "assets"
    assets.mkdir()
    attachment = assets / "opaque.bin"
    attachment.write_bytes(b"\x00\x01opaque attachment bytes")
    engine = _engine(tmp_path, "bundle-run")

    result = engine.run_test00([bundle])

    assert result["ok"] is True, result
    fidelity = result["details"]["fidelity"]
    by_name = {Path(item["source_path"]).name: item for item in fidelity["results"]}
    assert by_name["opaque.bin"]["parse_mode"] == "opaque_source_evidence"
    assert by_name["opaque.bin"]["source_sha256"] == by_name["opaque.bin"]["raw_roundtrip_sha256"]
    roles = {item["relative_path"]: item["role"] for item in result["artifacts"]["inventory"]}
    assert roles["assets/opaque.bin"] == "source_attachment"


def test_mixed_lossless_and_rendered_html_is_lossy_but_safe_for_canonical_test01(tmp_path: Path) -> None:
    canonical = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa")
    rendered = tmp_path / "chat.html"
    rendered.write_text(
        '<div class="conversation"><h4>Rendered</h4><pre class="message">Niekanoniczne</pre></div>',
        encoding="utf-8",
    )
    engine = _engine(tmp_path, "mixed-html")

    test00 = engine.run_test00([canonical, rendered])

    assert test00["outcome"] == "LOSSY"
    assert test00["ok"] is False
    assert test00["downstream_ready"] is True
    union = test00["details"]["source_union"]
    assert (union["lossless_chat_source_count"], union["lossy_chat_source_count"]) == (1, 1)
    roles = {item["relative_path"]: item["role"] for item in test00["artifacts"]["inventory"]}
    assert roles["chat.html"] == "lossy_rendered_control"

    database = tmp_path / "mixed-html.sqlite3"
    test01 = engine.run_test01([canonical, rendered], database=database, test00_result=test00)

    assert test01["ok"] is True, test01
    assert test01["details"]["excluded_lossy_source_count"] == 1
    with sqlite3.connect(database) as con:
        assert (
            con.execute(
                "SELECT COUNT(DISTINCT conversation_id) FROM memory_l0_records"
            ).fetchone()[0]
            == 1
        )
