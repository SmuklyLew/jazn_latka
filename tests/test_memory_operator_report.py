"""The canonical operator route observes P1 without creating project state."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from latka_jazn.tools.memory_rebuild_app.models import RebuildProject
from latka_jazn.tools.memory_rebuild_app.p1_operator_report import build_operator_report
from tests.test_memory_provenance_native_p1 import native_pair


def test_layout_does_not_create_project_store_or_expose_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(tmp_path / "host"))
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    project = RebuildProject.create("synthetic", tmp_path / "target")
    selected = tmp_path / "project.memory-rebuild.json"
    selected.write_text(json.dumps(project.to_dict()), encoding="utf-8")
    before = selected.read_bytes()
    report = build_operator_report(tmp_path, operation="layout", project_file=selected)
    assert report["ok"] is True and report["read_only"] is True
    assert report["memory_modified"] is False
    assert report["activation_authorized"] is False
    assert str(tmp_path) not in json.dumps(report)
    assert selected.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == [selected.name]


def test_comparison_uses_existing_native_snapshot_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, project, target, host, _ = native_pair(tmp_path, monkeypatch)
    selected = tmp_path / "project.memory-rebuild.json"
    selected.write_text(json.dumps(project.to_dict()), encoding="utf-8")
    before = target.read_bytes(), host.read_bytes()
    report = build_operator_report(root, operation="comparison", project_file=selected)
    assert report["ok"] is True
    comparison = report["result"]["comparisons"]["target_vs_host_selected_memory"]
    assert comparison["state"] == "equal"
    assert comparison["lineage"]["verification_state"] == "unverified"
    assert report["activation_authorized"] is False
    assert str(tmp_path) not in json.dumps(report)
    assert (target.read_bytes(), host.read_bytes()) == before


@pytest.mark.parametrize("contents", [b"not json", b"[]", b'{"target_root":null}', b"{" + b"x" * (2 * 1024 * 1024)],
                         ids=["invalid-json", "non-object", "missing-target", "oversize"])
def test_invalid_project_is_blocked_with_safe_codes(tmp_path: Path, contents: bytes) -> None:
    selected = tmp_path / "private-name.json"
    selected.write_bytes(contents)
    report = build_operator_report(tmp_path, operation="layout", project_file=selected)
    assert report["ok"] is False and report["state"] == "blocked"
    assert str(tmp_path) not in json.dumps(report)
    assert selected.name not in json.dumps(report)
    assert selected.read_bytes() == contents


def test_incomplete_pin_cannot_be_treated_as_independent_evidence(tmp_path: Path) -> None:
    report = build_operator_report(tmp_path, operation="readiness", reference=tmp_path / "reference.sqlite3")
    assert report["ok"] is False
    assert report["activation_authorized"] is False


def test_invalid_pin_is_rejected_even_without_runtime(tmp_path: Path) -> None:
    report = build_operator_report(tmp_path, operation="readiness", reference=tmp_path / "reference.sqlite3",
                                   reference_sha256="invalid")
    assert report["ok"] is False and report["state"] == "blocked"


def test_readiness_reports_safe_reason_codes_and_discards_private_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from latka_jazn.tools.memory_rebuild_app import p1_active_memory_readiness as readiness
    monkeypatch.setattr(readiness, "collect_active_memory_evidence", lambda _: {"checks": {
        "process": {"state": "conflict", "issue": "process_identity_not_verified"},
        "endpoint": {"state": "unverified", "issue": "/private/secret-token"}}})
    report = build_operator_report(tmp_path, operation="readiness")
    assert report["result"]["checks"]["process"]["issue"] == "process_identity_not_verified"
    assert report["result"]["checks"]["endpoint"]["issue"] == "evidence_issue_unavailable"
    assert "/private/" not in json.dumps(report)
    assert "secret-token" not in json.dumps(report)


def test_public_launcher_reaches_read_only_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-X", "utf8", str(root / "run.py"),
        "memory-inspection", "--root", str(tmp_path), "--operation", "readiness", "--json"],
        capture_output=True, text=True, encoding="utf-8", timeout=25, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema"] == "jazn_memory_operator_observation/v1"
    assert report["result"]["runtime_ready"] is False
    assert report["result"]["memory_recall_ready"] is None
    assert report["result"]["activation_authorized"] is False
    assert not list(tmp_path.iterdir())
