"""Operator setup and external CLI use the same project interpreter as JSS."""
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.core import Controller, Settings, StudioError
from tools.jazn_run_studio.first_run import SetupWizard
from tools.jazn_run_studio.operator_workspace import OperatorWorkspace
from tools.jazn_run_studio.requirements_worker import setup_scope


@pytest.fixture
def core(tmp_path, monkeypatch):
    monkeypatch.delenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", raising=False)
    monkeypatch.delenv("JAZN_STUDIO_PYTHON", raising=False)
    (tmp_path / ".settings").mkdir()
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text('PACKAGE_VERSION="test"')
    (tmp_path / "main.py").write_text("# test")
    (tmp_path / "run.py").write_text("# test")
    local = tmp_path / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    local.parent.mkdir(parents=True)
    local.write_bytes(b"fixture, not executed")
    (tmp_path / ".venv/pyvenv.cfg").write_text("include-system-site-packages=false\n")
    return Controller(tmp_path, Settings(model="demo")), local


def test_wizard_suggests_project_python_and_accepts_matching_scope(core, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(SetupWizard, "retry", lambda self: None)
    controller, local = core
    saved, completed = [], []
    wizard = SetupWizard(controller, saved.append, completed.append)
    wizard.timer.stop()
    try:
        wizard.suggest_paths()
        assert wizard.setting_fields["python"].text() == str(local)
        wizard.report = {"required_ok": True, "scope": setup_scope(controller.root, str(local))}
        wizard.consent.setChecked(True)
        wizard.accept()
        assert len(saved) == 1 and saved[0].python == str(local)
        assert completed == [setup_scope(controller.root, str(local))]
        assert wizard.finished_setup
    finally:
        wizard.reject()
        app.processEvents()
        controller.close()


@pytest.mark.skipif(os.name != "nt", reason="External Windows console entrypoint")
def test_external_jazn_console_selects_project_python_and_refuses_broken_venv(core, monkeypatch):
    from tools.jazn_run_studio import operator_workspace

    controller, local = core
    workspace = object.__new__(OperatorWorkspace)
    host: Any = SimpleNamespace(core=controller)
    workspace.host = host
    launches = []
    monkeypatch.setattr(operator_workspace.subprocess, "Popen",
                        lambda argv, **kwargs: launches.append((argv, kwargs)))
    workspace.open_tty()
    assert launches[0][0][0] == str(local)
    assert launches[0][1]["cwd"] == controller.root
    local.unlink()
    with pytest.raises(StudioError, match="interpretera"):
        workspace.open_tty()
    assert len(launches) == 1
    controller.close()
