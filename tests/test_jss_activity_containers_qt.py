"""VS Code-style activity grouping preserves the canonical view registry."""
from __future__ import annotations
import pytest
pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.workbench_shell import ACTIVITY_GROUPS


def test_activity_containers_are_distinct_and_do_not_drop_pages(window) -> None:
    shell = window.workbench
    assert sum(len(sections) for sections in ACTIVITY_GROUPS.values()) == window.nav.count()
    shell.activate_group("Testy i TPA")
    assert window.current_section.text() == "Katalog testów"
    assert shell.activity_actions["Testy i TPA"].isChecked()
    assert any(window.nav.item(i).text() == "TPA" and not window.nav.item(i).isHidden()
               for i in range(window.nav.count()))
    assert any(window.nav.item(i).text() == "Modele AI" and window.nav.item(i).isHidden()
               for i in range(window.nav.count()))
    window.navigate("Czat lokalny")
    assert shell.activity_actions["Czat"].isChecked()
    assert window.sidebar_heading.text() == "CZAT"


def test_small_window_keeps_activity_bar_when_sidebar_is_collapsed(window) -> None:
    window.resize(860, 580)
    QTest.qWait(35)
    assert window.sidebar.isHidden()
    assert window.workbench.activity.isVisible()
    window.workbench.activate_group("Studia")
    assert window.current_section.text() == "Studia Jaźni"
