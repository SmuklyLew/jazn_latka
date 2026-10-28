"""Real Qt interactions over synthetic isolated controllers, not live acceptance."""
from pathlib import Path
import json
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDockWidget, QWizard

from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.core import Job, Settings
from tools.jazn_run_studio.first_run import SetupWizard
from tools.jazn_run_studio.workspace_layout import SCHEMA, load_layout, save_layout, validate


def test_search_navigation_and_settings_do_not_save(window):
    window.section_search.setText("Developer")
    window.select_search_result()
    assert window.current_section.text() == "Developer"
    window.navigate("Ustawienia")
    original = window.core.settings
    window.settings_category.setCurrentText("Modele")
    window.settings_search.setText("Model Ollama")
    assert not window.fields["model"].isHidden()
    assert window.fields["daemon_url"].isHidden()
    window.fields["model"].setText("gemma3:latest")
    assert "Niezapisane" in window.settings_hint.text()
    assert window.core.settings == original
    window.reset_settings_draft()
    assert window.fields["model"].text() == Settings().model


def test_docks_can_move_hide_reopen_and_layout_is_primitive_json(window, tmp_path, monkeypatch):
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "layout-workspace"))
    assert isinstance(window.workspace.dock, QDockWidget)
    window.workspace.show(1)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, window.workspace.dock)
    window.switch_sidebar()
    window.persist_layout()
    saved = load_layout(window.core.root)
    assert saved["sidebar_right"] is True and saved["dock_area"] == 1
    assert saved["dock_visible"] is True
    window.workspace.dock.hide()
    window.workspace.show(2)
    assert window.workspace.dock.isVisible()
    assert window.workspace.tabs.currentIndex() == 2
    assert len(window.workspace.consoles) == 3
    assert all(console.output.isReadOnly() for console in window.workspace.consoles)


@pytest.mark.parametrize("payload", [
    {"schema": "old/v0"}, {"schema": SCHEMA, "width": 999999},
    {"schema": SCHEMA, "height": True}, {"schema": SCHEMA, "dock_area": 8},
    {"schema": SCHEMA, "pickle": "danger"}, {"schema": SCHEMA, "setup_scope": "invalid"},
])
def test_untrusted_layout_rejected(payload):
    with pytest.raises(ValueError):
        validate(payload)


def test_service_evidence_is_not_invented_from_pid(window):
    window.core.emit("status", "evidence", {"pid": 12345, "process_identity_confirmed": False})
    window.poll()
    assert window.services_table.item(0, 2).text() == "12345"
    assert window.services_table.item(0, 4).text() == "niezweryfikowana"
    assert window.services_table.item(1, 4).text() == "niezweryfikowana"


def test_optional_service_failure_visible_and_searchable(window):
    window.core.emit("probe:ollama", "state", {"state": "failed", "error": "URLError", "started": 1, "finished": 2})
    window.poll()
    assert "Problemy: 1" in window.workspace.problem_summary.text()
    assert window.workspace.problems.topLevelItem(0).text(0) == "Usługi opcjonalne"
    window.workspace.problem_search.setText("unmatched")
    assert window.workspace.problems.topLevelItemCount() == 0
    window.workspace.problem_search.clear()
    assert window.workspace.problems.topLevelItemCount() == 1
    window.core.emit("probe:ollama", "state", {"state": "succeeded", "error": None, "started": 3, "finished": 4})
    window.poll()
    assert "Nie wykryto problemów" in window.workspace.problem_summary.text()


def test_wizard_is_nonblocking_and_does_not_complete_failed_requirements(window, monkeypatch):
    job = Job("setup:requirements")
    monkeypatch.setattr(window.core, "check_setup", lambda: job)
    wizard = SetupWizard(window.core, lambda s: None, lambda s: None, window)
    wizard.show()
    QTest.qWait(30)
    assert wizard.job is job and not wizard.requirements.isComplete()
    assert wizard.progress.maximum() == 0
    window.core.setup_observation = {"required_ok": False, "rows": [{"name": "integrity", "state": "FAIL"}]}
    job.state = "succeeded"
    job.done.set()
    wizard.poll()
    assert not wizard.requirements.isComplete()
    item = wizard.table.item(0, 1)
    assert item is not None and item.text() == "FAIL"
    wizard.reject()
    assert not window.core.closed


def test_wizard_success_requires_explicit_save_consent(window, monkeypatch):
    job = Job("setup:requirements")
    monkeypatch.setattr(window.core, "check_setup", lambda: job)
    writes, receipts = [], []
    wizard = SetupWizard(window.core, writes.append, receipts.append, window)
    from tools.jazn_run_studio.requirements_worker import setup_scope
    from tools.jazn_run_studio.core import python_executable
    scope = setup_scope(window.core.root, python_executable(window.core.settings))
    wizard.report = {"required_ok": True, "scope": scope}
    wizard.accept()
    assert not writes and not receipts
    wizard.consent.setChecked(True)
    wizard.model.setText("gemma3:latest")
    wizard.accept()
    assert writes[0].model == "gemma3:latest"
    assert receipts == [scope]


def test_outputs_redacted_before_operator_view(window):
    from tools.jazn_run_studio.core import Redactor
    window.core.redactor = Redactor({"TOKEN": "secret-part"})
    window.core.emit("developer:git", "log", "token=secret-part")
    window.poll()
    assert "secret-part" not in window.workspace.output.toPlainText()
    assert "UKRYTO" in window.workspace.output.toPlainText()
