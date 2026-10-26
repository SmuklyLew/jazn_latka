"""Isolation contract for linked Git worktrees and Studio/TPA operators."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from latka_jazn.core.acceptance_layout import (
    acceptance_environment,
    resolve_acceptance_layout,
)
from latka_jazn.core.runtime_root import (
    default_runtime_workspace_path,
    workspace_runtime_path,
)
from latka_jazn.tools.application_shell.operator_paths import (
    OperatorPathError,
    validate_operator_path,
)


def _root(tmp_path: Path, name: str = "feature-worktree") -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def test_linked_worktree_default_is_root_local_without_moving_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    root = _root(tmp_path)
    marker = root / ".git"
    marker.write_text("gitdir: ../.git/worktrees/example\n", encoding="utf-8")
    old_shared = tmp_path / "workspace_runtime"
    old_shared.mkdir()
    (old_shared / "JAZN_ACTIVE_RUNTIME.json").write_text("leave untouched", encoding="utf-8")

    assert default_runtime_workspace_path(root) == root / "workspace_runtime"
    assert workspace_runtime_path(root) == root / "workspace_runtime"
    assert not (root / "workspace_runtime").exists()
    assert (old_shared / "JAZN_ACTIVE_RUNTIME.json").read_text(encoding="utf-8") == "leave untouched"


def test_main_checkout_and_legacy_nonworktree_defaults_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    master = _root(tmp_path, "jazn_latka_master")
    legacy = _root(tmp_path, "unversioned-system")
    (legacy / ".git").mkdir()  # Main checkout, not a linked worktree.
    assert default_runtime_workspace_path(master) == master / "workspace_runtime"
    assert default_runtime_workspace_path(legacy) == tmp_path / "workspace_runtime"


def test_explicit_override_still_precedes_worktree_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    (root / ".git").write_text("gitdir: dummy\n", encoding="utf-8")
    external = tmp_path / "explicit-runtime"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(external))
    assert workspace_runtime_path(root) == external.resolve()


def test_acceptance_layout_separates_system_memory_runtime_and_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    layout = resolve_acceptance_layout(root, base=tmp_path / "isolated-acceptance")
    assert layout.runtime == tmp_path / "isolated-acceptance" / "runtime"
    assert layout.operator == tmp_path / "isolated-acceptance" / "operator"
    assert layout.memory == layout.runtime / "memory"
    assert root not in layout.operator.parents
    assert layout.runtime not in layout.operator.parents
    assert not layout.operator.exists()
    assert validate_operator_path(layout.operator, root, directory=True) == layout.operator


@pytest.mark.parametrize("relative", (
    "source/workspace_runtime",
    "source/memory",
    "workspace_runtime",
    "memory",
))
def test_acceptance_rejects_protected_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str,
) -> None:
    root = _root(tmp_path, "source")
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    with pytest.raises(ValueError, match="nachodzi"):
        resolve_acceptance_layout(root, base=tmp_path / relative)


def test_acceptance_rejects_external_active_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    protected = tmp_path / "production-memory"
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(protected))
    with pytest.raises(ValueError, match="nachodzi"):
        resolve_acceptance_layout(root, base=protected / "subdir")


def test_acceptance_rejects_symlink_into_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    link = tmp_path / "alias"
    try:
        link.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Host cannot create directory symlink")
    with pytest.raises(ValueError, match="nachodzi"):
        resolve_acceptance_layout(root, base=link / "hidden")


def test_acceptance_environment_is_explicit_and_restores_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    previous = {
        "JAZN_RUNTIME_WORKSPACE_DIR": str(tmp_path / "old-runtime"),
        "JAZN_OPERATOR_STATE_ROOT": str(tmp_path / "old-operator"),
        "JAZN_MEMORY_ROOT": str(tmp_path / "old-memory"),
        "JAZN_MEMORY_MODE": "optional",
    }
    for key, value in previous.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="synthetic"):
        with acceptance_environment(root) as layout:
            assert os.environ["JAZN_RUNTIME_WORKSPACE_DIR"] == str(layout.runtime)
            assert os.environ["JAZN_OPERATOR_STATE_ROOT"] == str(layout.operator)
            assert os.environ["JAZN_MEMORY_ROOT"] == str(layout.memory)
            assert os.environ["JAZN_MEMORY_MODE"] == "off"
            raise RuntimeError("synthetic")
    assert {key: os.environ[key] for key in previous} == previous


def test_tpa_process_environment_is_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("PySide6")
    from tools.jazn_run_studio.tpa_runner import isolated_environment
    root = _root(tmp_path)
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(tmp_path / "private-memory"))
    child = isolated_environment(tmp_path / "tpa_tmp", root)
    assert child.value("JAZN_MEMORY_MODE") == "off"
    assert child.value("JAZN_RUNTIME_WORKSPACE_DIR") == str(tmp_path / "tpa_tmp" / "runtime")
    assert child.value("JAZN_MEMORY_ROOT") == str(tmp_path / "tpa_tmp" / "runtime" / "memory")
    assert child.value("JAZN_OPERATOR_STATE_ROOT") == str(tmp_path / "tpa_tmp" / "operator")
    assert "private-memory" not in child.value("JAZN_MEMORY_ROOT")
