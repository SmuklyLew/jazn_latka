"""Regression: JSS prefers a checkout-owned venv without touching runtime state."""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

from tools.jazn_run_studio.core import (
    Controller, Settings, StudioError, discovery, project_python_executable,
    python_candidate_for_ui, python_executable,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text('PACKAGE_VERSION="test"', encoding="utf-8")
    (tmp_path / "main.py").write_text("# synthetic system", encoding="utf-8")
    (tmp_path / "run.py").write_text("print('synthetic')", encoding="utf-8")
    return tmp_path


def make_local_venv(root: Path) -> Path:
    venv = root / ".venv"
    script = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    script.parent.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("include-system-site-packages = false\n", encoding="utf-8")
    script.write_bytes(b"synthetic interpreter, never executed")
    return script


def test_fallback_to_host_without_project_environment(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JAZN_STUDIO_PYTHON", raising=False)
    assert project_python_executable(root) is None
    assert python_executable(Settings(), root) == sys.executable


def test_project_venv_used_for_runtime_and_discovery(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JAZN_STUDIO_PYTHON", raising=False)
    local = make_local_venv(root)
    assert project_python_executable(root) == str(local)
    assert python_executable(Settings(), root) == str(local)
    assert discovery(Settings(), root)["python"] == str(local)
    core = Controller(root)
    assert core.command("version")[0] == str(local)


def test_explicit_operator_setting_and_environment_win(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = make_local_venv(root)
    custom = tmp_path / "operator-python.exe"
    custom.write_bytes(b"synthetic, never executed")
    monkeypatch.setenv("JAZN_STUDIO_PYTHON", str(custom))
    assert python_executable(Settings(), root) == str(custom)
    assert python_executable(Settings(python=sys.executable), root) == sys.executable
    assert str(local) != str(custom)
    with pytest.raises(StudioError, match="Nieprawidłowy"):
        python_executable(Settings(python=str(root / "missing-python.exe")), root)


def test_broken_project_venv_fails_closed_without_host_fallback(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAZN_STUDIO_PYTHON", raising=False)
    (root / ".venv").mkdir()
    with pytest.raises(StudioError, match="pyvenv.cfg"):
        python_executable(Settings(), root)
    report = discovery(Settings(), root)
    assert report["python"] is None
    assert "pyvenv.cfg" in report["python_error"]
    # The UI can open but must not silently use the host interpreter.
    expected = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert python_candidate_for_ui(Settings(), root) == str(expected)


def test_project_venv_requires_interpreter_file(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAZN_STUDIO_PYTHON", raising=False)
    venv = root / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("include-system-site-packages = false\n", encoding="utf-8")
    with pytest.raises(StudioError, match="interpretera"):
        python_executable(Settings(), root)


def test_mcp_uses_same_default_or_explicit_overrides(root: Path, tmp_path: Path) -> None:
    local = make_local_venv(root)
    assert python_executable(Settings(python=""), root) == str(local)
    other = tmp_path / "python-for-mcp"
    other.write_bytes(b"synthetic, never executed")
    assert python_executable(Settings(python=str(other)), root) == str(other)


def test_independent_worktrees_never_share_project_venv(tmp_path: Path) -> None:
    first = tmp_path / "master"
    second = tmp_path / "feature"
    first.mkdir()
    second.mkdir()
    assert python_executable(Settings(), first) == sys.executable
    expected = make_local_venv(second)
    assert python_executable(Settings(), second) == str(expected)
    assert python_executable(Settings(), first) != str(expected)
