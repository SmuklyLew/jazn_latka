"""Manual log-panel collapse is a user preference, not a one-event timeout."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window


def test_new_error_tab_does_not_reopen_manually_collapsed_logs(window) -> None:
    window.show_log("service:ollama")
    assert window.tabs.isVisible()
    window.toggle_logs()
    assert window.logs_user_hidden and not window.tabs.isVisible()

    window.core.emit("probe:gateway", "state", {
        "state": "failed", "pid": None, "error": "service_not_ready",
    })
    window.poll()

    assert "Błędy" in window.logs
    assert "Zdarzenia" in window.logs
    assert window.logs_user_hidden
    assert not window.tabs.isVisible()
    window.toggle_logs()
    assert window.tabs.isVisible()
    assert "service_not_ready" in window.logs["Błędy"].toPlainText()


def test_incoming_logs_stay_collapsed_until_explicit_repeated_requests(window) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    window.core.emit("status", "log", "first observation")
    window.poll()
    assert window.logs_user_hidden and not window.tabs.isVisible()
    assert window.logs["status"].toPlainText() == "first observation"
    for _ in range(3):
        view = window.show_log("status")
        QApplication.processEvents()
        assert window.tabs.isVisible() and not window.workspace.dock.isVisible()
        assert window.tabs.currentWidget() is view and view.hasFocus()
        assert not window.logs_user_hidden
        QTest.keyClick(view, Qt.Key.Key_J, Qt.KeyboardModifier.ControlModifier)
        assert window.logs_user_hidden and not window.tabs.isVisible()
        window.core.emit("probe:ollama", "state", {"state": "failed", "error": "connection_refused", "pid": None})
        window.poll()
        assert not window.tabs.isVisible() and not window.workspace.dock.isVisible()
        QTest.mouseClick(window.log_toggle, Qt.MouseButton.LeftButton)
        assert window.tabs.isVisible()
        window.toggle_logs()
    assert "connection_refused" in window.logs["Błędy"].toPlainText()


def test_dock_and_legacy_logs_remain_exclusive_through_menu_and_close(window) -> None:
    window.show_log("status")
    for _ in range(3):
        window.workspace.dock.toggleViewAction().trigger()
        assert window.workspace.dock.isVisible() and not window.tabs.isVisible()
        assert window.logs_user_hidden and window.log_toggle.text() == "Pokaż logi"
        window.workspace.dock.close()
        window.toggle_logs()
        assert window.tabs.isVisible() and not window.workspace.dock.isVisible()
    window.reset_layout()
    assert not window.tabs.isVisible() and window.log_toggle.text() == "Pokaż logi"


def test_problem_activation_opens_matching_source_and_full_export(window, monkeypatch, tmp_path) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog, QApplication
    full_line = "prefix " + "x" * 800 + " SOURCE-END"
    window.core.emit("probe:ollama", "log", full_line)
    window.core.emit("other", "log", "other source")
    window.core.emit("probe:ollama", "state", {"state": "failed", "error": "connection_refused", "pid": None})
    window.poll()
    window.workspace.show(0)
    item = window.workspace.problems.topLevelItem(0).child(0)
    window.workspace.problems.setCurrentItem(item)
    window.workspace.problems.setFocus()
    QApplication.processEvents()
    QTest.keyClick(window.workspace.problems, Qt.Key.Key_Return)
    assert window.current_section.text() == "Usługi i procesy"
    assert window.workspace.tabs.currentIndex() == 1
    assert window.workspace.source.currentData() == "probe:ollama"
    assert window.workspace.dock.isVisible() and not window.tabs.isVisible()
    assert "connection_refused" in window.workspace.problem_details.text()
    assert "SOURCE-END" not in window.workspace.output.toPlainText()
    target = tmp_path / "full-output.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    window.workspace.export_output()
    assert target.read_text(encoding="utf-8") == "[probe:ollama] " + full_line
    assert full_line in str(window.core.report())
    assert full_line in window.logs["probe:ollama"].toPlainText()
