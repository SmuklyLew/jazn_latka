"""Security contracts for local settings and acceptance isolation."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from latka_jazn.core.acceptance_layout import (
    acceptance_environment,
)
from latka_jazn.tools.application_shell.operator_paths import (
    OperatorPathError,
    operator_state_dir,
    operator_file,
    validate_operator_path,
)
from tools.jazn_run_studio.core import (
    Settings,
    StudioError,
    load_settings,
    save_settings,
    settings_path,
)


@pytest.fixture
def root(tmp_path, monkeypatch):
    system = tmp_path / "system"
    (system / ".settings").mkdir(parents=True)

    for key in (
        "JAZN_OPERATOR_STATE_ROOT",
        "JAZN_STUDIO_ACCEPTANCE_PROFILE",
        "JAZN_RUNTIME_WORKSPACE_DIR",
        "JAZN_MEMORY_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)

    return system


@pytest.mark.parametrize("part", [
    "secrets",
    "checkpoints",
    "acceptance",
    "acceptance/runtime",
    "acceptance/operator",
    "wheelhouse",
    "environments",
    "cache",
])
def test_unprivileged_operator_write_denied(root, part):
    path = root / ".settings_local" / part / "test.json"

    with pytest.raises(OperatorPathError):
        validate_operator_path(path, root)


def test_regular_operator_write_allowed(root):
    path = root / ".settings_local/operator/test.json"

    assert validate_operator_path(path, root) == path


def test_acceptance_requires_explicit_scope(root):
    allowed = root / ".settings_local/acceptance/operator"
    forbidden = root / ".settings_local/acceptance/runtime"

    with pytest.raises(OperatorPathError):
        validate_operator_path(allowed, root, directory=True)

    assert validate_operator_path(
        allowed, root, directory=True,
        allow_acceptance_operator=True,
    ) == allowed

    with pytest.raises(OperatorPathError):
        validate_operator_path(
            forbidden, root, directory=True,
            allow_acceptance_operator=True,
        )


def test_isolated_acceptance_keeps_operator_access(root):
    with acceptance_environment(root) as layout:
        assert layout.operator == (
            root / ".settings_local/acceptance/operator"
        )

        state = operator_state_dir("smoke", root)
        assert state.is_relative_to(layout.operator)

        settings = operator_file("smoke", root, "settings.json")
        assert settings.is_relative_to(layout.operator)


def test_worktrees_have_distinct_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", raising=False)

    left = tmp_path / "left"
    right = tmp_path / "right"

    (left / ".settings").mkdir(parents=True)
    (right / ".settings").mkdir(parents=True)

    assert settings_path(left) != settings_path(right)


def test_redirected_operator_directory_rejected(root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()

    local = root / ".settings_local"
    local.mkdir()

    try:
        (local / "operator").symlink_to(
            outside, target_is_directory=True
        )
    except (OSError, NotImplementedError):
        pytest.skip("Host does not allow directory symlinks")

    with pytest.raises((ValueError, OperatorPathError)):
        validate_operator_path(
            local / "operator/settings.json", root
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_windows_junction_rejected(root, tmp_path):
    local = root / ".settings_local"
    local.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    link = local / "operator"

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        pytest.skip("Cannot create junction on this host")

    with pytest.raises((ValueError, OperatorPathError)):
        validate_operator_path(
            link / "test.json", root
        )


def test_legacy_settings_are_preserved(root):
    legacy = root / "workspace_runtime/jazn_run_studio/settings.json"
    legacy.parent.mkdir(parents=True)

    previous = asdict(Settings(
        daemon_url="http://127.0.0.1:8796",
        mcp_port="8081",
    ))

    old_data = json.dumps(previous).encode("utf-8")
    legacy.write_bytes(old_data)

    loaded, digest = load_settings(root)
    assert loaded.daemon_url == "http://127.0.0.1:8796"
    assert loaded.mcp_port == "8081"
    assert digest is not None

    saved_digest = save_settings(root, loaded, digest)

    assert legacy.read_bytes() == old_data
    assert settings_path(root).is_file()
    assert not (root / "jazn_system_config.json").exists()

    reopened, current_digest = load_settings(root)

    assert current_digest == saved_digest
    assert reopened.daemon_url == loaded.daemon_url
    assert reopened.mcp_port == loaded.mcp_port

    # Stale writer must not silently overwrite newer settings.
    settings_path(root).write_text(
        json.dumps({
            **asdict(reopened),
            "mcp_port": "8082",
        }),
        encoding="utf-8",
    )

    with pytest.raises(StudioError, match="zmieniły"):
        save_settings(root, reopened, saved_digest)

    assert legacy.read_bytes() == old_data
