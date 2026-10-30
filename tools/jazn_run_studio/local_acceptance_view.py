"""Qt interface for operator-run acceptance tests with local-only durable evidence."""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import local_acceptance as store
from .tpa_runner import AUTOMATED_CASES, SafeTPARunner

STATES = (("PASS — operator potwierdził", "passed"),
          ("FAIL — problem", "failed"), ("BLOKADA — nie da się wykonać", "blocked"))


class LegacyAcceptanceNotes(QWidget):
    """Operator acceptance with isolated optional regression subchecks."""

    def __init__(self, root: Path, parent: QWidget | None = None, *, python: str = "") -> None:
        super().__init__(parent)
        self.root = root
        self.data: dict = {}
        self.digest: str | None = None
        self.rows: list[dict[str, str]] = []
        interpreter = python or ("" if getattr(sys, "frozen", False) else sys.executable)
        self.runner = SafeTPARunner(root, interpreter, self)
        self.runner.progress.connect(self._auto_progress)
        self.runner.completed.connect(self._auto_completed)
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Test lokalny", "Kategoria", "Stan w tej wersji"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAccessibleName("TPA — testy przepuszczania aktualizacji Jaźni")
        self.table.currentCellChanged.connect(self.selected)
        layout.addWidget(self.table)
        self.instructions = QPlainTextEdit()
        self.instructions.setReadOnly(True)
        self.instructions.setMaximumHeight(160)
        self.instructions.setAccessibleName("Kroki i kryteria lokalnego testu")
        layout.addWidget(self.instructions)
        auto_row = QHBoxLayout()
        self.auto_one = QPushButton("Uruchom podtest zaznaczonego")
        self.auto_one.setAccessibleName("Uruchom bezpieczny podtest wybranego scenariusza TPA")
        self.auto_one.clicked.connect(self.run_selected_subcheck)
        auto_row.addWidget(self.auto_one)
        self.auto_safe = QPushButton("Uruchom bezpieczne podtesty")
        self.auto_safe.clicked.connect(self.run_safe_subchecks)
        auto_row.addWidget(self.auto_safe)
        self.auto_cancel = QPushButton("Anuluj podtest")
        self.auto_cancel.setEnabled(False)
        self.auto_cancel.clicked.connect(self.runner.stop)
        layout.addLayout(auto_row)
        layout.addWidget(self.auto_cancel)
        self.auto_status = QLabel(
            "TPA: testy automatyczne sprawdzają wybrane regresje, ale nigdy "
            "nie zatwierdzają 22 bramek odbioru ręcznego."
        )
        self.auto_status.setWordWrap(True)
        layout.addWidget(self.auto_status)
        self.auto_log = QPlainTextEdit()
        self.auto_log.setReadOnly(True)
        self.auto_log.setMaximumHeight(120)
        self.auto_log.document().setMaximumBlockCount(600)
        self.auto_log.setAccessibleName("Dziennik izolowanych podtestów TPA")
        layout.addWidget(self.auto_log)
        form = QFormLayout()
        self.state = QComboBox()
        for title, key in STATES:
            self.state.addItem(title, key)
        self.state.setAccessibleName("Rzeczywisty ręczny wynik testu")
        form.addRow("Wynik:", self.state)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Co sprawdzono? Podaj wersję, port i rzeczywisty rezultat. Nie wklejaj sekretów.")
        self.note.setMaximumHeight(95)
        self.note.setAccessibleName("Lokalna notatka testu")
        form.addRow("Notatka:", self.note)
        self.evidence = QLineEdit()
        self.evidence.setMaxLength(800)
        self.evidence.setPlaceholderText("Identyfikator raportu lub lokalna ścieżka; bez sekretów i surowych logów")
        self.evidence.setAccessibleName("Odniesienie do lokalnego dowodu")
        form.addRow("Dowód:", self.evidence)
        layout.addLayout(form)
        row = QHBoxLayout()
        self._button(row, "Zapisz wynik", self.save)
        self._button(row, "Archiwizuj zaliczony", self.archive)
        self._button(row, "Odśwież", self.refresh)
        layout.addLayout(row)
        self.archived = QLabel()
        self.archived.setWordWrap(True)
        layout.addWidget(self.archived)
        custom = QFormLayout()
        self.custom_title = QLineEdit()
        self.custom_title.setMaxLength(160)
        self.custom_steps = QPlainTextEdit()
        self.custom_steps.setMaximumHeight(90)
        self.custom_expected = QPlainTextEdit()
        self.custom_expected.setMaximumHeight(75)
        custom.addRow("Nowy test (tytuł):", self.custom_title)
        custom.addRow("Kroki testu:", self.custom_steps)
        custom.addRow("Oczekiwany wynik:", self.custom_expected)
        layout.addLayout(custom)
        self._button(layout, "Dodaj test do lokalnej kolejki", self.add)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.refresh()

    def _button(self, parent: QHBoxLayout | QVBoxLayout, caption: str, fn) -> None:
        btn = QPushButton(caption)
        btn.clicked.connect(lambda checked=False: self._attempt(fn))
        btn.setAccessibleName(caption)
        parent.addWidget(btn)

    def _attempt(self, fn) -> None:
        try:
            fn()
            self.feedback.setText("Operacja zapisana wyłącznie lokalnie.")
        except (OSError, ValueError) as exc:
            self.feedback.setText("Błąd: " + str(exc))

    def run_selected_subcheck(self) -> None:
        case_id = self._chosen()
        if case_id not in AUTOMATED_CASES:
            self.auto_status.setText(
                "TPA: ten scenariusz wymaga wykonania instrukcji przez operatora. "
                "Nie uruchomiono testu ani nie nadano PASS."
            )
            return
        self._start_automatic((case_id,))

    def run_safe_subchecks(self) -> None:
        self._start_automatic(tuple(AUTOMATED_CASES))

    def _start_automatic(self, case_ids: tuple[str, ...]) -> None:
        try:
            self.runner.start_cases(case_ids)
        except (OSError, ValueError) as exc:
            self.auto_status.setText("TPA: BLOKADA • " + str(exc))
            return
        self.auto_one.setEnabled(False)
        self.auto_safe.setEnabled(False)
        self.auto_cancel.setEnabled(True)
        self.auto_status.setText("TPA: PRACUJE • izolowany proces testowy; bramki ręczne bez zmian.")

    def _auto_progress(self, line: str) -> None:
        self.auto_log.appendPlainText(line.rstrip())

    def _auto_completed(self, report: object) -> None:
        if not isinstance(report, dict):
            return
        self.auto_one.setEnabled(True)
        self.auto_safe.setEnabled(True)
        self.auto_cancel.setEnabled(False)
        status = str(report.get("status") or "BLOCKED")
        path = str(report.get("evidence_path") or "nie zapisano")
        self.auto_status.setText(
            "TPA: " + status + " • podtest regresyjny, a NIE pełny odbiór. "
            "Dowód: " + path
        )
        if report.get("persistence_error"):
            self.auto_log.appendPlainText(
                "BŁĄD: dowód nie został zapisany; nie wolno zakładać trwałości wyniku."
            )

    def closeEvent(self, event) -> None:
        if self.runner.active:
            self.runner.stop()
        super().closeEvent(event)

    def refresh(self) -> None:
        self.data, self.digest = store.load(self.root)
        self.rows = store.catalog(self.root, self.data)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        version = store.scope_version(self.root)
        for i, test in enumerate(self.rows):
            current = store.outcome(self.data, test["id"], version)
            status = ("Archiwum" if current and current.get("archived") else
                      current["status"].upper() if current else "DO WYKONANIA")
            for j, val in enumerate((test["id"], test["title"], test["category"], status)):
                self.table.setItem(i, j, QTableWidgetItem(val))
        self.table.blockSignals(False)
        done = sum(bool(store.outcome(self.data, x["id"], version)) for x in self.rows)
        self.summary.setText(
            f"Wersja: {version}  •  {done}/{len(self.rows)} zarejestrowanych wyników. "
            "Ręczny PASS nie jest dowodem CI; PASS podtestu nie zalicza odbioru. "
            "Po zmianie wersji wyniki wracają do kolejki."
        )
        self.archived.setText(
            f"Archiwum (wszystkie wersje): {len(self.data['archive'])} wyników. "
            "Dane przechowywane wyłącznie lokalnie, poza Git i MEMORY."
        )
        if self.rows:
            self.table.selectRow(0)
            self.selected(0, 0, -1, -1)

    def selected(self, row: int, _col: int, _oldrow: int, _oldcol: int) -> None:
        if not 0 <= row < len(self.rows):
            return
        test = self.rows[row]
        self.instructions.setPlainText(
            "CEL: " + test["title"] + "\n\nKROKI:\n" + test["steps"] +
            "\n\nOCZEKIWANY WYNIK:\n" + test["expected"]
        )
        if test["id"] in AUTOMATED_CASES:
            self.auto_status.setText(
                "TPA: dostępny bezpieczny podtest regresyjny (częściowe pokrycie). "
                "Pełny odbiór wymaga rzeczywistego potwierdzenia przez operatora."
            )
        elif not self.runner.active:
            self.auto_status.setText(
                "TPA: tylko ręcznie / brak zatwierdzonego wykonawcy automatycznego. "
                "Nie uruchomiono żadnej operacji."
            )
        state = store.outcome(self.data, test["id"], store.scope_version(self.root))
        self.note.setPlainText(str(state.get("note", "")) if state else "")
        self.evidence.setText(str(state.get("evidence", "")) if state else "")
        idx = self.state.findData(state.get("status")) if state else 0
        self.state.setCurrentIndex(max(0, idx))

    def _chosen(self) -> str:
        row = self.table.currentRow()
        if not 0 <= row < len(self.rows):
            raise ValueError("Najpierw wybierz test")
        return self.rows[row]["id"]

    def save(self) -> None:
        selected = self._chosen()
        self.digest = store.save_result(
            self.root, self.digest, selected, str(self.state.currentData()),
            self.note.toPlainText(), self.evidence.text()
        )
        self.refresh()

    def archive(self) -> None:
        self.digest = store.archive_result(self.root, self.digest, self._chosen())
        self.refresh()

    def add(self) -> None:
        self.digest = store.add_custom(
            self.root, self.digest, self.custom_title.text(),
            self.custom_steps.toPlainText(), self.custom_expected.toPlainText()
        )
        self.custom_title.clear()
        self.custom_steps.clear()
        self.custom_expected.clear()
        self.refresh()


# Public import remains compatible. The historical notes widget is retained for
# readers of old operator records; the application uses the executable workbench.
from .tpa_view import TPAPanel as LocalAcceptancePanel
