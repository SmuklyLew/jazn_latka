"""Regression: JSS dependency installer must expose failures and accept optional MCP evidence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from latka_jazn.tools import dependency_studio
from tools.jazn_run_studio.core import Controller, Settings
from tools.jazn_run_studio.first_run import SetupWizard
from tools.jazn_run_studio.window import Window


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


def test_dependency_json_summary_bounded_and_parsable(capsys, monkeypatch):
    """Large installer metadata is omitted from the first-run machine response."""
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


def test_dependency_process_failure_is_visible_in_operator_logs(wizard):
    """Missing subprocess JSON must leave a bounded failure event for the operator."""
    wizard._row_name = "MCP: mcp"
    wizard._row_stage = "install"
    wizard._row_output = ""
    wizard._row_stderr = "Traceback (most recent call last):\nRuntimeError: simulated installer failure\n"
    wizard._row_finished(1, None)
    assert "RuntimeError: simulated installer failure" in wizard.stage.text()
    assert "RuntimeError" in wizard.core.logs["setup:dependency-row"][-1]
    assert any(
        key == "setup:dependency-row" and kind == "state"
        and value.get("state") == "failed" and value.get("returncode") == 1
        for key, kind, value in list(wizard.core.events.queue)
    )


def test_optional_mcp_extension_preserves_canonical_root_venv(wizard, tmp_path, monkeypatch):
    """MCP and runtime must use the same ROOT/.venv, not a managed copy."""
    env = tmp_path / ".venv"
    python = env / "Scripts" / "python.exe"
    marker = env / "JAZN_DEPENDENCY_ENVIRONMENT.json"
    python.parent.mkdir(parents=True)
    python.touch()
    marker.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(wizard, "retry", lambda: None)
    wizard._row_name = "MCP: mcp"
    wizard._row_setting = "mcp_python"
    wizard._row_profiles = "core,run-studio,mcp-http,test-evidence"
    wizard._row_stage = "install"
    wizard._row_output = json.dumps({
        "ok": True, "state": "private_environment_extended",
        "profiles": wizard._row_profiles.split(","),
        "python_executable": str(python),
        "environment_marker_path": str(marker),
        "activation_marker_updated": True,
    })
    wizard._row_finished(0, None)
    assert wizard.core.settings.python == str(python.resolve())
    assert wizard.core.settings.mcp_python == str(python.resolve())
    assert wizard.setting_fields["mcp_python"].text() == str(python.resolve())
    assert any(
        key == "setup:dependency-row" and kind == "state"
        and value.get("state") == "succeeded"
        for key, kind, value in list(wizard.core.events.queue)
    )


def test_optional_profile_rejects_foreign_marker(wizard, tmp_path):
    """A foreign marker must not authorize a change even for the correct venv."""
    env = tmp_path / ".venv"
    python = env / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    foreign = tmp_path / "foreign.json"
    foreign.write_text("{}", encoding="utf-8")
    wizard._row_stage = "install"
    wizard._row_name = "MCP: mcp"
    wizard._row_setting = "mcp_python"
    wizard._row_profiles = "core,run-studio,mcp-http,test-evidence"
    wizard._row_output = json.dumps({
        "ok": True, "state": "private_environment_extended",
        "profiles": wizard._row_profiles.split(","),
        "python_executable": str(python),
        "environment_marker_path": str(foreign),
        "activation_marker_updated": True,
    })
    original = wizard.core.settings.mcp_python
    wizard._row_finished(0, None)
    assert wizard.core.settings.mcp_python == original
    assert "managed_environment_not_verified" in wizard.stage.text()
