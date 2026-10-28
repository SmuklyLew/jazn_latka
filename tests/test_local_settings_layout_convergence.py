"""Contract tests for worktree-owned configuration paths."""
from pathlib import Path

import pytest

from latka_jazn.core.local_settings_layout import (
    local_settings_enabled,
    resolve_local_settings_layout,
)
from latka_jazn.core.acceptance_layout import resolve_acceptance_layout
from latka_jazn.tools.application_shell.operator_paths import operator_state_dir
from tools.jazn_run_studio.core import settings_path


def test_versioned_settings_enables_local_layout(tmp_path: Path):
    system = tmp_path / "system"
    (system / ".settings").mkdir(parents=True)
    layout = resolve_local_settings_layout(system)
    assert layout.local == system / ".settings_local"
    assert layout.operator == layout.local / "operator"
    assert layout.acceptance == layout.local / "acceptance"
    assert not layout.local.exists()


def test_acceptance_and_studio_are_owned_by_worktree(tmp_path: Path, monkeypatch):
    system = tmp_path / "system"
    (system / ".settings").mkdir(parents=True)
    for key in ("JAZN_OPERATOR_STATE_ROOT", "JAZN_MEMORY_ROOT",
                "JAZN_RUNTIME_WORKSPACE_DIR", "JAZN_STUDIO_ACCEPTANCE_PROFILE"):
        monkeypatch.delenv(key, raising=False)
    layout = resolve_acceptance_layout(system)
    assert layout.runtime == system / ".settings_local/acceptance/runtime"
    assert layout.operator == system / ".settings_local/acceptance/operator"
    assert operator_state_dir("jazn_run_studio", system) == (
        system / ".settings_local/operator/jazn_run_studio"
    )
    assert settings_path(system) == (
        system / ".settings_local/operator/jazn_run_studio/settings.json"
    )
    assert not (system / ".settings_local").exists()


def test_legacy_root_remains_separate(tmp_path: Path):
    system = tmp_path / "legacy"
    system.mkdir()
    assert not local_settings_enabled(system)
    layout = resolve_acceptance_layout(system)
    assert not layout.runtime.is_relative_to(system)


def test_redirected_local_root_is_rejected(tmp_path: Path):
    system = tmp_path / "system"
    (system / ".settings").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (system / ".settings_local").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable on this host")
    with pytest.raises(ValueError):
        resolve_local_settings_layout(system)
