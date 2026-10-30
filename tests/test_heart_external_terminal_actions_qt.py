"""Windows terminal actions must not confuse the shell with Jaźń runtime.

These isolated tests assert subprocess arguments only; they do not claim an
embedded ConPTY implementation or a real Windows console acceptance.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window  # noqa: F401
from tools.jazn_run_studio.core import StudioError


def test_operator_menu_keeps_system_shell_and_latka_chat_separate(window) -> None:
    terminal = window.workbench.menus["Terminal"]
    texts = [action.text() for action in terminal.actions()]
    assert "Otwórz PowerShell w osobnym oknie" in texts
    assert "Otwórz lokalny czat Jaźni (run.py)" in texts
    assert "Obsługa PTY / ConPTY" in texts


@pytest.mark.skipif(os.name != "nt", reason="Windows external console API")
def test_external_terminal_opens_system_powershell_without_run_py(window, monkeypatch, tmp_path: Path) -> None:
    system_root = tmp_path / "windows"
    ps = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    ps.parent.mkdir(parents=True)
    ps.touch()
    monkeypatch.setenv("SystemRoot", str(system_root))
    calls = []

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return object()

    monkeypatch.setattr("tools.jazn_run_studio.operator_workspace.subprocess.Popen", fake_popen)
    window.workspace.open_system_terminal()
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [str(ps), "-NoLogo", "-NoExit"]
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == window.core.root
    assert kwargs["creationflags"] != 0
    assert "run.py" not in " ".join(argv)


@pytest.mark.skipif(os.name != "nt", reason="Windows external console API")
def test_missing_system_powershell_fails_closed(window, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    def must_not_spawn(*_args, **_kwargs):
        raise AssertionError("Must not launch any process")
    monkeypatch.setattr("tools.jazn_run_studio.operator_workspace.subprocess.Popen", must_not_spawn)
    with pytest.raises(StudioError, match="PowerShell"):
        window.workspace.open_system_terminal()
