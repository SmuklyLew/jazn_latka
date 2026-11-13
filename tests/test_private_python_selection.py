"""Private interpreter selection: no pip, no daemon and no MEMORY side effects."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from latka_jazn.dependencies import environment
from latka_jazn.dependencies import private_python as private


def _fixture_venv(root: Path) -> Path:
    directory = root / ".venv"
    directory.mkdir()
    (directory / "pyvenv.cfg").write_text("include-system-site-packages = false\n", encoding="utf-8")
    executable = private.private_python_path(root)
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture-executable")
    return executable


def test_absent_private_environment_keeps_legacy_selector(tmp_path: Path) -> None:
    result = private.private_python_status(tmp_path)
    assert result["state"] == "absent"
    assert result["present"] is False
    assert result["python_executable"] is None
    assert private.selected_private_python(tmp_path) is None


def test_incomplete_private_environment_fails_closed_before_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".venv").mkdir()
    monkeypatch.setattr(private.subprocess, "run", lambda *_a, **_kw: pytest.fail("probe ran"))
    report = private.private_python_status(tmp_path)
    assert report["state"] == "private_venv_incomplete"
    with pytest.raises(RuntimeError, match="private_venv_incomplete"):
        private.selected_private_python(tmp_path)


def test_private_probe_uses_exact_interpreter_without_pip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    python = _fixture_venv(tmp_path)
    calls: list[list[str]] = []
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert kwargs["timeout"] == 10
        payload = {
            "prefix": str(tmp_path / ".venv"),
            "base_prefix": str(tmp_path),
            "executable": str(python),
            "major": 3,
            "minor": 14,
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")
    monkeypatch.setattr(private.subprocess, "run", fake_run)
    monkeypatch.setattr(private.sys, "executable", str(tmp_path / "outside-python"))
    report = private.private_python_status(tmp_path)
    assert report["ready"] is True
    assert report["current"] is False
    assert calls[0][:4] == [str(python), "-I", "-X", "utf8"]
    assert "-m" not in calls[0] and "pip" not in calls[0]


def test_python_probe_rejects_interpreter_from_another_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    python = _fixture_venv(tmp_path)
    monkeypatch.setattr(private.sys, "executable", str(tmp_path / "elsewhere"))
    monkeypatch.setattr(private.subprocess, "run", lambda argv, **_kw:
        subprocess.CompletedProcess(argv, 0, json.dumps({
            "prefix": str(tmp_path / "foreign"),
            "base_prefix": str(tmp_path),
            "executable": str(python), "major": 3, "minor": 14,
        }), ""))
    assert private.private_python_status(tmp_path)["state"] == "private_venv_identity_mismatch"


def test_healthy_private_venv_precedes_global_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from latka_jazn.dependencies import private_python
    interpreter = str(tmp_path / ".venv" / "bin" / "python")
    monkeypatch.setattr(private_python, "private_python_status", lambda _root: {
        "present": True, "ready": True, "current": False,
        "python_executable": interpreter, "state": "ready",
    })
    monkeypatch.setattr(environment, "dependency_activation_status",
                        lambda _root: pytest.fail("global interpreter was selected"))
    report = environment.prepare_entrypoint_environment(tmp_path, auto_install=False)
    assert report["state"] == "private_python_handoff"
    assert report["reexec_python"] == interpreter


def test_private_venv_rechecks_core_after_windows_handoff_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE", "1")
    monkeypatch.setattr(private, "private_python_status", lambda _root: {
        "present": True, "ready": True, "current": True,
        "python_executable": "private-python", "state": "ready",
    })
    monkeypatch.setattr(environment, "dependency_activation_status",
                        lambda _root: {"current_interpreter_ready": False})
    report = environment.prepare_entrypoint_environment(tmp_path, auto_install=False)
    assert report["ok"] is False
    assert report["state"] == "private_python_dependencies_missing"
    assert report["reexec_python"] is None


def test_broken_private_venv_never_falls_back_to_global_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(private, "private_python_status", lambda _root: {
        "present": True, "ready": False, "current": False,
        "python_executable": None, "state": "private_venv_incomplete",
    })
    monkeypatch.setattr(environment, "dependency_activation_status",
                        lambda _root: pytest.fail("unsafe fallback"))
    result = environment.prepare_entrypoint_environment(tmp_path, auto_install=False)
    assert result["ok"] is False
    assert result["state"] == "private_python_invalid"
