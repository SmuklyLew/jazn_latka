"""Synthetic-only Qt navigation: no Ollama process or daemon is started."""
import sys

import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.tpa_catalog import LIVE_CASES
from tools.jazn_run_studio.tpa_view import TPAPanel
from tests.test_tpa_2_current_state import store


def test_wizard_starts_from_first_pending_and_moves_without_approving(store):
    app = QApplication.instance() or QApplication([])
    panel = TPAPanel(store.root, python=sys.executable)
    try:
        panel.wizard_start()
        first = panel.chosen()
        assert panel._wizard_active
        assert first not in LIVE_CASES
        assert "Odroczone live: 5" in panel.wizard_status.text()
        panel.wizard_step(1)
        assert panel.chosen() != first
        assert panel.chosen() not in LIVE_CASES
        assert panel.cell(0, 3).text() == "NOT_RUN"
        panel.wizard_step(-1)
        assert panel.chosen() == first
    finally:
        panel.close()
        app.processEvents()


def test_live_plan_requires_opt_in_and_selected_model(store, monkeypatch):
    app = QApplication.instance() or QApplication([])
    panel = TPAPanel(store.root, python=sys.executable)
    captured = {}
    try:
        monkeypatch.setattr(panel.plan_runner, "start",
                            lambda *args, **kwargs: captured.update(kwargs))
        panel.run_automatic_plan()
        assert captured["regression_only"] is True
        panel.live_plan.setChecked(True)
        with pytest.raises(ValueError, match="model"):
            panel.run_automatic_plan()
        # Merely opting in never creates or starts a model or daemon.
        assert panel.runner.active is False
    finally:
        panel.close()
        app.processEvents()
