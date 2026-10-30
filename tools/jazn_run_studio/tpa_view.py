"""Operational TPA queue, guided acceptance and run-owned evidence."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
import sys
import time
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QGridLayout,
    QHeaderView, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)
from . import local_acceptance as legacy
from .tpa_catalog import LIVE_CASES, MODES, execution_map
from .tpa_engine import TPARunner
from .tpa_plan_runner import TPAPlanRunner
from .tpa_execution_plan import plan_counts
from .tpa_guidance import attach_evidence, record_observation
from .tpa_current_state import current_state
from .tpa_reports import STATES, TERMINAL, readable_report, safe_child, source_identity, summary
from .tpa_triage import TRIAGE_LABELS, triage_cases, local_queue_text, NOWE, DO_POWTORZENIA, NIEAKTUALNE, ZALICZONE


class TPAPanel(QWidget):
    dependency_requested = Signal()
    models_requested = Signal()

    def __init__(self, root: Path, parent: QWidget | None = None, *, python: str = ""):
        super().__init__(parent)
        self.root, self.rows = root.resolve(), execution_map()
        self.report: dict | None = None
        self._history: list[dict] = []
        self.case_state: dict = {}
        self.history_mode = False
        self.pending_observation: dict | None = None
        self.triage: dict[str, dict[str, str]] = {}
        self.attached: dict[str, list[str]] = {}
        self.guide_drafts: dict[tuple[str, str], dict] = {}
        self._guide_key = ("", "")
        self._log_selection: tuple[str, str] | None = None
        self._guide_id, self._started = "", 0.0
        self.runner = TPARunner(root, python or ("" if getattr(sys, "frozen", False) else sys.executable), self)
        self.runner.progress.connect(self._progress)
        self.runner.changed.connect(self.refresh_view)
        self.runner.prepared.connect(self._prepared)
        self.runner.completed.connect(self._completed)
        self.plan_runner = TPAPlanRunner(self.runner, self)
        self.plan_runner.changed.connect(self.plan_changed)
        self.plan_runner.completed.connect(self.plan_completed)
        self.plan_runner.error.connect(lambda text: self.feedback.setText(text))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.summary = QLabel("TPA — nie sprawdzono środowiska")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.setup_details = QWidget()
        setup = QGridLayout(self.setup_details)
        setup.setContentsMargins(0, 0, 0, 0)
        self.python_field = QLineEdit(self.runner.python)
        self.python_field.setAccessibleName("Interpreter testów TPA")
        setup.addWidget(self.python_field, 0, 0, 1, 3)
        self.choose_python = self.button("Wybierz Python…", self.pick_python)
        setup.addWidget(self.choose_python, 0, 3)
        self.check_button = self.button("Sprawdź gotowość", self.check_ready)
        self.dependencies_button = self.button("Studio Zależności", self.dependency_requested.emit)
        ready_bar = QHBoxLayout()
        self.setup_toggle = QPushButton("Środowisko i model…")
        self.setup_toggle.setCheckable(True)
        self.setup_toggle.setAccessibleName("Rozwiń wybór Pythona i modelu TPA")
        self.setup_toggle.toggled.connect(self.setup_details.setVisible)
        for widget in (self.check_button, self.setup_toggle, self.dependencies_button):
            ready_bar.addWidget(widget)
        layout.addLayout(ready_bar)
        self.model = QComboBox()
        self.model.setEditable(False)
        self.model.setAccessibleName("Zainstalowany model Ollama do odbioru TPA")
        self.model.addItem("Wykryj zainstalowane modele…", "")
        self.refresh_models_button = self.button("Wykryj modele", self.models_requested.emit)
        setup.addWidget(QLabel("Model Ollama"), 1, 0)
        setup.addWidget(self.model, 1, 1, 1, 2)
        setup.addWidget(self.refresh_models_button, 1, 3)
        setup.setColumnStretch(2, 1)
        self.source_kind = QComboBox()
        for label, key in (("origin/master (domyślnie)", "master"), ("Branch", "branch"),
                           ("Pull Request", "pr"), ("Próbne scalenie PR", "merge"),
                           ("Lokalny SYSTEM", "local"), ("Zweryfikowany SYSTEM ZIP", "zip")):
            self.source_kind.addItem(label, key)
        if not (self.root / ".git").exists():
            self.source_kind.setCurrentIndex(self.source_kind.findData("local"))
        self.source_kind.setAccessibleName("Źródło testów TPA")
        self.source_value = QLineEdit()
        self.source_value.setPlaceholderText("Branch, numer PR lub absolutna ścieżka SYSTEM/ZIP")
        self.source_value.setAccessibleName("Identyfikator źródła testów TPA")
        setup.addWidget(self.source_kind, 2, 0, 1, 2)
        setup.addWidget(self.source_value, 2, 2, 1, 2)
        layout.addWidget(self.setup_details)
        self.setup_details.hide()
        filters = QGridLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Szukaj nazwy, identyfikatora lub przyczyny…")
        self.search.setAccessibleName("Filtr nazwy TPA")
        filters.addWidget(self.search, 0, 0, 1, 4)
        self.category, self.mode_filter, self.result_filter, self.triage_filter = QComboBox(), QComboBox(), QComboBox(), QComboBox()
        for col, (widget, title) in enumerate(((self.category, "Kategoria"), (self.mode_filter, "Tryb"), (self.result_filter, "Wynik"), (self.triage_filter, "Odbiór lokalny"))):
            widget.addItem(title + ": wszystkie", "")
            widget.setAccessibleName("Filtr TPA: " + title)
            widget.setMinimumWidth(60)
            widget.currentIndexChanged.connect(self.apply_filters)
            filters.addWidget(widget, 1, col)
        for category in sorted({r["category"] for r in self.rows}):
            self.category.addItem(category, category)
        for key, label in MODES.items():
            self.mode_filter.addItem(label, key)
        for state in STATES:
            self.result_filter.addItem(state, state)
        for key, label in TRIAGE_LABELS.items():
            self.triage_filter.addItem(label, key)
        self.search.textChanged.connect(self.apply_filters)
        layout.addLayout(filters)
        actions = QGridLayout()
        self.auto_one = self.button("Uruchom zaznaczone", self.run_selected_subcheck)
        self.auto_safe = self.button("Uruchom plan automatyczny", self.run_automatic_plan)
        self.retry_button = self.button("Ponów nieudane / blokady", self.retry_failed)
        self.auto_cancel = self.button("Zatrzymaj", self.stop_work)
        for i, widget in enumerate((self.auto_one, self.auto_safe, self.retry_button, self.auto_cancel)):
            actions.addWidget(widget, i // 2, i % 2)
        layout.addLayout(actions)
        self.auto_status = QLabel("PASS podtestu potwierdza zakres regresji. Pełny odbiór ma osobny wynik.")
        self.auto_status.setWordWrap(True)
        self.auto_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.auto_status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("%v / %m pozycji")
        layout.addWidget(self.progress)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(len(self.rows), 7)
        self.table.setHorizontalHeaderLabels(["Scenariusz", "Regresja", "Live", "Pełny odbiór", "Aktualność", "Ostatnia próba", "Następny krok"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAccessibleName("Kolejka 22 scenariuszy TPA; zaznacz wiersze lub pola wyboru")
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.setMinimumSize(0, 170)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(45)
        for col in (0, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 75), (2, 75), (3, 85), (4, 95), (5, 110)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, width)
        self.table.verticalHeader().hide()
        for i, case in enumerate(self.rows):
            for col, text in enumerate((case["title"], "NOT_RUN", "NOT_RUN", "NOT_RUN", "Nie ustalono", "—", "Nie sprawdzono gotowości.")):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, case["id"])
                if col == 0:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                self.table.setItem(i, col, item)
        self.table.currentCellChanged.connect(self.selected)
        self.splitter.addWidget(self.table)
        self.tabs = QTabWidget()
        self.instructions = self.text_view("Szczegóły scenariusza")
        self.tabs.addTab(self.instructions, "Szczegóły")
        self.auto_log = self.text_view("Log i zaakceptowane odpowiedzi testowe")
        self.tabs.addTab(self.auto_log, "Przebieg / log")
        self._guide()
        self.report_view = self.text_view("Czytelny raport TPA")
        self.tabs.addTab(self.report_view, "Raport")
        self.technical = self.text_view("Dane techniczne i starsze wyniki")
        self.tabs.addTab(self.technical, "Techniczne")
        self.local_gates_view = self.text_view("Nowe, do powtórzenia i nieaktualne odbiory lokalne")
        self.tabs.addTab(self.local_gates_view, "Odbiory lokalne")
        plan_page = QWidget()
        self.plan_page = plan_page
        plan_layout = QVBoxLayout(plan_page)
        self.plan_history = QComboBox()
        self.plan_history.setAccessibleName("Historia planów TPA")
        plan_layout.addWidget(self.plan_history)
        plan_actions = QHBoxLayout()
        self.resume_plan_button = self.button("Kontynuuj przerwany plan", self.resume_plan)
        self.checkpoint_button = self.button("Zapisz checkpoint", self.plan_runner.checkpoint)
        self.plan_history.currentIndexChanged.connect(self.update_controls)
        for button in (self.resume_plan_button, self.checkpoint_button):
            plan_actions.addWidget(button)
        plan_layout.addLayout(plan_actions)
        self.plan_details = self.text_view("Zależności, blokady i checkpoint planu TPA")
        plan_layout.addWidget(self.plan_details)
        self.tabs.addTab(plan_page, "Plany i checkpointy")
        self.tabs.setMinimumHeight(180)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter, 1)
        history_row = QHBoxLayout()
        self.history = QComboBox()
        self.history.setMinimumWidth(80)
        self.history.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.history.setAccessibleName("Historia TPA")
        self.history.currentIndexChanged.connect(self.load_history)
        history_row.addWidget(self.history, 1)
        history_row.addWidget(self.button("Aktualny stan 22 scenariuszy", self.show_current))
        history_row.addWidget(self.button("Odśwież", self.refresh))
        history_row.addWidget(self.button("Odzyskaj raport", self.recover_selected_report))
        history_row.addWidget(self.button("Starsze wyniki", self.show_legacy))
        layout.addLayout(history_row)
        exports = QHBoxLayout()
        self.log_button = self.button("Pokaż log", self.show_log)
        self.report_button = self.button("Otwórz raport", self.open_report)
        self.export_button = self.button("Eksportuj raport ZIP…", self.export_report)
        for button in (self.log_button, self.report_button, self.export_button):
            exports.addWidget(button)
        layout.addLayout(exports)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.feedback)
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self.update_progress)
        self.elapsed_timer.start(250)
        self.attempt(self.runner.store.recover_interrupted)
        self.attempt(self.refresh)
        self.table.selectRow(0)
        self.table.itemSelectionChanged.connect(self.update_controls)
        self.table.itemChanged.connect(self.update_controls)
        self.row_timer = QTimer(self)
        self.row_timer.setSingleShot(True)
        self.row_timer.timeout.connect(self.table.resizeRowsToContents)
        self.refresh_view()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "row_timer"):
            self.row_timer.start(0)

    @staticmethod
    def text_view(name: str) -> QPlainTextEdit:
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        view.setAccessibleName(name)
        return view

    def cell(self, row: int, column: int) -> QTableWidgetItem:
        item = self.table.item(row, column)
        if item is None:
            raise ValueError("Niepełny wiersz tabeli TPA")
        return item

    def button(self, title: str, action) -> QPushButton:
        button = QPushButton(title)
        button.setAccessibleName(title)
        button.clicked.connect(lambda _checked=False: self.attempt(action))
        return button

    def attempt(self, action) -> None:
        try:
            action()
        except (OSError, ValueError, RuntimeError) as exc:
            self.feedback.setText("Operacja niedostępna: " + self.runner.redactor.text(str(exc)))

    def _guide(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.live_button = self.button("Wykonaj odbiór izolowany", lambda: self.start((self.chosen(),), "live"))
        self.sandbox_button = self.button("Otwórz izolowane Studio", lambda: self.start((self.chosen(),), "sandbox"))
        row.addWidget(self.live_button)
        row.addWidget(self.sandbox_button)
        layout.addLayout(row)
        self.checklist = QListWidget()
        self.checklist.setWordWrap(True)
        self.checklist.setAccessibleName("Kroki odbioru wspomaganego")
        layout.addWidget(self.checklist, 1)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Co zaobserwowano? Bez dowodu wpisz: nie ustalono i wskaż potrzebne sprawdzenie.")
        self.note.setMaximumHeight(85)
        layout.addWidget(self.note)
        row = QHBoxLayout()
        self.state = QComboBox()
        for label, value in (("BLOCKED — brak warunków", "BLOCKED"), ("FAIL — problem", "FAIL"), ("PASS — kryteria spełnione", "PASS")):
            self.state.addItem(label, value)
        row.addWidget(self.state)
        self.proof_button = self.button("Dołącz dowód…", self.attach_proof)
        self.observe_button = self.button("Zapisz odbiór z dowodami", self.save)
        row.addWidget(self.proof_button)
        row.addWidget(self.observe_button)
        layout.addLayout(row)
        self.tabs.addTab(page, "Odbiór wspomagany")

    def set_installed_models(self, names: object, preferred: str = "") -> None:
        """Populate TPA choices only from the observed local Ollama model list."""
        previous = self.model.currentData()
        installed = sorted({name for name in names if isinstance(name, str) and name.strip()}) if isinstance(names, list) else []
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItem("Wybierz zainstalowany model…" if installed else "Brak modeli / Ollama niedostępna", "")
        for name in installed:
            self.model.addItem(name, name)
        index = self.model.findData(previous or preferred)
        self.model.setCurrentIndex(index if index >= 0 else 0)
        self.model.blockSignals(False)
        self.model.setToolTip("Lista modeli z lokalnego API Ollama; bez pobierania i bez ręcznego wpisywania.")

    @staticmethod
    def full_gate_description(value: str) -> str:
        if value == "NOT_RUN":
            return "NOT_RUN — osobny pełny odbiór operatorski nie został wykonany (test izolowany może mieć PASS)"
        return value or "NOT_RUN — osobny pełny odbiór operatorski nie został wykonany"

    def selected_ids(self) -> tuple[str, ...]:
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        rows.update(i for i in range(self.table.rowCount()) if self.cell(i, 0).checkState() == Qt.CheckState.Checked)
        return tuple(self.rows[i]["id"] for i in sorted(rows) if not self.table.isRowHidden(i))

    def chosen(self) -> str:
        row = self.table.currentRow()
        if not 0 <= row < len(self.rows) or self.table.isRowHidden(row):
            raise ValueError("Wybierz widoczny scenariusz TPA")
        return self.rows[row]["id"]

    def pick_python(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Interpreter testów", self.python_field.text())
        if name:
            self.python_field.setText(name)
            self.runner.availability.clear()
            self.runner.probe.clear()
            self.refresh_view()

    def check_ready(self) -> None:
        self.runner.python = self.python_field.text().strip()
        self._started = time.monotonic()
        self.runner.check_ready()
        self.update_controls()

    def start(self, ids: tuple[str, ...], execution: str = "regression") -> None:
        if not ids:
            raise ValueError("Zaznacz co najmniej jeden widoczny scenariusz")
        self.runner.python = self.python_field.text().strip()
        self._started = time.monotonic()
        self.auto_log.clear()
        self._log_selection = None
        selected_model = self.model.currentData() or ""
        if execution == "live" and any(case in LIVE_CASES for case in ids) and not selected_model:
            raise ValueError("Najpierw kliknij Wykryj modele Ollama i wybierz zainstalowany model z listy.")
        # Public Studio launchers verify a real checkout/export. Keep the
        # existing direct panel API usable by unpackaged synthetic fixtures.
        packaged = (self.root / ".git").exists() or (self.root / "PACKAGE_INTEGRITY_MANIFEST.json").is_file()
        self.runner.start_selection(ids, execution=execution, model=selected_model,
                                    source_kind=str(self.source_kind.currentData()) if packaged else None,
                                    source_value=self.source_value.text().strip())
        self.history_mode = False
        self.attached.clear()
        if execution != "regression":
            self.tabs.setCurrentWidget(self.auto_log)
        self.report = self.runner.report
        self.refresh_view()

    def run_selected_subcheck(self) -> None:
        self.start(self.selected_ids())

    def run_safe_subchecks(self) -> None:
        self.start(tuple(r["id"] for r in self.rows))

    def run_automatic_plan(self) -> None:
        self.runner.python = self.python_field.text().strip()
        self.history_mode = False
        self.plan_runner.start(tuple(r["id"] for r in self.rows),
            source={"kind": self.source_kind.currentData(), "value": self.source_value.text().strip()},
            model=self.model.currentData() or "")
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.plan_page))
        self.plan_changed()

    def stop_work(self) -> None:
        if self.plan_runner.active:
            self.plan_runner.stop()
        else:
            self.runner.stop()

    def resume_plan(self) -> None:
        plan_id = self.plan_history.currentData()
        if not plan_id:
            raise ValueError("Wybierz zapisany, niezakończony plan")
        self.plan_runner.resume(str(plan_id))

    def plan_changed(self) -> None:
        plan = self.plan_runner.plan
        if plan is not None:
            self.plan_details.setPlainText("Plan " + plan["plan_id"] + "\n" + str(plan_counts(plan))
                + "\nPełne odbiory operatorskie są oddzielne. Przerwana tura nie jest wysyłana ponownie.\n\n"
                + json.dumps(plan, ensure_ascii=False, indent=2))
        self.update_controls()

    def plan_completed(self, plan: object) -> None:
        if isinstance(plan, dict):
            self.feedback.setText("Zapisano wykonanie planu: " + str(plan_counts(plan)) + ". Pełny odbiór operatorski pozostaje oddzielny.")
        self.refresh()

    def retry_failed(self) -> None:
        if not self.report:
            raise ValueError("Wybierz przebieg w historii")
        ids = tuple(r["case_id"] for r in self.report["results"] if r["status"] in {"FAIL", "BLOCKED", "TIMEOUT", "INTERRUPTED", "CANCELLED", "SKIPPED"})
        self.start(ids, self.report.get("execution", "regression"))

    def _prepared(self, probe: object) -> None:
        self.technical.setPlainText(json.dumps(probe, ensure_ascii=False, indent=2))
        if self.pending_observation is not None:
            pending, self.pending_observation = self.pending_observation, None
            if isinstance(probe, dict) and probe.get("ok") is True:
                self.attempt(lambda: self.finish_observation(pending, probe.get("source", {})))
            else:
                self.feedback.setText("Nie zapisano odbioru: brak potwierdzonej tożsamości źródła.")
        self.refresh_view()

    def _progress(self, text: str) -> None:
        current = self.runner.report
        running = next((r["case_id"] for r in current["results"] if r["status"] == "RUNNING"), "") if current else ""
        key = (current["run_id"], running) if current else ("", "")
        if text.startswith("Zaakceptowana odpowiedź testowa:") and self._log_selection not in {None, key}:
            self.auto_log.clear()
            self._log_selection = key
        if self._log_selection is not None and self._log_selection != key:
            return  # A selected completed test must not receive another test's output.
        self.auto_log.appendPlainText(self.runner.redactor.text(text))
        if text.startswith("Zaakceptowana odpowiedź testowa:"):
            self.tabs.setCurrentWidget(self.auto_log)

    def _completed(self, report: object) -> None:
        if isinstance(report, dict):
            self.report = report
            if report.get("persistence_error"):
                self.feedback.setText(report["persistence_error"])
        self.refresh()

    def refresh_view(self) -> None:
        if self.runner.active and self.runner.report is not None and self.runner._next_after_probe:
            self.report = self.runner.report
        results = {r["case_id"]: r for r in self.report["results"]} if self.report else {}
        current = source_identity(self.root)
        current.update(self.runner.probe.get("source", {}))
        history = list(self._history)
        if self.runner.report is not None and ((self.runner.active and self.runner._next_after_probe)
                or not any(r["run_id"] == self.runner.report["run_id"] for r in history)):
            history = [r for r in history if r["run_id"] != self.runner.report["run_id"]]
            history.append(self.runner.report)
        self.case_state = current_state(self.runner.store, current, history)
        for i, case in enumerate(self.rows):
            result = results.get(case["id"], {})
            projection = self.case_state[case["id"]]
            latest = projection["last_attempt"]
            if not self.history_mode:
                result = latest["row"] if latest else {}
            state = result.get("status", "NOT_RUN")
            reason = result.get("reason") or self.runner.availability.get(case["id"], {}).get("reason") or "Użyj Sprawdź gotowość."
            channel = self.report.get("execution", "regression") if self.report else "regression"
            values = [state if channel == "regression" else "NOT_RUN",
                      state if channel == "live" else "NOT_RUN", result.get("full_gate", "NOT_RUN")]
            relation = "uncertain"
            if self.history_mode and self.report:
                from .tpa_triage import _source_relation
                relation = _source_relation(self.report["source"], current)
            elif not self.history_mode:
                values = [projection[k]["status"] if projection[k] else "NOT_RUN" for k in ("regression", "live", "full")]
                relations = [projection[k]["source_relation"] for k in ("regression", "live", "full") if projection[k]]
                relation = "stale" if "stale" in relations else "uncertain" if not relations or "uncertain" in relations else "same"
                if latest and latest["evidence_errors"]:
                    reason = " ".join(latest["evidence_errors"])
            freshness = {"same": "Aktualne", "stale": "Nieaktualne", "uncertain": "Nie ustalono"}[relation]
            last_time = (latest["time"] if latest and not self.history_mode else result.get("finished_utc", "")) or "—"
            for col, text in enumerate([*values, freshness, last_time[:19], reason], 1):
                self.cell(i, col).setText(text)
                self.cell(i, col).setToolTip("Wynik scenariusza: " + state + "\n" + reason + "\nPełny odbiór: " + self.full_gate_description(result.get("full_gate", "NOT_RUN")))
            full = projection["full"]
            triage_state = (NOWE if latest is None else NIEAKTUALNE if relation == "stale" else
                            ZALICZONE if latest["status"] == "PASS" and full and full["status"] == "PASS" and full["source_relation"] == "same" else DO_POWTORZENIA)
            triage = {"state": triage_state, "reason": " ".join(full["evidence_errors"]) if full and full["evidence_errors"] else reason}
            self.triage[case["id"]] = triage
            self.cell(i, 0).setToolTip(case["title"] + "\nID: " + case["id"] + "\nOdbiór: " + TRIAGE_LABELS[triage["state"]] + "\n" + triage["reason"])
        ready = sum(v["ready"] for v in self.runner.availability.values())
        counters = summary(self.report)["counts"] if self.report else {}
        if not self.history_mode:
            counters = dict(Counter(s["last_attempt"]["status"] if s["last_attempt"] else "NOT_RUN" for s in self.case_state.values()))
        scope = " • historia: " + self.report["source"]["version"] if self.report and self.report["source"]["version"] != legacy.scope_version(self.root) else ""
        selected_python = self.runner.probe.get("python") or self.python_field.text()
        python_label = " / ".join(Path(selected_python).parts[-3:]) if selected_python else "nie wybrano"
        self.summary.setToolTip("Interpreter: " + (selected_python or "nie wybrano") + "\nRaporty: " + str(self.runner.store.base))
        view_label = "TPA — historia" if self.history_mode else "TPA — stan zbiorczy"
        self.summary.setText(view_label + " • SYSTEM " + legacy.scope_version(self.root).split("-", 1)[0] + scope + "\nPython: " + python_label
                             + f" • gotowe podtesty: {ready}/22 • MEMORY: off\n" + " | ".join(f"{k}: {v}" for k, v in counters.items()))
        self.apply_filters()
        self.local_gates_view.setPlainText(local_queue_text(self.triage))
        self.table.resizeRowsToContents()
        self.selected(self.table.currentRow(), 0, -1, -1)
        self.update_controls()
        self.update_progress()

    def update_controls(self) -> None:
        active = self.runner.active or self.plan_runner.active
        for button in (self.auto_one, self.auto_safe, self.check_button, self.retry_button, self.live_button, self.sandbox_button):
            button.setEnabled(not active)
            button.setToolTip("Poczekaj na zakończenie przebiegu lub użyj Zatrzymaj." if active else "")
        self.auto_one.setEnabled(not active and bool(self.selected_ids()))
        if not self.selected_ids():
            self.auto_one.setToolTip("Zaznacz co najmniej jeden widoczny scenariusz.")
        self.retry_button.setEnabled(not active and self.report is not None and any(r["status"] in {"FAIL", "BLOCKED", "TIMEOUT", "INTERRUPTED", "CANCELLED", "SKIPPED"} for r in self.report["results"]))
        if not self.retry_button.isEnabled() and not active:
            self.retry_button.setToolTip("Brak nieudanych, pominiętych lub zablokowanych pozycji w wybranym przebiegu.")
        self.auto_cancel.setEnabled(active)
        self.resume_plan_button.setEnabled(not active and bool(self.plan_history.currentData()))
        self.checkpoint_button.setEnabled(self.plan_runner.plan is not None)
        for widget in (self.python_field, self.choose_python, self.history, self.model, self.refresh_models_button, self.source_kind, self.source_value):
            widget.setEnabled(not active)
        for button in (self.export_button, self.report_button, self.proof_button, self.observe_button):
            button.setEnabled(not active and self.report is not None and bool(self.report.get("finished_utc")))
        try:
            live = self.chosen() in LIVE_CASES
        except ValueError:
            live = False
        self.live_button.setEnabled(not active and live)
        self.live_button.setToolTip("Rzeczywiste kroki na własnym daemonie; tury wymagają modelu." if live else "Dostępny podtest i prowadzony odbiór w izolowanym Studio.")

    def update_progress(self) -> None:
        rows = self.report["results"] if self.report else []
        done = sum(r["status"] in TERMINAL for r in rows)
        self.progress.setRange(0, max(1, len(rows)))
        self.progress.setValue(done)
        if self.runner.active:
            current = next((r["title"] for r in rows if r["status"] == "RUNNING"), "Kontrola gotowości")
            self.auto_status.setText(f"{current} • {max(0, int(time.monotonic() - self._started))} s • zakończono {done}/{len(rows)}")
        elif self.report:
            self.auto_status.setText(f"Zakończono {done}/{len(rows)} pozycji • {self.report['run_id']} • pełny odbiór osobno.")

    def apply_filters(self, *_args) -> None:
        if not hasattr(self, "table"):
            return
        query = self.search.text().casefold().strip()
        for i, case in enumerate(self.rows):
            text = " ".join((case["id"], case["title"], self.cell(i, 6).text())).casefold()
            visible = (not query or query in text) and (not self.category.currentData() or self.category.currentData() == case["category"])
            visible = visible and (not self.mode_filter.currentData() or self.mode_filter.currentData() == case["mode"])
            visible = visible and (not self.result_filter.currentData() or self.result_filter.currentData() in {self.cell(i, col).text() for col in (1, 2, 3)})
            visible = visible and (not self.triage_filter.currentData() or self.triage_filter.currentData() == self.triage.get(case["id"], {}).get("state", "NOWE"))
            self.table.setRowHidden(i, not visible)

    def selected(self, row: int, _col: int, _oldrow: int, _oldcol: int) -> None:
        if not 0 <= row < len(self.rows):
            return
        case = self.rows[row]
        if not self.history_mode and not self.runner.active:
            entry = self.case_state.get(case["id"], {}).get("last_attempt")
            self.report = next((r for r in self._history if entry and r["run_id"] == entry["run_id"]), self.report)
        result = next((r for r in self.report["results"] if r["case_id"] == case["id"]), {}) if self.report else {}
        self.instructions.setPlainText("ID: " + case["id"] + "\nCEL: " + case["title"] + "\n\nKRYTERIA:\n" + case["expected"]
                                       + "\n\nWYKONAWCA: " + case["executor"] + "\n" + "\n".join(case["files"])
                                       + "\nZależności: " + ", ".join(case["requirements"]) + "\n\nZAOBSERWOWANO:\n" + result.get("reason", "nie ustalono")
                                       + "\nWynik scenariusza: " + result.get("status", "NOT_RUN")
                                       + "\nOcena bieżącego odbioru: " + TRIAGE_LABELS[self.triage.get(case["id"], {"state": "NOWE"})["state"]]
                                       + "\n" + self.triage.get(case["id"], {}).get("reason", "")
                                       + "\nPełny odbiór operatorski: " + self.full_gate_description(result.get("full_gate", "NOT_RUN"))
                                       + "\nCzas / kod wyjścia: " + str(result.get("duration_seconds", "nie ustalono")) + " s / " + str(result.get("exit_code", "nie ustalono"))
                                       + "\nWyniki z JUnit: " + json.dumps(result.get("counts", {}), ensure_ascii=False)
                                       + "\nUruchomiono: " + " ".join(result.get("command", []))
                                       + "\nDalej: " + result.get("next_step", "Wykonaj kroki odbioru wspomaganego.")
                                       + "\n\nOGRANICZENIA:\n" + case["limitations"])
        guide_key = (self.report["run_id"] if self.report else "", case["id"])
        if self._guide_key != guide_key:
            self.guide_drafts[self._guide_key] = {
                "note": self.note.toPlainText(), "state": self.state.currentIndex(),
                "checked": [i for i in range(self.checklist.count()) if (item := self.checklist.item(i)) is not None and item.checkState() == Qt.CheckState.Checked]}
            self._guide_key = guide_key
            self._guide_id = case["id"]
            self.checklist.clear()
            draft = self.guide_drafts.get(guide_key, {})
            for i, text in enumerate(case["guide"]):
                item = QListWidgetItem(text)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if i in draft.get("checked", []) else Qt.CheckState.Unchecked)
                self.checklist.addItem(item)
            self.note.setPlainText(draft.get("note", ""))
            self.state.setCurrentIndex(draft.get("state", 0))

    def refresh(self) -> None:
        prior_plan = self.plan_history.currentData()
        self.plan_history.clear()
        self.plan_history.addItem("Historia planów — wybierz", "")
        for plan in self.plan_runner.store.history():
            self.plan_history.addItem(plan["created_utc"][:19] + " • " + plan["status"] + " • " + plan["plan_id"][-8:], plan["plan_id"])
        self.plan_history.setCurrentIndex(max(0, self.plan_history.findData(prior_plan)))
        chosen = self.report["run_id"] if self.report else ""
        self.history.blockSignals(True)
        try:
            self.history.clear()
            self.history.addItem("Historia — wybierz przebieg", "")
            history = self.runner.store.history()
            self._history = history
            current = source_identity(self.root)
            probe_source = self.runner.probe.get("source")
            if isinstance(probe_source, dict):
                current.update(probe_source)
            self.triage = triage_cases(self.rows, history, current)
            if self.runner.store.history_errors:
                self.feedback.setText("Błąd odczytu historii: " + " | ".join(self.runner.store.history_errors))
            for report in history:
                self.history.addItem(report["started_utc"][:19] + " • " + report["source"]["version"] + " • " + report["run_id"][-8:], report["run_id"])
            for error in self.runner.store.history_errors:
                run_id = error.split(":", 1)[0]
                self.history.addItem("Uszkodzony raport — " + run_id, run_id)
            if not self.report and history:
                self.report = history[0]
                chosen = self.report["run_id"]
            self.history.setCurrentIndex(max(0, self.history.findData(chosen)))
        finally:
            self.history.blockSignals(False)
        self.refresh_view()

    def load_history(self, _index: int) -> None:
        run_id = self.history.currentData()
        if run_id:
            self.attempt(lambda: self._load_report(str(run_id)))

    def _load_report(self, run_id: str) -> None:
        self.history_mode = True
        self.report = self.runner.store.load(run_id)
        self.attached.clear()
        self.refresh_view()
        self.open_report()

    def show_current(self) -> None:
        self.history_mode = False
        self.refresh()

    def recover_selected_report(self) -> None:
        if self.runner.active:
            raise ValueError("Poczekaj na zakończenie bieżącego przebiegu")
        run_id = self.history.currentData()
        if not run_id:
            raise ValueError("Wybierz przebieg lub jego uszkodzony raport w historii")
        self.runner.store.recover_report(str(run_id))
        self.runner.store.recover_interrupted()
        self.feedback.setText("Odzyskano kompletną rewizję; zachowano poprzednie pliki. Nie wysłano żadnej tury.")
        self.refresh()

    def show_log(self) -> None:
        if not self.report:
            raise ValueError("Wybierz przebieg z historii lub uruchom testy")
        key = self.chosen()
        row = next((r for r in self.report["results"] if r["case_id"] == key), {})
        self._log_selection = (self.report["run_id"], key)
        if self.runner.active and self.report is self.runner.report and row.get("status") == "RUNNING":
            self.auto_log.setPlainText(self.runner.buffer)
            self.tabs.setCurrentWidget(self.auto_log)
            return
        if not row.get("log"):
            raise ValueError("Test nie ma logu w tym przebiegu: nie uruchomiono go lub zapis się nie udał.")
        path = safe_child(self.runner.store.folder(self.report["run_id"]), row["log"])
        if not path.is_file():
            raise ValueError("Brak pliku logu tego przebiegu. Nie wybrano logu innego testu.")
        self.auto_log.setPlainText(self.runner.redactor.text(path.read_text(encoding="utf-8")))
        self.tabs.setCurrentWidget(self.auto_log)

    def open_report(self) -> None:
        if not self.report:
            raise ValueError("Najpierw wybierz przebieg")
        self.report_view.setPlainText(readable_report(self.report))
        self.technical.setPlainText(json.dumps(self.report, ensure_ascii=False, indent=2))
        self.tabs.setCurrentWidget(self.report_view)

    def show_legacy(self) -> None:
        data, _ = legacy.load(self.root)
        self.technical.setPlainText("Historyczne ręczne wyniki; nie są dowodem nowego wykonania.\n" + self.runner.redactor.text(json.dumps(data, ensure_ascii=False, indent=2)))
        self.tabs.setCurrentWidget(self.technical)

    def export_report(self) -> None:
        if not self.report or self.runner.active:
            raise ValueError("Eksport wymaga zakończonego przebiegu")
        name, _ = QFileDialog.getSaveFileName(self, "Nowy raport TPA", self.report["run_id"] + ".zip", "ZIP (*.zip)")
        if name:
            target = self.runner.store.export_zip(self.report, Path(name))
            self.feedback.setText("Wyeksportowano raport i dowody: " + str(target))

    def attach_proof(self) -> None:
        if not self.report:
            raise ValueError("Najpierw wykonaj i wybierz przebieg")
        name, _ = QFileDialog.getOpenFileName(self, "Raport/log testowy; bez prywatnej MEMORY", "", "Raporty (*.txt *.log *.json *.xml)")
        if name:
            artifact = attach_evidence(self.runner.store, self.report, Path(name))
            self.attached.setdefault(self.chosen(), []).append(artifact)
            self.feedback.setText("Dołączono zredagowany dowód: " + artifact)

    def save(self) -> None:
        if not self.report:
            raise ValueError("Najpierw wykonaj podtest lub odbiór izolowany")
        key = self.chosen()
        checked = [i for i in range(self.checklist.count()) if (item := self.checklist.item(i)) is not None and item.checkState() == Qt.CheckState.Checked]
        row = next((r for r in self.report["results"] if r["case_id"] == key), {})
        proofs = list(self.attached.get(key, []))
        if row.get("junit"):
            proofs.append(row["junit"])
        if key + ".live.json" in self.report["artifacts"]:
            proofs.append(key + ".live.json")
        pending = {"report": self.report, "key": key, "checked": checked,
                   "note": self.note.toPlainText(), "proofs": proofs, "outcome": str(self.state.currentData())}
        source_root = Path(self.report.get("environment", {}).get("execution_root") or self.root)
        if (source_root / ".git").exists() or (source_root / "PACKAGE_INTEGRITY_MANIFEST.json").is_file():
            self.pending_observation = pending
            try:
                self.runner.check_ready(source_root=source_root)
            except (OSError, ValueError, RuntimeError):
                self.pending_observation = None
                raise
            self.update_controls()
        else:
            self.finish_observation(pending, None)

    def finish_observation(self, pending: dict, verified: dict | None) -> None:
        record_observation(self.runner.store, pending["report"], pending["key"], pending["checked"],
                           pending["note"], pending["proofs"], pending["outcome"], verified_source=verified)
        self.feedback.setText("Zapisano odrębny odbiór człowieka z dowodami; wcześniejsze obserwacje zachowane.")
        self.refresh_view()

    def shutdown(self) -> bool:
        if self.runner.active or self.plan_runner.active:
            self.stop_work()
            return False
        return True

    def closeEvent(self, event) -> None:
        if not self.shutdown():
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        self.elapsed_timer.stop()
        super().closeEvent(event)
