"""Model choice in offscreen TPA smoke is limited to locally observed Ollama models."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from tools.jazn_run_studio.tpa_smoke import select_existing_model
from tools.jazn_run_studio.tpa_view import TPAPanel


@pytest.fixture
def panel(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    widget = TPAPanel(tmp_path, python=sys.executable)
    yield widget
    widget.close()
    app.processEvents()


def test_smoke_selects_only_verified_inventory_model(panel: TPAPanel) -> None:
    select_existing_model(panel, "gemma3:latest", ["gemma3:latest", "qwen3:latest"])
    assert panel.model.currentData() == "gemma3:latest"
    assert panel.model.isEditable() is False


def test_smoke_rejects_unknown_model_without_substitution(panel: TPAPanel) -> None:
    with pytest.raises(ValueError, match="nie jest zainstalowany"):
        select_existing_model(panel, "not-installed:latest", ["gemma3:latest"])
    assert panel.model.currentData() == ""


def test_smoke_rejects_empty_inventory(panel: TPAPanel) -> None:
    with pytest.raises(ValueError, match="nie jest zainstalowany"):
        select_existing_model(panel, "gemma3:latest", [])
