"""Minimum viewport and asynchronous form selection are operational contracts."""
from __future__ import annotations

from pathlib import Path
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QScrollArea
from PySide6.QtTest import QTest
from tools.jazn_run_studio.core import Controller, Settings
from tools.jazn_run_studio.window import Window


@pytest.fixture
def window(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    (tmp_path/"latka_jazn").mkdir()
    (tmp_path/"latka_jazn/version.py").touch()
    (tmp_path/"run.py").touch()
    (tmp_path/"main.py").touch()
    core = Controller(tmp_path, Settings(theme="dark"))
    window = Window(core,smoke=True)
    window.show()
    yield window
    window.close()
    app.processEvents()


def test_service_controls_fit_minimum_supported_width(window: Window) -> None:
    window.resize(860,580)
    window.nav.setCurrentRow(1)
    QTest.qWait(150)
    page = window.pages.currentWidget()
    assert isinstance(page,QScrollArea)
    assert page.horizontalScrollBar().maximum() == 0
    assert all(status.wordWrap() for status in window.statuses.values())


def test_changing_studio_rejects_delayed_schema_for_previous_selection(window: Window) -> None:
    schema = [{"path":["status"],"description":"Read-only status","fields":[]}]
    first = str(window.studio_choice.currentData())
    window.core.emit("helper:schema:"+first,"helper",schema)
    window.poll()
    assert window.execute_button.isEnabled() and window.schema_key == first
    window.studio_choice.setCurrentIndex(1)
    assert not window.execute_button.isEnabled()
    assert not window.command_schema and not window.schema_key
    window.core.emit("helper:schema:"+first,"helper",schema)
    window.poll()
    assert not window.execute_button.isEnabled() and not window.command_schema
