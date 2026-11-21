"""Regression: first-run dependency findings are read-only.

Dependency Studio, not SetupWizard, owns install / wheelhouse operations.
The original installer test is archived byte-for-byte under tests/archive.
"""
from __future__ import annotations

from pathlib import Path
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton
from tools.jazn_run_studio.core import Controller, Settings
from tools.jazn_run_studio.window import Window
from tools.jazn_run_studio.first_run import SetupWizard


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


def test_missing_dependency_rows_are_read_only_and_still_visible(wizard) -> None:
    rows = [
        {"name": "Testy: pytest", "state": "OPTIONAL_MISSING",
         "detail": "brak", "remedy": "Studio Zależności"},
        {"name": "MCP: uvicorn", "state": "OPTIONAL_MISSING",
         "detail": "brak", "remedy": "Studio Zależności"},
        {"name": "MCP: tzdata", "state": "PASS"},
        {"name": "Unknown: arbitrary", "state": "OPTIONAL_MISSING"},
        {"name": "packaging", "state": "FAIL", "remedy": "diagnostyka"},
    ]
    wizard._render_setup_rows(rows)
    assert wizard.table.columnCount() == 4
    assert wizard.table.rowCount() == len(rows)
    assert wizard.table.item(0, 1).text() == "OPTIONAL_MISSING"
    assert wizard.table.item(1, 3).text() == "Studio Zależności"
    assert wizard.table.item(4, 1).text() == "FAIL"
    assert all(wizard.table.cellWidget(i, col) is None
               for i in range(len(rows)) for col in range(4))
    assert wizard.provision_process is None


def test_refresh_clears_old_rows_without_creating_installer_buttons(wizard) -> None:
    wizard._render_setup_rows([{"name": "MCP: mcp", "state": "OPTIONAL_MISSING"}])
    wizard._render_setup_rows([{"name": "Core", "state": "PASS"}])
    assert wizard.table.rowCount() == 1
    assert wizard.table.item(0, 0).text() == "Core"
    assert wizard.table.cellWidget(0, 3) is None
    assert wizard.findChildren(QPushButton)


def test_wizard_has_no_dependency_install_or_private_wheelhouse_methods(wizard) -> None:
    assert not hasattr(wizard, "install_missing")
    assert not hasattr(wizard, "_start_row_step")
    assert not hasattr(wizard, "_row_finished")
    assert wizard.provision_process is None
