"""Regression for explicit per-row first-run dependency installation."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox
from tools.jazn_run_studio.core import Controller, Settings
from tools.jazn_run_studio.window import Window
from tools.jazn_run_studio.first_run import SetupWizard


@pytest.fixture
def wizard(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").touch()
    (tmp_path / "run.py").touch()
    (tmp_path / "main.py").touch()
    core = Controller(tmp_path, Settings(theme="dark"))
    window = Window(core, smoke=True)
    window.show()
    dialog = SetupWizard(core, lambda _settings: None, lambda _scope: None, window)
    dialog.timer.stop()
    yield dialog
    dialog.close()
    window.close()
    app.processEvents()


def test_install_button_is_only_shown_for_known_missing_capabilities(wizard):
    """Only allowlisted missing rows have an installation action."""
    rows = [
        {"name": "Testy: pytest", "state": "OPTIONAL_MISSING"},
        {"name": "MCP: uvicorn", "state": "OPTIONAL_MISSING"},
        {"name": "MCP: tzdata", "state": "PASS"},
        {"name": "Unknown: arbitrary", "state": "OPTIONAL_MISSING"},
        {"name": "packaging", "state": "FAIL"},
    ]
    wizard._render_setup_rows(rows)
    assert wizard.table.columnCount() == 5
    assert wizard.table.cellWidget(0, 4).text() == "Zainstaluj…"
    assert wizard.table.cellWidget(1, 4).text() == "Zainstaluj…"
    assert wizard.table.cellWidget(2, 4) is None
    assert wizard.table.cellWidget(3, 4) is None
    assert wizard.table.cellWidget(4, 4).text() == "Zainstaluj…"
    wizard._render_setup_rows([{"name": "Testy: pytest", "state": "PASS"}])
    assert wizard.table.cellWidget(0, 4) is None
    assert wizard.provision_process is None


def test_operator_denial_never_starts_install_and_valid_approval_selects_profile(
    wizard, monkeypatch, tmp_path,
):
    """Cancel must be side-effect free; approval selects only the known profile."""
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    from latka_jazn.dependencies import private_python as private_module
    monkeypatch.setattr(private_module, "private_python_status", lambda _root: {"ready": True})
    monkeypatch.setattr(private_module, "private_python_path", lambda _root: python)
    wizard.report = {"rows": [{"name": "Testy: pytest", "state": "OPTIONAL_MISSING"}]}
    calls = []
    monkeypatch.setattr(wizard, "_start_row_step", lambda *args: calls.append(args))
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No
    )
    wizard.install_missing("Testy: pytest")
    wizard.install_missing("MCP: mcp")
    assert calls == []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes
    )
    wizard.install_missing("Testy: pytest")
    assert calls == [("download",)]
    assert wizard._row_profiles == "core,run-studio,mcp-http,test-evidence"
    assert wizard._row_python == str(python)


def test_missing_private_venv_is_refused_before_confirmation(wizard, monkeypatch):
    """A missing ROOT/.venv must not download or create another interpreter."""
    wizard.report = {"rows": [{"name": "MCP: mcp", "state": "OPTIONAL_MISSING"}]}
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: pytest.fail("invalid interpreter must not request approval"),
    )
    wizard.install_missing("MCP: mcp")
    assert wizard.provision_process is None
    assert wizard._row_stage == ""


def test_extension_uses_only_root_venv_and_rejects_foreign_interpreter(
    wizard, monkeypatch, tmp_path,
):
    """Only a verified canonical private Python may replace proposed JSS fields."""
    root_venv = tmp_path / ".venv"
    interpreter = root_venv / "Scripts" / "python.exe"
    marker = root_venv / "JAZN_DEPENDENCY_ENVIRONMENT.json"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    marker.write_text("{}", encoding="utf-8")
    foreign = tmp_path / "foreign-python.exe"
    foreign.touch()
    wizard._row_setting = "python"
    wizard._row_name = "Testy: pytest"
    wizard._row_profiles = "core,run-studio,mcp-http,test-evidence"
    monkeypatch.setattr(wizard, "retry", lambda: None)
    wizard._row_stage = "install"
    wizard._row_output = json.dumps({
        "ok": True, "state": "private_environment_extended",
        "activation_marker_updated": True,
        "profiles": wizard._row_profiles.split(","),
        "python_executable": str(foreign),
        "environment_marker_path": str(marker),
    })
    wizard._row_finished(0, None)
    assert wizard.core.settings.python != str(foreign)
    wizard._row_stage = "install"
    wizard._row_output = json.dumps({
        "ok": True, "state": "private_environment_extended",
        "activation_marker_updated": True,
        "profiles": wizard._row_profiles.split(","),
        "python_executable": str(interpreter),
        "environment_marker_path": str(marker),
    })
    wizard._row_finished(0, None)
    assert wizard.core.settings.python == str(interpreter.resolve())
    assert wizard.core.settings.mcp_python == str(interpreter.resolve())
    assert wizard.setting_fields["python"].text() == str(interpreter.resolve())
    assert wizard.setting_fields["mcp_python"].text() == str(interpreter.resolve())
    assert wizard._provisional_python_setting == str(interpreter.resolve())
