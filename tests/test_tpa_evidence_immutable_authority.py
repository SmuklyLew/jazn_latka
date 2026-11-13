"""Isolated evidence RunStore must not inherit a test fixture's changing ROOT.

The original path guard remains active for every write. No daemon or MEMORY.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.jazn_run_studio.tpa_reports import RunStore
from latka_jazn.tools.application_shell.operator_paths import validate_operator_path


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "prepared-system"
    (root / "local_resources").mkdir(parents=True)
    (root / ".settings").mkdir()
    return root


def test_evidence_path_authority_survives_foreign_workspace_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    output = root / ".settings_local" / "acceptance" / "operator" / "jazn_studio_tpa"
    monkeypatch.setenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", "isolated")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", "$ROOT/workspace_runtime")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    store = RunStore(root, evidence_base=output)
    assert store.folder("run-" + "a" * 32) == output / ("run-" + "a" * 32)
    # Reproduce pytest runtest_logreport while the test's monkeypatch points
    # to a different (synthetic) SYSTEM and operator profile.
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "foreign-workspace"))
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(tmp_path / "foreign-memory"))
    monkeypatch.delenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", raising=False)
    assert store.folder("run-" + "a" * 32) == output / ("run-" + "a" * 32)


def test_unsafe_initial_evidence_context_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    output = root / ".settings_local" / "acceptance" / "operator" / "jazn_studio_tpa"
    monkeypatch.setenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", "isolated")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "foreign-workspace"))
    with pytest.raises(ValueError, match="workspace_escapes_root"):
        RunStore(root, evidence_base=output)


def test_evidence_path_cannot_escape_after_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    output = root / ".settings_local" / "acceptance" / "operator" / "jazn_studio_tpa"
    monkeypatch.setenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", "isolated")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", "$ROOT/workspace_runtime")
    store = RunStore(root, evidence_base=output)
    store.base.mkdir(parents=True)
    escaped = store.base / ("run-" + "b" * 32)
    try:
        escaped.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable to the runner")
    with pytest.raises(ValueError, match="Dowiązanie"):
        store.folder(escaped.name)


def test_explicit_workspace_context_does_not_weaken_path_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "foreign"))
    protected = root / "workspace_runtime" / "danger"
    with pytest.raises(ValueError, match="workspace"):
        validate_operator_path(protected, root, directory=True,
                               workspace_configured=root / "workspace_runtime")
