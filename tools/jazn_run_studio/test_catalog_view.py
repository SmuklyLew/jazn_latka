"""Native Qt test catalogue with explicit, cancellable bulk pytest execution.

Catalogue and reviews are read-only. The existing Test Studio runner owns
the pytest subprocess; TPA retains separate operator/full acceptance authority.
"""
from __future__ import annotations

from pathlib import Path
import queue
import sys

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QProgressBar, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)
from tools.jazn_tests_studio.core import filtered
from tools.jazn_tests_studio.runner import PytestRun

_VISIBLE_ROW_LIMIT = 300
_STATUS_OPTIONS = (
    ("Wszystkie", "all"),
    ("Aktualne", "current"),
    ("Wymaga przeglądu", "review_required"),
    ("Nieaktualne", "obsolete"),
    ("Niezgodne", "incompatible"),
)


class TestCatalogPanel(QWidget):
    """Read-only catalogue and explicit Test Studio bulk test executor."""

    __test__ = False
    open_tpa_requested = Signal()

    def __init__(self, root: Path, parent: QWidget | None = None, *,
                 python: str = "", enable_execution: bool = True) -> None:
        super().__init__(parent)
        self.root = root
        self.python = python or sys.executable
        self.rows: list[tuple[str, dict]] = []
        self.batch: PytestRun | None = None
        self.batch_events: queue.SimpleQueue[dict] = queue.SimpleQueue()
        self.batch_timer = QTimer(self)
        self.batch_timer.timeout.connect(self.poll_batch)
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
        run_controls = QHBoxLayout()
        self.run_all_button = QPushButton("Uruchom WSZYSTKIE aktywne testy (pytest)")
        self.run_all_button.setAccessibleName("Zbiorczy przebieg wszystkich aktywnych testów pytest z trwałymi raportami")
        self.run_all_button.clicked.connect(self.start_batch)
        self.run_all_button.setEnabled(enable_execution)
        run_controls.addWidget(self.run_all_button)
        self.stop_batch_button = QPushButton("Zatrzymaj testy")
        self.stop_batch_button.setEnabled(False)
        self.stop_batch_button.clicked.connect(self.stop_batch)
        run_controls.addWidget(self.stop_batch_button)
        self.tpa_button = QPushButton("Odbiór zbiorczy TPA (22 scenariusze)")
        self.tpa_button.clicked.connect(self.open_tpa_requested.emit)
        run_controls.addWidget(self.tpa_button)
        layout.addLayout(run_controls)
        self.batch_status = QLabel(
            "Testy nieuruchomione. Pełne odbiory TPA, modelu, MCP, Windows i CI "
            "pozostają oddzielne — wynik pytest nigdy ich nie zatwierdza."
        )
        self.batch_status.setWordWrap(True)
        self.batch_status.setAccessibleName("Postęp zbiorczy testów Jaźni")
        layout.addWidget(self.batch_status)
        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 1)
        self.batch_progress.setValue(0)
        layout.addWidget(self.batch_progress)
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

    def start_batch(self) -> None:
        if self.batch is not None and not self.batch.done.is_set():
            raise ValueError("Poprzedni zbiorczy przebieg testów nadal trwa.")
        if QMessageBox.question(
            self, "Zbiorcze testy Jaźni",
            "Uruchomić WSZYSTKIE aktywne testy pytest na wybranym Pythonie? "
            "Testy wykonają się w osobnym procesie. Raporty JUnit i niezmienne "
            "dowody zostaną zapisane poza SYSTEM/MEMORY.\n\n"
            "Zielony wynik pytest NIE zatwierdza odbiorów TPA i CI."
        ) != QMessageBox.StandardButton.Yes:
            return
        # No installed dependencies are changed; user-selected interpreter
        # must be executable by the existing Test Studio subprocess runner.
        self.batch_events = queue.SimpleQueue()
        self.batch_status.setText("Uruchamianie zbiorczego pytest… Pełny odbiór TPA: NOT_RUN.")
        self.batch_progress.setRange(0, 0)
        self.run_all_button.setEnabled(False)
        self.stop_batch_button.setEnabled(True)
        self.batch = PytestRun(
            self.root, timeout=7200, python=self.python, evidence=True,
            on_event=self.batch_events.put,
        ).start()
        self.batch_timer.start(150)

    def stop_batch(self) -> None:
        if self.batch is not None and not self.batch.done.is_set():
            self.batch.stop()
            self.batch_status.setText("Zatrzymywanie własnego procesu testów; brak dowodu pełnego odbioru.")

    def poll_batch(self) -> None:
        if self.batch is None:
            self.batch_timer.stop()
            return
        for _ in range(200):
            try:
                event = self.batch_events.get_nowait()
            except queue.Empty:
                break
            kind = event.get("type")
            if kind == "collection":
                self.batch_progress.setRange(0, max(1, int(event.get("total") or 0)))
            elif kind == "result":
                total = max(1, int(event.get("total") or 0))
                self.batch_progress.setRange(0, total)
                self.batch_progress.setValue(min(total, int(event.get("completed") or 0)))
                self.batch_status.setText(
                    "Pytest: " + str(event.get("completed", 0)) + "/" + str(event.get("total", 0))
                    + " testów • ostatni wynik " + str(event.get("status", "UNKNOWN"))
                    + ". Pełne TPA/CI: NOT_RUN."
                )
        if not self.batch.done.is_set():
            return
        result = self.batch.result or {}
        self.batch_timer.stop()
        self.run_all_button.setEnabled(True)
        self.stop_batch_button.setEnabled(False)
        counts = result.get("counts", {})
        status = "PASS" if result.get("ok") is True else str(result.get("outcome") or "ERROR").upper()
        self.batch_status.setText(
            f"Pytest: {status}; wykonano {result.get('completed', 0)}/{result.get('total', 0)}, "
            f"FAILED={counts.get('FAILED', 0)}, ERROR={counts.get('ERROR', 0)}, "
            f"SKIPPED={counts.get('SKIPPED', 0)}.\n"
            "Dowody: " + str(result.get("evidence_dir") or "NIEZAPISANE") + "\n"
            "Pełny odbiór TPA/Windows/Ollama/MCP/CI: NOT_RUN — osobna walidacja."
        )

    def shutdown(self) -> bool:
        """Do not abandon a child pytest process during JSS window teardown."""
        if self.batch is not None and not self.batch.done.is_set():
            self.batch.stop()
            return False
        self.batch_timer.stop()
        return True

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
