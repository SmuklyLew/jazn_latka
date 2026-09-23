from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.dependencies.common import (
    default_environments_root,
    default_local_python_root,
    default_wheelhouse_root,
    environment_marker_path,
)


def test_default_dependency_state_lives_in_host_workspace_not_active_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime_roots" / "jazn-v16.3.25.5.5"
    runtime_root.mkdir(parents=True)

    workspace = workspace_runtime_path(runtime_root)
    expected = workspace / "local_resources" / "python"
    local_python = default_local_python_root(runtime_root)

    assert local_python == expected
    assert default_wheelhouse_root(runtime_root) == expected / "wheelhouse"
    assert default_environments_root(runtime_root) == expected / "environments"
    assert environment_marker_path(runtime_root) == expected / "JAZN_DEPENDENCY_ENVIRONMENT.json"
    assert workspace != runtime_root / "workspace_runtime"
    with pytest.raises(ValueError):
        local_python.relative_to(runtime_root)


def test_dependency_environment_override_remains_explicit_operator_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    explicit = tmp_path / "operator-managed-envs"
    monkeypatch.setenv("JAZN_DEPENDENCY_ENVIRONMENTS", str(explicit))

    assert default_environments_root(runtime_root) == explicit.resolve()
    assert default_wheelhouse_root(runtime_root).parent == workspace_runtime_path(runtime_root) / "local_resources" / "python"
