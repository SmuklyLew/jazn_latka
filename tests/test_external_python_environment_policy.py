"""Regression tests for opt-in External Python (no install, no fallback)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from latka_jazn.dependencies import environment
from latka_jazn.dependencies import environment_manager as manager


def _configure(root: Path, python: Path, **changes: object) -> Path:
    folder = root / ".settings_local"
    folder.mkdir(exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\ndependencies = ["tzdata>=2024.1", "packaging>=24.2,<27"]\n'
        '[project.optional-dependencies]\nrun-studio = ["PySide6-Essentials>=6.12,<6.13"]\n',
        encoding="utf-8",
    )
    registry = root / "latka_jazn" / "resources" / "dependencies"
    registry.mkdir(parents=True)
    (registry / "profiles.json").write_text(json.dumps({
        "profiles": {
            "core": {"source": "project.dependencies"},
            "run-studio": {"source_optional_group": "run-studio"},
        },
    }), encoding="utf-8")
    policy = {
        "schema_version": manager.SCHEMA_VERSION,
        "mode": "external",
        "python_executable": str(python),
        "required_profiles": ["core"],
        "automatic_installation": False,
        "automatic_updates": False,
        "allow_environment_deletion": False,
    }
    policy.update(changes)
    target = folder / manager.CONFIG_NAME
    target.write_text(json.dumps(policy), encoding="utf-8")
    return target


def _fake_probe(monkeypatch: pytest.MonkeyPatch, python: Path,
                *, missing: list[str] | None = None,
                version: list[int] | None = None) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert command[0] == str(python)
        assert command[1:5] == ["-I", "-B", "-X", "utf8"]
        assert "pip" not in command
        assert kwargs["check"] is False
        result = {
            "executable": str(python),
            "python_version": version or [3, 14],
            "implementation": "cpython",
            "architecture": "x86_64",
            "prefix": str(python.parent.parent),
            "base_prefix": "/other",
            "missing": missing or [],
            "incompatible": [],
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(result), "")

    monkeypatch.setattr(manager.subprocess, "run", run)
    return calls


def test_absent_policy_preserves_legacy_without_creating_files(tmp_path: Path) -> None:
    assert manager.load_environment_policy(tmp_path) is None
    assert not manager.policy_path(tmp_path).exists()


def test_external_readonly_and_prefers_operator_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _configure(tmp_path, Path(sys.executable))
    before = target.read_bytes()
    calls = _fake_probe(monkeypatch, Path(sys.executable))
    monkeypatch.setattr(environment, "install_bundle", lambda *a, **k: pytest.fail("pip/venv mutation"))
    monkeypatch.setattr(environment, "materialize_compatible_dependency_artifact",
                        lambda *a, **k: pytest.fail("bundle materialization"))
    result = environment.prepare_entrypoint_environment(tmp_path, auto_install=True)
    assert result["ok"] is True
    assert result["state"] == "external_environment_ready"
    assert result["reexec_python"] is None
    assert len(calls) == 1
    assert target.read_bytes() == before
    assert not (tmp_path / ".venv").exists()


def test_external_missing_dependency_never_bootstraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(tmp_path, Path(sys.executable))
    _fake_probe(monkeypatch, Path(sys.executable), missing=["tzdata"])
    monkeypatch.setattr(environment, "install_bundle", lambda *a, **k: pytest.fail("installation"))
    result = environment.prepare_entrypoint_environment(tmp_path, auto_install=True)
    assert result["ok"] is False
    assert result["state"] == "external_environment_not_ready"
    assert "external_required_distributions_missing" in result["external_environment"]["errors"]


@pytest.mark.parametrize("invalid", [
    {"automatic_installation": True},
    {"automatic_updates": True},
    {"allow_environment_deletion": True},
    {"mode": "managed"},
    {"required_profiles": ["run-studio"]},
    {"python_executable": "python"},
])
def test_invalid_external_policy_fails_closed(
    tmp_path: Path, invalid: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(tmp_path, Path(sys.executable), **invalid)
    monkeypatch.setattr(environment, "install_bundle", lambda *a, **k: pytest.fail("installation"))
    result = environment.prepare_entrypoint_environment(tmp_path, auto_install=True)
    assert result["ok"] is False
    assert result["state"] == "environment_policy_invalid"


def test_external_unsupported_profile_fails_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(tmp_path, Path(sys.executable), required_profiles=["core", "nonexistent"])
    monkeypatch.setattr(manager.subprocess, "run",
                        lambda *a, **k: pytest.fail("interpreter launch"))
    result = manager.inspect_external_environment(
        tmp_path, manager.load_environment_policy(tmp_path),
    )
    assert result["status"] == "INVALID"
    assert "external_unknown_profile:nonexistent" in result["errors"]


def test_external_does_not_repeat_failed_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_python = tmp_path / "python"
    fake_python.write_bytes(b"test fixture, not executed")
    _configure(tmp_path, fake_python)
    _fake_probe(monkeypatch, fake_python)
    monkeypatch.setenv("JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE", "1")
    result = environment.prepare_entrypoint_environment(tmp_path, auto_install=True)
    assert result["ok"] is False
    assert result["state"] == "external_environment_handoff_not_established"
    assert result["reexec_python"] is None


def test_external_rejects_unverified_interpreter_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(tmp_path, Path(sys.executable))
    _fake_probe(monkeypatch, Path(sys.executable), version=[3, 15])
    result = manager.inspect_external_environment(
        tmp_path, manager.load_environment_policy(tmp_path),
    )
    assert result["ready"] is False
    assert "external_python_unsupported_version" in result["errors"]


def test_jss_launcher_honors_external_without_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import run_studio
    from tools.jazn_run_studio import dependency_preflight

    _configure(tmp_path, Path(sys.executable))
    _fake_probe(monkeypatch, Path(sys.executable))
    monkeypatch.setattr(run_studio, "__file__", str(tmp_path / "run_studio.py"))
    monkeypatch.setattr(dependency_preflight, "dispatch", lambda: 19)
    assert run_studio.main() == 19


def test_studio_selector_obeys_explicit_external(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.jazn_run_studio.core import Settings, StudioError, python_executable

    _configure(tmp_path, Path(sys.executable))
    _fake_probe(monkeypatch, Path(sys.executable))
    assert python_executable(Settings(python=sys.executable), root=tmp_path) == sys.executable
    with pytest.raises(StudioError, match="inny niż wybrany External"):
        python_executable(Settings(python=str(tmp_path / "another-python")), root=tmp_path)
