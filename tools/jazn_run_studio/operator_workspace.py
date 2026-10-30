"""Operator evidence panels over existing jobs; no second runtime or shell."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDockWidget, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)
from .core import ACTIONS, python_executable, StudioError
from .problem_guidance import explain_failure

if TYPE_CHECKING:
    from .window import Window


class TaskConsole(QWidget):
    """A real job output console, explicitly not PTY/ConPTY emulation."""
    def __init__(self, window: Window, index: int):
        super().__init__()
        self.host = window
        self.key = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.choice = QComboBox()
        for action in ACTIONS:
            if not action.mutates:
                self.choice.addItem(action.label, action.key)
        row.addWidget(QLabel(f"Konsola {index}"))
        row.addWidget(self.choice, 1)
        run = QPushButton("Wykonaj")
        run.clicked.connect(lambda: window.guard(self.run))
        row.addWidget(run)
        layout.addLayout(row)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2500)
        self.output.setMinimumHeight(70)
        self.output.setPlaceholderText("Konsola zadań — bez emulacji terminala TTY.")
        layout.addWidget(self.output)
        self.last = ""

    def run(self) -> None:
        self.key = str(self.choice.currentData())
        self.host.core.start_action(self.key)

    def refresh(self) -> None:
        with self.host.core.lock:
            job = self.host.core.jobs.get(self.key)
            text = (self.key + " • " + job.state + "\n" if job else "") + "\n".join(self.host.core.logs.get(self.key, ()))
        if text != self.last:
            self.last = text
            self.output.setPlainText(text)
            self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())


class OperatorWorkspace:
    def __init__(self, window: Window):
        self.host = window
        self.observations: dict[str, dict[str, Any]] = {}
        self.failures: dict[str, dict[str, Any]] = {}
        self.completed = 0
        self.dock_height = 300  # operator-resizable height, not a fixed pane
        self.dock = QDockWidget("Narzędzia operatora", window)
        self.dock.setObjectName("heartOperatorDock")
        self.dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.tabs = QTabWidget()
        self.dock.setWidget(self.tabs)
        self.dock.setMinimumHeight(180)
        window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock)
        self.dock.hide()
        self._problems()
        self._output()
        self._terminal()
        self._history()
        self._technical()
        self._interactive_terminal()
        self.last_output = ""
        self._last_jobs = ""
        self.dock.visibilityChanged.connect(self.dock_visibility_changed)

    def _interactive_terminal(self) -> None:
        from .terminal_view import InteractiveTerminal
        self.interactive_terminal = InteractiveTerminal(self.host)
        self.tabs.addTab(self.interactive_terminal, "Terminal PTY")

    def dock_visibility_changed(self, visible: bool) -> None:
        if visible and not self.host.unified_operator_mode:
            self.host.set_logs_visible(False)
        if not visible and self.dock.height() >= 180:
            self.dock_height = min(3000, self.dock.height())

    def _problems(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.problem_search = QLineEdit()
        self.problem_search.setPlaceholderText("Szukaj problemu, źródła lub powodu")
        self.problem_search.textChanged.connect(self.render_problems)
        layout.addWidget(self.problem_search)
        self.problem_summary = QLabel("Nie wykonano kontroli. Brak potwierdzonej diagnozy.")
        layout.addWidget(self.problem_summary)
        self.problems = QTreeWidget()
        self.problems.setColumnCount(4)
        self.problems.setHeaderLabels(["Poziom / źródło", "Powód", "Czas lokalny", "Moduł"])
        self.problems.itemActivated.connect(self.open_problem)
        self.problems.itemSelectionChanged.connect(self.show_problem_guidance)
        layout.addWidget(self.problems)
        self.problem_details = QLabel(
            "Wybierz problem, aby zobaczyć przyczynę i bezpieczny następny krok."
        )
        self.problem_details.setWordWrap(True)
        self.problem_details.setMinimumHeight(56)
        layout.addWidget(self.problem_details)
        open_logs = QPushButton("Pokaż logi wybranego zadania")
        open_logs.clicked.connect(self.show_selected_logs)
        layout.addWidget(open_logs)
        self.tabs.addTab(panel, "Problemy")

    def _output(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        row = QHBoxLayout()
        self.source = QComboBox()
        self.source.addItem("Wszystkie źródła", "")
        self.output_search = QLineEdit()
        self.output_search.setPlaceholderText("Filtr wyjścia")
        self.follow = QCheckBox("Przewijaj")
        self.follow.setChecked(True)
        export = QPushButton("Eksportuj po redakcji…")
        export.clicked.connect(lambda: self.host.guard(self.export_output))
        row.addWidget(self.source)
        row.addWidget(self.output_search, 1)
        row.addWidget(self.follow)
        row.addWidget(export)
        layout.addLayout(row)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2500)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.output.setPlaceholderText(
            "Zredagowane zdarzenia z bieżącej sesji. Długie linie są skracane "
            "wyłącznie w widoku; pełny raport możesz wyeksportować."
        )
        layout.addWidget(self.output)
        self.tabs.addTab(panel, "Output / Logi")

    def _terminal(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        note = QLabel("Konsole zadań uruchamiają istniejące operacje. Nie są emulatorem PTY; prawdziwa konsola systemowa uruchamia się osobno.")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        tty = QPushButton("Otwórz czat Jaźni w osobnym oknie")
        tty.setEnabled(os.name == "nt" and not self.host.smoke)
        tty.clicked.connect(lambda: self.host.guard(self.open_tty))
        row.addWidget(tty)
        preset = QPushButton("Preset: trzy konsole pionowo")
        preset.clicked.connect(self.three_consoles)
        row.addWidget(preset)
        layout.addLayout(row)
        # Independent full-height tabs avoid stacking three cramped outputs.
        # A true ConPTY/PTY widget is a distinct lifecycle feature.
        self.consoles_splitter = QTabWidget()
        self.consoles_splitter.setAccessibleName("Konsole zadań")
        self.consoles: list[TaskConsole] = []
        self.three_consoles()
        layout.addWidget(self.consoles_splitter)
        self.tabs.addTab(panel, "Konsole zadań")

    def three_consoles(self) -> None:
        while len(self.consoles) < 3:
            console = TaskConsole(self.host, len(self.consoles) + 1)
            self.consoles.append(console)
            self.consoles_splitter.addTab(console, f"Konsola {len(self.consoles)}")

    def _history(self) -> None:
        """History reuses the canonical TPA store, never copies evidence."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        bar = QHBoxLayout()
        self.history_summary = QLabel("Historia: nie odczytano")
        self.history_summary.setWordWrap(True)
        bar.addWidget(self.history_summary, 1)
        refresh = QPushButton("Odśwież")
        refresh.clicked.connect(self.refresh_history)
        bar.addWidget(refresh)
        layout.addLayout(bar)
        self.history_tree = QTreeWidget()
        self.history_tree.setAccessibleName("Historia zadań bieżących i zapisanych przebiegów TPA")
        self.history_tree.setHeaderLabels(["Przebieg / źródło", "Wynik", "Czas", "Akcja"])
        self.history_tree.setRootIsDecorated(False)
        self.history_tree.setAlternatingRowColors(True)
        header = self.history_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.history_tree.itemActivated.connect(self.open_history_item)
        layout.addWidget(self.history_tree)
        self.tabs.addTab(panel, "Historia")

    def refresh_history(self) -> None:
        self.history_tree.clear()
        with self.host.core.lock:
            jobs = [job.snapshot() for job in self.host.core.jobs.values()]
        for job in reversed(jobs[-100:]):
            key = str(job.get("key") or job.get("action") or "zadanie")
            state = str(job.get("state", "nieznany"))
            item = QTreeWidgetItem(self.history_tree, [
                "Zadanie: " + key, state, "bieżąca sesja", "Otwórz log",
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, ("job", key))
        reports: list[dict[str, Any]] = []
        issue = ""
        try:
            store = self.host.local_acceptance_panel.runner.store
            reports = store.history()[:100]
            if store.history_errors:
                issue = " • odczyt: " + "; ".join(str(x) for x in store.history_errors[:2])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            issue = " • błąd odczytu " + type(exc).__name__
        for report in reports:
            run_id = str(report.get("run_id", ""))
            if not run_id:
                continue
            rows = report.get("results") or []
            states = [str(row.get("status", "NOT_RUN")) for row in rows if isinstance(row, dict)]
            passed = states.count("PASS")
            blocked = sum(state in {"FAIL", "BLOCKED", "TIMEOUT"} for state in states)
            item = QTreeWidgetItem(self.history_tree, [
                "TPA: " + run_id, f"{passed} PASS, {blocked} błędów/blokad",
                str(report.get("started_utc", ""))[:19], "Otwórz raport TPA",
            ])
            item.setToolTip(1, "To wyniki podtestów; pełny odbiór jest osobną kontrolą.")
            item.setData(0, Qt.ItemDataRole.UserRole, ("tpa", run_id))
        self.history_summary.setText(
            f"Zadania tej sesji: {len(jobs)} • historia TPA: {len(reports)}" + issue
        )

    def open_history_item(self, item: QTreeWidgetItem, _column: int) -> None:
        identity = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(identity, tuple) or len(identity) != 2:
            return
        kind, key = identity
        if kind == "job":
            self.open_log_source(str(key))
            return
        if kind == "tpa":
            self.host.navigate("TPA")
            panel = self.host.local_acceptance_panel
            index = panel.history.findData(key)
            if index < 0:
                panel.refresh()
                index = panel.history.findData(key)
            if index >= 0:
                panel.history.setCurrentIndex(index)
                panel.load_history(index)

    def _technical(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        refresh = QPushButton("Odśwież dane techniczne (tylko odczyt)")
        refresh.clicked.connect(self.refresh_technical)
        layout.addWidget(refresh)
        self.technical = QPlainTextEdit()
        self.technical.setReadOnly(True)
        self.technical.setAccessibleName("Zredagowane dowody techniczne JSS")
        self.technical.setPlaceholderText("Nie sprawdzono. Odśwież, aby wczytać bieżące dowody.")
        layout.addWidget(self.technical)
        self.tabs.addTab(panel, "Techniczne")

    def refresh_technical(self) -> None:
        with self.host.core.lock:
            jobs = [job.snapshot() for job in self.host.core.jobs.values()]
        payload = {
            "scope": "local_studio_read_only",
            "runtime_readiness": "not_verified_by_this_panel",
            "services": self.observations,
            "jobs": jobs,
            "accepted_visible_turn": True if self.host.core.accepted_turn_proof else None,
        }
        self.technical.setPlainText(self.host.core.redactor.text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        ))

    def open_log_source(self, key: str) -> None:
        """Select one source in the shared output panel; no second log window."""
        self.refresh()
        index = self.source.findData(key)
        self.source.setCurrentIndex(index if index >= 0 else 0)
        self.show(1)
        self.refresh()

    def open_tty(self) -> None:
        """Open the existing canonical Jaźń CLI in a distinct Windows console.

        This does not embed a terminal, claim ownership of an existing daemon,
        or represent shell access. Keep it distinct from open_system_terminal.
        """
        if os.name != "nt":
            raise StudioError("Ten przycisk wymaga terminala Windows")
        core = self.host.core
        subprocess.Popen([python_executable(core.settings), "-X", "utf8", str(core.root / "run.py")],
                         cwd=core.root, env=core.child_environment(), shell=False,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def open_system_terminal(self) -> None:
        """Launch an actual external PowerShell, not the Jaźń runtime CLI.

        Use the Windows system shell by absolute path; never interpolate an
        operator text string into a command, reuse daemon PID, or log secrets.
        """
        if os.name != "nt":
            raise StudioError("Zewnętrzna konsola PowerShell jest dostępna tylko na Windows")
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        shell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if not shell.is_file():
            raise StudioError("Nie znaleziono systemowego PowerShell w katalogu Windows")
        core = self.host.core
        # External operator shells must not inherit optional secret-file
        # credentials injected for canonical runtime children.
        from .core import SECRET_NAME
        safe_env = {key: value for key, value in os.environ.items()
                    if not SECRET_NAME.search(key)}
        safe_env["JAZN_ROOT"] = str(core.root)
        subprocess.Popen([str(shell), "-NoLogo", "-NoProfile", "-NoExit"],
                         cwd=core.root, env=safe_env, shell=False,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def show(self, tab: int = 0) -> None:
        was_visible = self.dock.isVisible()
        if was_visible and self.dock.height() >= 180:
            self.dock_height = min(3000, self.dock.height())
        self.dock.show()
        self.dock.raise_()
        self.tabs.setCurrentIndex(tab)
        if not self.host.unified_operator_mode:
            self.host.set_logs_visible(False)
        # Only opening a hidden dock sets its remembered height.
        # Tab switches must not override the operator's manual resize.
        if not was_visible:
            requested = min(self.dock_height, max(180, self.host.height() - 180))
            self.host.resizeDocks([self.dock], [requested], Qt.Orientation.Vertical)
        if tab == 3:
            self.refresh_history()
        elif tab == 4:
            self.refresh_technical()

    def observe(self, key: str, kind: str, value: Any) -> None:
        if kind in {"evidence", "probe"} and isinstance(value, dict):
            service = "runtime" if kind == "evidence" else str(value.get("service", ""))
            self.observations[service] = dict(value)
        if kind == "state" and value.get("state") in {"succeeded", "failed", "stopped"}:
            self.completed += 1
            self.failures.pop(key, None)
            if value["state"] == "failed":
                self.failures[key] = dict(value)
            self.render_problems()

    def render_problems(self, *_args: object) -> None:
        self.problems.clear()
        query = self.problem_search.text().casefold().strip()
        groups: dict[str, QTreeWidgetItem] = {}
        for key, value in sorted(self.failures.items()):
            reason = self.host.core.redactor.text(str(value.get("error") or "niepowodzenie operacji"))
            guide = explain_failure(key, reason)
            if query and query not in (key + " " + reason + " " + guide.title + " " + guide.remedy).casefold():
                continue
            category = "Usługi opcjonalne" if key.startswith("probe:") else "Runtime" if key in {"status", "start", "stop", "restart"} else "Operacje"
            if category not in groups:
                groups[category] = QTreeWidgetItem(self.problems, [category])
            raw_stamp = value.get("finished") or value.get("started")
            try:
                stamp = (datetime.fromtimestamp(raw_stamp, timezone.utc).astimezone().strftime("%H:%M:%S")
                         if isinstance(raw_stamp, (int, float)) and raw_stamp > 0 else "brak czasu")
            except (OSError, OverflowError, ValueError):
                stamp = "nieprawidłowy czas"
            level = "Ostrzeżenie" if category == "Usługi opcjonalne" else "Błąd"
            target = "Usługi i procesy" if category in {"Runtime", "Usługi opcjonalne"} else "Diagnostyka"
            item = QTreeWidgetItem(groups[category], [level + " • " + key, guide.title, stamp, guide.module])
            item.setToolTip(1, guide.remedy)
            item.setData(0, Qt.ItemDataRole.UserRole, target)
            item.setData(1, Qt.ItemDataRole.UserRole, guide.remedy)
            item.setData(2, Qt.ItemDataRole.UserRole, reason)
            item.setData(3, Qt.ItemDataRole.UserRole, key)
        self.problems.expandAll()
        self.problem_summary.setText(f"Problemy: {len(self.failures)} • wykonane kontrole: {self.completed}" if self.failures else
                                    "Nie wykryto problemów w wykonanych kontrolach." if self.completed else
                                    "Nie wykonano kontroli. Brak potwierdzonej diagnozy.")

    def show_problem_guidance(self) -> None:
        item = self.problems.currentItem()
        if item is None or item.parent() is None:
            self.problem_details.setText("Wybierz konkretny problem, aby zobaczyć rozwiązanie.")
            return
        self.problem_details.setText(
            "Problem: " + item.text(1) + "  •  Kod: "
            + str(item.data(2, Qt.ItemDataRole.UserRole) or "nieznany")
            + "\nCo zrobić: " + str(item.data(1, Qt.ItemDataRole.UserRole) or "Sprawdź logi.")
        )

    def show_selected_logs(self) -> None:
        item = self.problems.currentItem()
        if item is None or item.parent() is None:
            self.problem_details.setText("Najpierw wybierz konkretny problem z listy. Nie otwarto logu innego zadania.")
            return
        key = str(item.data(3, Qt.ItemDataRole.UserRole) or "")
        index = self.source.findData(key)
        if index < 0:
            # Events are already in core logs; refresh adds newly observed sources.
            self.refresh()
            index = self.source.findData(key)
        if index >= 0:
            self.source.setCurrentIndex(index)
        else:
            self.source.setCurrentIndex(0)
        self.show(1)
        self.refresh()

    def open_problem(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.parent() is None:
            return
        target = item.data(0, Qt.ItemDataRole.UserRole)
        if target:
            self.host.navigate(str(target))
        self.problems.setCurrentItem(item)
        self.show_problem_guidance()
        self.show_selected_logs()

    def export_output(self) -> None:
        name, _ = QFileDialog.getSaveFileName(self.host, "Nowy redagowany log", "studio-output.txt", "Tekst (*.txt)")
        if name:
            from .core import _path_without_links
            target = _path_without_links(Path(name).absolute())
            with target.open("x", encoding="utf-8") as stream:
                stream.write(self.host.core.redactor.text("\n".join(self.output_lines())))

    def output_lines(self, logs: dict[str, tuple[str, ...]] | None = None) -> list[str]:
        """Filter source data before presentation truncation or exclusive export."""
        if logs is None:
            with self.host.core.lock:
                logs = {key: tuple(lines) for key, lines in self.host.core.logs.items()}
        query, source = self.output_search.text().casefold(), str(self.source.currentData() or "")
        return [f"[{key}] {line}" for key, values in logs.items() if not source or key == source
                for line in values if not query or query in line.casefold()]

    def refresh(self) -> None:
        core = self.host.core
        with core.lock:
            logs = {key: tuple(lines) for key, lines in core.logs.items()}
            jobs = [j.snapshot() for j in core.jobs.values()]
        existing = {str(self.source.itemData(i)) for i in range(self.source.count())}
        for key in sorted(logs):
            if key not in existing:
                self.source.addItem(key, key)
        lines = self.output_lines(logs)
        # Truncation is presentation-only; source logs and export_report stay untouched.
        preview = [line if len(line) <= 600 else line[:600] + " … [skrócono w widoku]"
                   for line in lines[-2500:]]
        text = "\n".join(preview)
        if text != self.last_output:
            self.last_output = text
            position = self.output.verticalScrollBar().value()
            self.output.setPlainText(text)
            self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum() if self.follow.isChecked() else position)
        for console in self.consoles:
            console.refresh()
        active = sum(j["state"] in {"starting", "running", "stopping"} for j in jobs)
        self.host.operator_status.setText(f"Problemy: {len(self.failures)}  •  Zadania: {active}")
