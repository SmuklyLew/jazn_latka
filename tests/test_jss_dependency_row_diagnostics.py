"""Dependency Studio owns installer diagnostics; first-run only reads them.

Original installer-in-the-wizard test is archived byte-for-byte in tests/archive.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from latka_jazn.dependencies import private_python
from latka_jazn.dependencies.common import DependencyStudioError
from latka_jazn.tools import dependency_studio
from tools.jazn_run_studio.core import Controller, Settings
from tools.jazn_run_studio.first_run import SetupWizard
from tools.jazn_run_studio.requirements_worker import setup_scope
from tools.jazn_run_studio.window import Window


@pytest.fixture
def wizard(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    (tmp_path / "latka_jazn").mkdir()
    for marker in ("latka_jazn/version.py", "run.py", "main.py"):
        (tmp_path / marker).touch()
    core = Controller(tmp_path, Settings(theme="dark"))
    window = Window(core, smoke=True)
    window.show()
    dialog = SetupWizard(core, lambda _settings: None, lambda _scope: None, window)
    dialog.timer.stop()
    yield dialog
    dialog.close()
    window.close()
    app.processEvents()


def test_dependency_json_summary_bounded_and_parsable(capsys, monkeypatch):
    """Large metadata must not leak into the operator-facing machine summary."""
    payload = {
        "ok": True, "command": "install", "state": "optional_environment_ready",
        "profiles": ["core", "mcp-http"],
        "environment_marker_path": "C:/managed/marker.json",
        "marker": {"pip_inspect": "x" * 850000},
    }
    monkeypatch.setattr(dependency_studio, "execute", lambda _ns: (0, payload))
    assert dependency_studio.main(["--json-summary", "install", "--offline"]) == 0
    rendered = capsys.readouterr().out
    data = json.loads(rendered)
    assert len(rendered) < 4096
    assert data["state"] == "optional_environment_ready"
    assert data["profiles"] == ["core", "mcp-http"]
    assert "marker" not in data


def test_dependency_studio_error_remains_visible_without_wizard_installer(capsys, monkeypatch):
    """A real failed Dependency Studio command must retain a bounded error."""
    def refused(_ns):
        raise DependencyStudioError("simulated installer failure")

    monkeypatch.setattr(dependency_studio, "execute", refused)
    assert dependency_studio.main(["--json-summary", "install", "--offline"]) == 2
    rendered = capsys.readouterr().out
    payload = json.loads(rendered)
    assert len(rendered) < 4096
    assert payload["ok"] is False
    assert payload["error_type"] == "DependencyStudioError"
    assert "simulated installer failure" in payload["error"]


def test_optional_mcp_dependency_diagnostic_cannot_install_inside_wizard(wizard):
    """Missing MCP is visible but never starts installer or changes Python."""
    before_python = wizard.core.settings.python
    before_mcp = wizard.core.settings.mcp_python
    wizard._render_setup_rows([
        {"name": "MCP: mcp", "state": "OPTIONAL_MISSING",
         "detail": "Brak importu", "remedy": "Studio Zależności"}
    ])
    assert wizard.table.item(0, 1).text() == "OPTIONAL_MISSING"
    assert wizard.table.item(0, 3).text() == "Studio Zależności"
    assert wizard.table.cellWidget(0, 3) is None
    wizard.provision("install-offline")
    assert "Studio Zależności" in wizard.provision_result.text()
    assert wizard.provision_process is None
    assert wizard.core.settings.python == before_python
    assert wizard.core.settings.mcp_python == before_mcp


def test_onboarding_accept_rejects_foreign_mcp_interpreter(wizard, monkeypatch):
    """Foreign interpreter cannot masquerade as project-owned ROOT/.venv."""
    root = wizard.core.root
    canonical = private_python.private_python_path(root)
    canonical.parent.mkdir(parents=True)
    canonical.touch()
    foreign = root / "foreign-python.exe"
    foreign.touch()
    monkeypatch.setattr(
        private_python, "private_python_status", lambda _root: {"ready": True}
    )
    wizard.setting_fields["python"].setText(str(canonical))
    wizard.setting_fields["mcp_python"].setText(str(foreign))
    wizard.report = {"required_ok": True}
    wizard.consent.setChecked(True)
    wizard.save = lambda _settings: pytest.fail("foreign interpreter must not be saved")
    wizard.accept()
    assert wizard.finished_setup is False
    assert "Jaźń i MCP muszą używać jednego ROOT/.venv" in wizard.notice.text()


def test_onboarding_accepts_only_verified_canonical_python(wizard, monkeypatch):
    """The retained final setup gate binds both roles to the same project venv."""
    root = wizard.core.root
    canonical = private_python.private_python_path(root)
    canonical.parent.mkdir(parents=True)
    canonical.touch()
    monkeypatch.setattr(
        private_python, "private_python_status", lambda _root: {"ready": True}
    )
    wizard.setting_fields["python"].setText(str(canonical))
    wizard.setting_fields["mcp_python"].setText(str(canonical))
    scope = setup_scope(root, str(canonical.resolve()))
    wizard.report = {
        "required_ok": True, "scope": scope,
        "mcp": {"interpreter": str(canonical.resolve())},
    }
    wizard.consent.setChecked(True)
    saved = []
    completed = []
    wizard.save = lambda settings: saved.append(settings)
    wizard.completed = lambda value: completed.append(value)
    wizard.accept()
    assert wizard.finished_setup is True
    assert len(saved) == 1
    assert saved[0].python == saved[0].mcp_python == str(canonical.resolve())
    assert completed == [scope]
