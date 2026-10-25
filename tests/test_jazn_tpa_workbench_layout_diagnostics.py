"""Qt width diagnostic preserving the existing 860x580 acceptance assertion."""
from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QWidget
from PySide6.QtTest import QTest
from tests.test_jazn_run_studio_layout import window


def test_service_page_and_stack_fit_minimum_width(window) -> None:
    window.resize(860, 580)
    window.nav.setCurrentRow(1)
    QTest.qWait(150)
    area = window.pages.currentWidget()
    assert isinstance(area, QScrollArea)
    content = area.widget()
    assert isinstance(content, QWidget)
    maximum = area.horizontalScrollBar().maximum()
    diagnostic = {
        "actual_window_width": window.width(),
        "window_minimum_width": window.minimumWidth(),
        "sidebar_width": window.sidebar.width(),
        "shell_width": window.shell_splitter.width(),
        "stack_width": window.pages.width(),
        "stack_minimum_hint": window.pages.minimumSizeHint().width(),
        "scroll_width": area.width(),
        "viewport_width": area.viewport().width(),
        "content_width": content.width(),
        "content_minimum_hint": content.minimumSizeHint().width(),
        "scroll_maximum": maximum,
        "stack_page_minimums": [
            (window.nav.item(i).text(), window.pages.widget(i).minimumSizeHint().width())
            for i in range(window.pages.count())
        ],
        "content_children_minimum": [
            (type(item).__name__, item.objectName(), item.minimumSizeHint().width(), item.sizeHint().width())
            for item in content.findChildren(QWidget)
            if item.minimumSizeHint().width() > 400
        ][:20],
    }
    assert maximum == 0, diagnostic
