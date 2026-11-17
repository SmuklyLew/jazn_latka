"""Direct installer entrypoints must honor an operator-selected External Python."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from latka_jazn.dependencies import environment, private_extension
from latka_jazn.dependencies.common import DependencyStudioError
from latka_jazn.dependencies.environment_manager import (
    EnvironmentPolicyError, require_operator_managed_environment,
)


def _external(root: Path, **overrides: object) -> None:
    folder = root / ".settings_local"
    folder.mkdir()
    record = {
        "schema_version": "jazn_python_environment/v1",
        "mode": "external",
        "python_executable": str(Path(sys.executable).absolute()),
        "required_profiles": ["core"],
        "automatic_installation": False,
        "automatic_updates": False,
        "allow_environment_deletion": False,
    }
    record.update(overrides)
    (folder / "python_environment.json").write_text(
        json.dumps(record), encoding="utf-8",
    )


def test_direct_install_bundle_refuses_without_touching_wheelhouse(tmp_path: Path) -> None:
    _external(tmp_path)
    with pytest.raises(DependencyStudioError, match="external_environment_mutation_forbidden"):
        environment.install_bundle(tmp_path, tmp_path / "missing-wheelhouse")
    assert not (tmp_path / ".venv").exists()


def test_gc_mutation_is_blocked_but_dry_run_remains_readonly(tmp_path: Path) -> None:
    _external(tmp_path)
    with pytest.raises(DependencyStudioError, match="external_environment_mutation_forbidden"):
        environment.dependency_environment_gc(tmp_path, dry_run=False)
    assert not (tmp_path / ".venv").exists()


def test_private_extension_denied_even_with_operator_supplied_bundle(tmp_path: Path) -> None:
    _external(tmp_path)
    with pytest.raises(DependencyStudioError, match="external_environment_mutation_forbidden"):
        private_extension.extend_private_environment(tmp_path, tmp_path / "wheelhouse")


@pytest.mark.parametrize("mode", ["venv", "install", "extend", "repair", "online", "wizard"])
def test_setup_modes_forbid_external(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    from argparse import Namespace
    from tools import jazn_setup

    _external(tmp_path)
    monkeypatch.setattr(jazn_setup, "ROOT", tmp_path)
    monkeypatch.setattr(jazn_setup, "_root_check", lambda _root: None)
    with pytest.raises(jazn_setup.SetupError, match="external_environment_mutation_forbidden"):
        jazn_setup.execute(Namespace(mode=mode, profile=[]))


@pytest.mark.parametrize("command", ["prepare-resources", "install-python",
                                    "prepare-venv", "download-deps", "install-offline"])
def test_jss_direct_provisioning_is_denied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str,
) -> None:
    from latka_jazn.tools import jss_prerequisite_setup

    _external(tmp_path)
    args = ["--root", str(tmp_path), command, "--yes"]
    if command == "install-offline":
        args.extend(["--bundle", str(tmp_path / "irrelevant")])
    result = jss_prerequisite_setup.main(args)
    output = capsys.readouterr().out
    assert result == 1
    assert json.loads(output)["error_code"] == "external_environment_mutation_forbidden"
    assert not (tmp_path / ".venv").exists()


def test_invalid_policy_cannot_enable_direct_managed_mutation(tmp_path: Path) -> None:
    _external(tmp_path, mode=["external"])
    with pytest.raises(EnvironmentPolicyError, match="environment_policy_mode_invalid"):
        require_operator_managed_environment(tmp_path)
    with pytest.raises(DependencyStudioError, match="environment_policy_mode_invalid"):
        environment.dependency_environment_gc(tmp_path, dry_run=False)
