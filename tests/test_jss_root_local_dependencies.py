"""ROOT-local dependency layout is explicit; existing operator state is preserved."""
from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.dependencies.common import (
    DependencyStudioError,
    default_environments_root,
    default_local_python_root,
    default_wheelhouse_root,
    environment_marker_path,
    existing_environment_marker_path,
    legacy_environment_marker_path,
    root_local_resources_enabled,
)
from latka_jazn.dependencies.environment import dependency_environment_gc


def test_fresh_root_local_resources_selects_root_venv(tmp_path: Path) -> None:
    root = tmp_path / "jazn-system"
    (root / "local_resources").mkdir(parents=True)
    assert root_local_resources_enabled(root)
    assert default_local_python_root(root) == root / "local_resources" / "python"
    assert default_wheelhouse_root(root) == root / "local_resources" / "wheelhouse"
    assert default_environments_root(root) == root / ".venv"
    assert environment_marker_path(root) == (
        root / "local_resources" / "python" / "JAZN_DEPENDENCY_ENVIRONMENT.json"
    )


def test_legacy_host_layout_is_not_moved_implicitly(tmp_path: Path) -> None:
    root = tmp_path / "runtime_roots" / "old-release"
    root.mkdir(parents=True)
    legacy = workspace_runtime_path(root) / "local_resources" / "python"
    assert not root_local_resources_enabled(root)
    assert default_local_python_root(root) == legacy
    assert default_environments_root(root) == legacy / "environments"


def test_missing_new_marker_falls_back_to_legacy_marker(tmp_path: Path) -> None:
    root = tmp_path / "jazn-root"
    (root / "local_resources").mkdir(parents=True)
    old_path = legacy_environment_marker_path(root)
    old_path.parent.mkdir(parents=True)
    old_path.write_text("{}", encoding="utf-8")
    assert existing_environment_marker_path(root) == old_path
    new_path = environment_marker_path(root)
    new_path.parent.mkdir(parents=True)
    new_path.write_text("{}", encoding="utf-8")
    assert existing_environment_marker_path(root) == new_path


def test_root_local_resources_symlinks_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "system"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    try:
        (root / "local_resources").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("host does not permit symlink creation")
    with pytest.raises(DependencyStudioError, match="unsafe_root_local_resources_link"):
        default_wheelhouse_root(root)


def test_gc_never_deletes_root_venv_contents(tmp_path: Path) -> None:
    root = tmp_path / "jazn-root"
    (root / "local_resources").mkdir(parents=True)
    scripts = root / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    sentinel = scripts / "python.exe"
    sentinel.write_bytes(b"fixture")
    report = dependency_environment_gc(root, dry_run=False)
    assert report["gc_candidates"] == []
    assert report["removed"] == []
    assert sentinel.read_bytes() == b"fixture"


def test_explicit_environments_override_remains_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "system"
    (root / "local_resources").mkdir(parents=True)
    separate = tmp_path / "operator-venvs"
    monkeypatch.setenv("JAZN_DEPENDENCY_ENVIRONMENTS", str(separate))
    assert default_environments_root(root) == separate.resolve()
