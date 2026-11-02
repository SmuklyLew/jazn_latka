"""Native, explicitly read-only Qt catalogue and verified evidence history.

This migrates *inspection* of test purposes and expectations only. It does not
claim parity with legacy execution, review editing or cancellation.
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)
from tools.jazn_tests_studio.core import filtered

_VISIBLE_ROW_LIMIT = 300
_STATUS_OPTIONS = (
    ("Wszystkie", "all"),
    ("Aktualne", "current"),
    ("Wymaga przeglądu", "review_required"),
    ("Nieaktualne", "obsolete"),
    ("Niezgodne", "incompatible"),
)


class TestCatalogPanel(QWidget):
    """No test execution, review mutation or persistence is possible here."""

    __test__ = False

    def __init__(self, root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.root = root
        self.rows: list[tuple[str, dict]] = []
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        outer.addWidget(tabs)
        catalog_page = QWidget()
        tabs.addTab(catalog_page, "Katalog i oczekiwania")
        from .test_history_view import TestHistoryPanel
        self.history_panel = TestHistoryPanel(root)
        tabs.addTab(self.history_panel, "Historia wyników TPA")
        layout = QVBoxLayout(catalog_page)
        controls = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Szukaj: nazwa, cel, kategoria lub tag")
        self.query.setMaxLength(200)
        self.query.setAccessibleName("Filtr katalogu testów")
        controls.addWidget(self.query)
        self.state_filter = QComboBox()
        self.state_filter.setAccessibleName("Stan przeglądu testów")
        for label, value in _STATUS_OPTIONS:
            self.state_filter.addItem(label, value)
        controls.addWidget(self.state_filter)
        refresh = QPushButton("Wczytaj testy")
        refresh.setAccessibleName("Wczytaj katalog testów tylko do odczytu")
        refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh)
        layout.addLayout(controls)
        self.summary = QLabel("Nie wczytano katalogu. Odczyt następuje na żądanie.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Test", "Cel", "Kategoria", "Stan"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAccessibleName("Katalog testów Jaźni")
        self.table.currentCellChanged.connect(self.show_details)
        layout.addWidget(self.table)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Oczekiwania wybranego testu")
        self.details.setPlaceholderText("Wybierz test, aby przeczytać jego oczekiwania i cel.")
        self.details.setMaximumHeight(145)
        layout.addWidget(self.details)

    def refresh(self, *_unused: object) -> None:
        """Use canonical catalog/reviews API; never infer missing records as passed."""
        self.rows = []
        self.table.setRowCount(0)
        self.details.clear()
        try:
            entries = filtered(
                self.root,
                query=self.query.text(),
                status=str(self.state_filter.currentData() or "all"),
            )
        except (OSError, ValueError, RuntimeError) as error:
            self.summary.setText(
                "Katalog niedostępny — brak potwierdzenia: " + type(error).__name__
            )
            return
        self.rows = entries[:_VISIBLE_ROW_LIMIT]
        self.table.setRowCount(len(self.rows))
        for index, (nodeid, item) in enumerate(self.rows):
            values = (
                str(nodeid),
                str(item.get("purpose") or ""),
                str(item.get("category") or ""),
                str(item.get("status") or "unknown"),
            )
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self.summary.setText(
            f"Znaleziono {len(entries)} testów; pokazano {len(self.rows)}. "
            "Odczyt tylko do wglądu, bez wykonania ani zapisu ocen."
        )
        if self.rows:
            self.table.selectRow(0)

    def show_details(self, row: int, _column: int, *_unused: object) -> None:
        if not (0 <= row < len(self.rows)):
            self.details.clear()
            return
        nodeid, record = self.rows[row]
        self.details.setPlainText(
            f"Test: {nodeid}\n"
            f"Cel: {record.get('purpose') or 'brak opisu'}\n"
            f"Oczekiwane: {record.get('expected') or 'brak kontraktu'}\n"
            f"Stan przeglądu: {record.get('status') or 'unknown'}"
        )
