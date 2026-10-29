"""Operator workspace remains usable without duplicating log panes."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from tests.test_jazn_run_studio_layout import window  # noqa: F401


def test_read_only_startup_check_runs_status_and_model_discovery(window, monkeypatch) -> None:
    actions: list[str] = []
    monkeypatch.setattr(window.core, "start_action", lambda key: actions.append(key))
    monkeypatch.setattr(window.core, "probe", lambda key: actions.append("probe:" + key))
    window.check_local_readiness()
    assert actions == ["status", "probe:ollama"]
    assert "Nie uruchamiam usług" in window.quick_start_status.text()


def test_only_one_log_panel_visible_at_once(window) -> None:
    window.log_view("probe:ollama")
    assert window.tabs.isVisible() is False  # no surprise popups after an error
    window.workspace.show(1)
    assert window.workspace.dock.isVisible()
    assert not window.tabs.isVisible()
    window.toggle_logs()
    assert window.tabs.isVisible()
    assert not window.workspace.dock.isVisible()


def test_problem_has_remedy_not_just_exception_class(window) -> None:
    workspace = window.workspace
    workspace.observe("probe:ollama", "state", {
        "key": "probe:ollama",
        "state": "failed",
        "error": "connection_refused",
        "finished": 1_793_223_100.0,
    })
    workspace.show(0)
    assert workspace.problems.topLevelItemCount() >= 1
    group = workspace.problems.topLevelItem(0)
    assert group.childCount() == 1
    problem = group.child(0)
    assert "Ollama" in problem.text(1)
    workspace.problems.setCurrentItem(problem)
    assert "Co zrobić:" in workspace.problem_details.text()
    assert "/api/tags" in workspace.problem_details.text()
    window.core.emit("probe:ollama", "log", "Test połączenia nie powiódł się")
    window.poll()
    workspace.show_selected_logs()
    assert workspace.tabs.currentIndex() == 1
    assert workspace.source.currentData() == "probe:ollama"



def test_long_raw_logs_are_truncated_only_in_view(window) -> None:
    text = "x" * 1200
    window.core.emit("probe:ollama", "log", text)
    window.poll()
    window.workspace.refresh()
    assert "[skrócono w widoku]" in window.workspace.output.toPlainText()
    assert len(window.core.logs["probe:ollama"][-1]) == 1200
