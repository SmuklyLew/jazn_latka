"""Source-copy TPA authority and prepared SYSTEM runtime stay independently scoped."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from latka_jazn.core.runtime_root import workspace_runtime_path
from tools.jazn_run_studio import tpa_live
from tools.jazn_run_studio.tpa_paths import TOKEN_ENV, issue_staging, validate_staging


@pytest.fixture
def prepared_tpa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    authority = tmp_path / "prepared-SYSTEM"
    (authority / "local_resources").mkdir(parents=True)
    run_id = "run-" + "a" * 32
    run_folder = authority / ".settings_local" / "acceptance" / "operator" / "jazn_studio_tpa" / run_id
    run_folder.mkdir(parents=True)
    source_copy = run_folder / "source-code"
    source_copy.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(authority / "workspace_runtime"))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "off")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(authority / ".settings_local/acceptance/operator"))
    return authority, run_folder, run_id, source_copy


def test_live_staging_authorized_by_original_root_and_bound_to_copy(prepared_tpa):
    authority, run_folder, run_id, source_copy = prepared_tpa
    folder, token = issue_staging(authority, run_folder, "gui-daemon", execution_root=source_copy)
    claim = json.loads((folder.parent / (folder.name + ".claim.json")).read_text(encoding="utf-8"))
    assert claim["root"] == str(authority.resolve())
    assert claim["execution_root"] == str(source_copy.resolve())
    assert validate_staging(authority, folder, run_id, "gui-daemon", token,
                            execution_root=source_copy) == folder
    assert validate_staging(authority, folder, run_id, "gui-daemon", token,
                            cleaning=True, execution_root=source_copy) == folder


def test_staging_refuses_foreign_source_and_mismatched_lineage(prepared_tpa):
    authority, run_folder, run_id, source_copy = prepared_tpa
    foreign = authority.parent / "other-SYSTEM"
    foreign.mkdir()
    with pytest.raises(ValueError, match="ROOT"):
        issue_staging(authority, run_folder, "chat-reconnect", execution_root=foreign)
    folder, token = issue_staging(authority, run_folder, "gui-daemon", execution_root=source_copy)
    with pytest.raises(ValueError, match="ROOT"):
        validate_staging(authority, folder, run_id, "gui-daemon", token,
                         execution_root=foreign)
    with pytest.raises(ValueError, match="uprawnienie"):
        validate_staging(authority, folder, run_id, "gui-daemon", "wrong-token",
                         execution_root=source_copy)
    with pytest.raises(ValueError, match="uprawnienie"):
        validate_staging(authority, folder, run_id, "gui-daemon", token,
                         execution_root=authority)


def test_live_entrypoint_separates_evidence_authority_from_execution_root(
    prepared_tpa, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
):
    authority, run_folder, run_id, source_copy = prepared_tpa
    folder, token = issue_staging(authority, run_folder, "gui-daemon", execution_root=source_copy)
    monkeypatch.setenv(TOKEN_ENV, token)
    called: list[tuple[Path, Path]] = []

    def fake_exercise(root: Path, staging: Path, *args, **kwargs):
        called.append((root, staging))
        return {"status": "PASS"}

    monkeypatch.setattr(tpa_live, "exercise", fake_exercise)
    monkeypatch.setattr(sys, "argv", [
        "tpa_live", "--root", str(source_copy), "--authority-root", str(authority),
        "--folder", str(folder), "--run-id", run_id, "--case", "gui-daemon",
    ])
    assert tpa_live.main() == 0
    assert called == [(source_copy, folder)]
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert tpa_live.main() == 1  # Replay of a consumed staging claim is refused.
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["status"] == "BLOCKED"
    assert rejected["pre_start_rejected"] is True
    assert called == [(source_copy, folder)]


def test_test_daemon_workspace_is_inside_staged_system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = tmp_path / "live-gui-daemon"
    stage = folder / "SYSTEM"
    (stage / "local_resources").mkdir(parents=True)

    keys = ("JAZN_RUNTIME_WORKSPACE_DIR", "JAZN_MEMORY_ROOT",
            "JAZN_OPERATOR_STATE_ROOT", "JAZN_MEMORY_MODE", "JAZN_STUDIO_ACCEPTANCE_PROFILE")
    with monkeypatch.context() as scoped:
        for key in keys:
            scoped.setenv(key, "test-unset-placeholder")
        tpa_live._set_staged_environment(folder)
        assert Path(os.environ["JAZN_RUNTIME_WORKSPACE_DIR"]) == stage / "workspace_runtime"
        assert workspace_runtime_path(stage) == (stage / "workspace_runtime").resolve()
        assert Path(os.environ["JAZN_OPERATOR_STATE_ROOT"]) == folder / "operator"
        assert os.environ["JAZN_MEMORY_MODE"] == "off"
        scoped.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(folder / "runtime"))
        with pytest.raises(ValueError, match="workspace_escapes_root"):
            workspace_runtime_path(stage)
