"""JSS handoff is single-shot and guarded for both private and External Python."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

import run_studio
from latka_jazn.dependencies import environment_manager, private_python, process_handoff


@pytest.fixture
def studio_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(run_studio, "__file__", str(tmp_path / "run_studio.py"))
    return tmp_path


def _never_handoff(*_args: object, **_kwargs: object) -> int:
    pytest.fail("recursive or unsafe handoff attempted")


@pytest.mark.parametrize("mode", ["external", "private"])
def test_studio_recursion_guard_precedes_handoff(
    studio_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    monkeypatch.setenv("JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE", "1")
    monkeypatch.setattr(process_handoff, "handoff_to_managed_python", _never_handoff)
    if mode == "external":
        monkeypatch.setattr(environment_manager, "load_environment_policy", lambda _root: {"mode": "external"})
        monkeypatch.setattr(environment_manager, "inspect_external_environment", lambda _root, _policy: {
            "ready": True, "current": False, "python_executable": "external-test-python", "errors": [],
        })
        monkeypatch.setattr(private_python, "private_python_status", lambda _root: pytest.fail("private path used"))
        expected = "external_environment_handoff_not_established"
    else:
        monkeypatch.setattr(environment_manager, "load_environment_policy", lambda _root: None)
        monkeypatch.setattr(private_python, "private_python_status", lambda _root: {
            "present": True, "ready": True, "current": False,
            "python_executable": "private-test-python", "state": "ready",
        })
        expected = "private_python_handoff_not_established"
    assert run_studio.main() == 78
    assert expected in capsys.readouterr().err


@pytest.mark.parametrize("mode,python_name", [
    ("external", "external-test-python"),
    ("private", "private-test-python"),
])
def test_verified_selection_uses_one_canonical_handoff(
    studio_root: Path, monkeypatch: pytest.MonkeyPatch, mode: str, python_name: str,
) -> None:
    monkeypatch.delenv("JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE", raising=False)
    monkeypatch.setattr(run_studio.sys, "argv", ["run_studio.py", "--operator-test"])
    calls: list[tuple[str, list[str], bool]] = []

    def record(python: str, argv: list[str], *, replace_process: bool) -> int:
        calls.append((python, argv, replace_process))
        return 29

    monkeypatch.setattr(process_handoff, "handoff_to_managed_python", record)
    if mode == "external":
        monkeypatch.setattr(environment_manager, "load_environment_policy", lambda _root: {"mode": "external"})
        monkeypatch.setattr(environment_manager, "inspect_external_environment", lambda _root, _policy: {
            "ready": True, "current": False, "python_executable": python_name, "errors": [],
        })
        monkeypatch.setattr(private_python, "private_python_status", lambda _root: pytest.fail("private path used"))
    else:
        monkeypatch.setattr(environment_manager, "load_environment_policy", lambda _root: None)
        monkeypatch.setattr(private_python, "private_python_status", lambda _root: {
            "present": True, "ready": True, "current": False,
            "python_executable": python_name, "state": "ready",
        })
    assert run_studio.main() == 29
    assert calls == [(python_name, [str(studio_root / "run_studio.py"), "--operator-test"], True)]


def test_private_broken_environment_fails_before_handoff(
    studio_root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(environment_manager, "load_environment_policy", lambda _root: None)
    monkeypatch.setattr(private_python, "private_python_status", lambda _root: {
        "present": True, "ready": False, "current": False,
        "python_executable": None, "state": "private_venv_incomplete",
    })
    monkeypatch.setattr(process_handoff, "handoff_to_managed_python", _never_handoff)
    assert run_studio.main() == 78
