from __future__ import annotations

"""Synthetic, privacy-free regression tests for Memory Studio operator steps."""

from pathlib import Path
import json
import zipfile

import pytest

from latka_jazn.tools.memory_rebuild_app.application import MemoryRebuildApplicationService
from latka_jazn.tools.memory_rebuild_app.file_checks import check_memory_source_files
from latka_jazn.tools.memory_rebuild_app.report_sanitizer import sanitize_report
from latka_jazn.tools.memory_rebuild_app.source_bundle import (
    SourceRole, classify_source_role,
)
from latka_jazn.tools.memory_rebuild_app.steps import (
    STEP_ORDER, STEP_SPECS, legacy_profile_for_step, step_for_legacy_profile,
)
from latka_jazn.tools.memory_rebuild_app.studio import StudioState


def test_operator_step_names_preserve_legacy_lineage() -> None:
    assert STEP_ORDER == ("step00", "step01", "step02", "step03", "step04", "final")
    assert [item.legacy_profile for item in STEP_SPECS] == [
        "test00", "test01", "test02", "test03", "test04", "final"
    ]
    assert legacy_profile_for_step("step03") == "test03"
    assert legacy_profile_for_step("test03") == "test03"
    assert step_for_legacy_profile("final").step_id == "final"
    with pytest.raises(ValueError):
        legacy_profile_for_step("../unsafe")


def test_service_run_step_is_a_compatibility_facade() -> None:
    service = object.__new__(MemoryRebuildApplicationService)
    captured: list[str] = []
    def stub_run(profile: str, **kwargs: object) -> dict:
        captured.append(profile)
        return {"ok": True, "outcome": "PASSED", "checked": kwargs}
    service.run_protocol = stub_run  # type: ignore[method-assign]
    result = service.run_step("step02", database="example.sqlite3")
    assert captured == ["test02"]
    assert result["step_id"] == "step02"
    assert result["kind"] == "rebuild_step"


def test_dated_chatgpt_export_files_are_recognized() -> None:
    assert classify_source_role("conversations-2025.06.16.json") is SourceRole.CANONICAL_CHAT_GRAPH
    assert classify_source_role("conversations-2026.07.17-008.json") is SourceRole.CANONICAL_CHAT_GRAPH
    assert classify_source_role("chat-2025.06.16.html") is SourceRole.LOSSLESS_CONTROL_GRAPH
    assert classify_source_role("shared_conversations-2025.06.16.json") is SourceRole.UNKNOWN_SIDECAR
    assert classify_source_role("conversations.json") is SourceRole.CANONICAL_CHAT_GRAPH


def test_file_check_reads_every_jsonl_line_and_keeps_sources_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "diary.jsonl"
    source.write_text('{"id":1}\n{"id":2}\n', encoding="utf-8")
    before = source.read_bytes()
    report = check_memory_source_files([source], report_dir=tmp_path / "reports")
    assert report["ok"] is True
    assert report["file_count"] == 1
    assert report["files"][0]["format_check"]["record_count"] == 2
    assert source.read_bytes() == before
    sanitized = json.loads((tmp_path / "reports" / "file-checks.sanitized.json").read_text(encoding="utf-8"))
    assert str(tmp_path) not in json.dumps(sanitized)


def test_jsonl_failure_on_late_line_is_not_lost_to_sampled_sniff(tmp_path: Path) -> None:
    source = tmp_path / "runtime_events.jsonl"
    source.write_text('{"id":1}\n' * 30 + '{"secret":"incomplete"\n', encoding="utf-8")
    report = check_memory_source_files([source])
    assert report["ok"] is False
    assert report["status"] == "FAILED"
    assert "format_validation_ValueError" in report["files"][0]["blocking_codes"]


def test_odt_is_checked_as_package_not_imported_into_memory(tmp_path: Path) -> None:
    path = tmp_path / "important-moments.odt"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", "<office/>")
    report = check_memory_source_files([path])
    assert report["ok"] is True
    assert report["status"] == "REVIEW"
    assert report["files"][0]["format_check"]["ok"] is True
    assert report["files"][0]["pipeline"] == "catalog_only"


def test_sanitization_redacts_arbitrary_private_text_and_keys(tmp_path: Path) -> None:
    report = {
        "status": "PASSED",
        "details": "very private quote from a conversation",
        "source": str(tmp_path / "PRIVATE" / "chat.json"),
        "nested": {"person@example.org": "private value"},
    }
    safe = sanitize_report(report)
    flat = json.dumps(safe, ensure_ascii=False)
    assert "private quote" not in flat
    assert "person@example.org" not in flat
    assert "private value" not in flat
    assert str(tmp_path) not in flat
    assert safe["status"] == "PASSED"
    assert safe["source"]["private_locator_removed"] is True


def test_invalid_resume_run_id_is_rejected_before_filesystem_access() -> None:
    state = object.__new__(StudioState)
    with pytest.raises(ValueError):
        state.resume_step_run("../../external")
