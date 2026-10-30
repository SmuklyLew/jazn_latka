"""TPA chooses local Ollama models and keeps full acceptance states distinct."""
from __future__ import annotations

import sys

import pytest
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.tpa_view import TPAPanel


@pytest.fixture
def panel(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "SYSTEM"
    root.mkdir()
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    widget = TPAPanel(root, python=sys.executable)
    yield widget
    widget.close()
    app.processEvents()


def test_tpa_model_choice_is_noneditable_and_only_installed_models(panel):
    assert not panel.model.isEditable()
    assert panel.model.currentData() == ""
    panel.set_installed_models(["gemma3:latest", "mistral:latest", "gemma3:latest", ""])
    assert [panel.model.itemData(i) for i in range(1, panel.model.count())] == [
        "gemma3:latest", "mistral:latest",
    ]
    assert panel.model.currentData() == ""
    panel.model.setCurrentIndex(panel.model.findData("mistral:latest"))
    panel.set_installed_models(["mistral:latest", "gemma3:latest"], preferred="gemma3:latest")
    assert panel.model.currentData() == "mistral:latest"
    panel.set_installed_models(["gemma3:latest"], preferred="mistral:latest")
    assert panel.model.currentData() == ""


def test_known_model_from_settings_is_preselected_only_after_detection(panel):
    assert panel.model.currentData() == ""
    panel.set_installed_models(["gemma3:latest"], preferred="gemma3:latest")
    assert panel.model.currentData() == "gemma3:latest"
    panel.set_installed_models([])
    assert panel.model.currentData() == ""


def test_tpa_requests_refresh_without_inventing_models(panel):
    requests = []
    panel.models_requested.connect(lambda: requests.append("probe"))
    panel.refresh_models_button.click()
    assert requests == ["probe"]
    assert panel.model.currentData() == ""


def test_live_resume_requires_selected_installed_model(panel):
    with pytest.raises(ValueError, match="Wykryj modele"):
        panel.start(("chat-resume",), execution="live")
    assert not panel.runner.active


def test_pass_of_isolated_scenario_does_not_promote_manual_gate(panel):
    caption = panel.full_gate_description("NOT_RUN")
    assert "pełny odbiór operatorski" in caption
    assert "PASS" in caption
    assert panel.full_gate_description("PASS") == "PASS"
    # Display helper does not mutate stored status or any acceptance report.
    assert panel.report is None


from tests.test_jazn_run_studio_layout import window  # noqa: E402


def test_settings_model_must_be_chosen_from_discovered_list(window):
    assert window.fields["model"].isReadOnly()
    assert not window.settings_model_selector.isEditable()
    window.set_settings_installed_models(["gemma3:latest", "mistral:latest"])
    assert window.settings_model_selector.findData("gemma3:latest") >= 0
    window.settings_model_selector.setCurrentIndex(
        window.settings_model_selector.findData("gemma3:latest")
    )
    assert window.fields["model"].text() == "gemma3:latest"
    window.set_settings_installed_models([])
    assert window.settings_model_selector.currentData() == ""


def test_readable_report_distinguishes_passed_execution_and_unperformed_full_gate():
    from tools.jazn_run_studio.tpa_reports import readable_report

    report = {
        "run_id": "run-" + "a" * 32,
        "source": {"version": "synthetic"},
        "python": sys.executable,
        "started_utc": "2026-10-30T00:00:00Z",
        "finished_utc": "2026-10-30T00:01:00Z",
        "results": [{
            "status": "PASS", "title": "Wznowienie tury",
            "expected": "Exactly one final", "reason": "accepted and acknowledged",
            "full_gate": "NOT_RUN",
        }],
        "coverage_map": [{
            "id": "chat-resume", "title": "Wznowienie tury",
            "execution_status": "PASS", "full_gate": "NOT_RUN",
            "limitations": "Synthetic fixture.",
        }],
    }
    text = readable_report(report)
    assert "PASS • Wznowienie tury" in text
    assert "Pełna bramka: NOT_RUN — osobny odbiór operatorski do wykonania" in text
    assert report["results"][0]["full_gate"] == "NOT_RUN"
