from __future__ import annotations

from pathlib import Path
import json
import sqlite3

import pytest

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

    test02 = engine.run_test02(database)
    assert test02["ok"] is True, test02
    assert test02["details"]["projection"]["raw_l0_unchanged"] is True

    test03 = engine.run_test03([first, second], test00_result=test00)
    assert test03["ok"] is True, test03
    assert test03["details"]["semantic_reconciliation"] is True

    manifests = engine.seal_manifest()
    private = json.loads(Path(manifests["private"]).read_text(encoding="utf-8"))
    sanitized = json.loads(Path(manifests["sanitized"]).read_text(encoding="utf-8"))
    assert private["results"]["test00"]["outcome"] == "PASSED"
    assert private["results"]["test03"]["outcome"] == "PASSED"
    assert sanitized["source_bundle_inventory"][0].get("path") is None
    with pytest.raises(FileExistsError):
        engine._manifest.complete().write_once(engine.run_root)


def test_test03_fails_closed_for_changed_same_node_payload(tmp_path: Path) -> None:
    first = _write_source(tmp_path / "conversations.json", "conversation-a", "payload one")
    second = _write_source(tmp_path / "conversations-1.json", "conversation-a", "payload two")
    engine = _engine(tmp_path, "conflict")

    result = engine.run_test03([first, second])

    assert result["ok"] is False
    assert result["outcome"] == "BLOCKED"
    assert "same_node_payload_or_parent_conflict" in result["blockers"]


def test_application_service_dispatches_the_same_protocol_engine(tmp_path: Path) -> None:
    source = _write_source(tmp_path / "conversations.json", "conversation-a", "Tayfa")
    service = MemoryRebuildApplicationService(
        tmp_path / "service",
        tool_root=Path.cwd(),
        base_commit=BASE_COMMIT,
        run_id="service-run",
    )

    result = service.run_protocol("test00", sources=[source])

    assert isinstance(service.engine, ProtocolEngine)
    assert result["ok"] is True
    assert Path(result["run_manifest"]["private"]).is_file()


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
    assert engine.run_test01([source], database=database, test00_result=test00)["ok"] is True
    assert engine.run_test02(database)["ok"] is True

    test04 = engine.run_test04(database, _benchmark(tmp_path / "benchmark.private.json"))
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
    assert cli_main(
        [
            "protocol-run",
            "--profile", "test00",
            "--output-root", str(tmp_path / "cli"),
            "--source", str(source),
            "--base-commit", BASE_COMMIT,
            "--run-id", "cli-run",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert Path(payload["run_manifest"]["sanitized"]).is_file()


def test_studio_runner_constructs_the_same_application_service(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class FakeService:
        def __init__(self, output_root, **kwargs):
            calls.append((Path(output_root), kwargs))

        def run_protocol(self, profile, **kwargs):
            calls.append((profile, kwargs))
            return {"ok": True, "outcome": "PASSED", "profile": profile}

    state = studio.StudioState(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=None,
        project=None,
        tool_root=Path.cwd(),
        settings_path=tmp_path / "settings.json",
    )
    dialogs = type("Dialogs", (), {"message": lambda self, *_args: None})()
    monkeypatch.setattr(studio, "MemoryRebuildApplicationService", FakeService)

    studio._run_test(state, dialogs, "test02")

    assert calls[-1][0] == "test02"
    assert calls[-1][1]["database"] == state.database


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
