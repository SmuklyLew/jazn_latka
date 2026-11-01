"""Read-only evidence history over RunStore snapshots, with background I/O."""
from __future__ import annotations

from pathlib import Path
import subprocess
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .tpa_reports import RunStore, STATES
from .test_evidence_archive import export_snapshot, history, import_snapshot


class _Signals(QObject):
    finished = Signal(object)


class _ReadHistory(QRunnable):
    def __init__(self, base: Path, root: Path):
        super().__init__()
        self.base, self.root = base, root
        self.signals = _Signals()

    def run(self) -> None:
        try:
            runs, errors = history(self.base)
            current_sha = None
            current_dirty = None
            # Read-only identity observation, off the GUI thread. Failure is
            # unknown, never a match with historical evidence.
            try:
                result = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                                        capture_output=True, timeout=5, check=False,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.returncode == 0:
                    current_sha = result.stdout.decode("ascii").strip()
                    state = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"],
                                           capture_output=True, timeout=5, check=False,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if state.returncode == 0:
                        current_dirty = bool(state.stdout)
            except (OSError, subprocess.SubprocessError, UnicodeError):
                pass
            self.signals.finished.emit({"runs": runs, "errors": errors, "sha": current_sha, "dirty": current_dirty, "base": self.base})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.signals.finished.emit({"runs": [], "errors": [type(exc).__name__ + ": historia niedostępna"], "sha": None, "dirty": None, "base": self.base})


class _ArchiveJob(QRunnable):
    def __init__(self, operation: str, args: tuple):
        super().__init__()
        self.operation, self.args = operation, args
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = (import_snapshot if self.operation == "import" else export_snapshot)(*self.args)
            self.signals.finished.emit({"operation": self.operation, "path": str(result)})
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            self.signals.finished.emit({"error": type(exc).__name__ + ": odmowa importu/eksportu; zachowano źródłowe dowody"})


class TestHistoryPanel(QWidget):
    """No test runner, mutation, process cleanup or runtime owner is created."""

    __test__ = False

    def __init__(self, root: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.root = root
        self.runs: list[dict] = []
        self.visible: list[dict] = []
        self.current_sha: str | None = None
        self.current_dirty: bool | None = None
        self.worker: _ReadHistory | None = None
        self.archive_worker: _ArchiveJob | None = None
        self.loaded_base: Path | None = None
        layout = QVBoxLayout(self)
        source = QHBoxLayout()
        self.base = QLineEdit(str(RunStore(root).base))
        self.base.setAccessibleName("Katalog dowodów testów do odczytu")
        source.addWidget(self.base, 1)
        choose = QPushButton("Wybierz katalog…")
        choose.clicked.connect(self.choose_folder)
        source.addWidget(choose)
        self.refresh_button = QPushButton("Wczytaj historię")
        self.refresh_button.clicked.connect(self.refresh)
        source.addWidget(self.refresh_button)
        layout.addLayout(source)
        row = QHBoxLayout()
        self.run_choice = QComboBox()
        self.run_choice.setAccessibleName("Przebieg testów")
        self.run_choice.currentIndexChanged.connect(self.render_results)
        row.addWidget(self.run_choice, 2)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Szukaj scenariusza lub przyczyny")
        self.query.setAccessibleName("Filtr historii wyników")
        self.query.textChanged.connect(self.render_results)
        row.addWidget(self.query, 1)
        self.status = QComboBox()
        self.status.addItems(["Wszystkie", *STATES])
        self.status.setAccessibleName("Filtr wyniku wykonania")
        self.status.currentIndexChanged.connect(self.render_results)
        row.addWidget(self.status)
        layout.addLayout(row)
        archive_row = QHBoxLayout()
        self.export_button = QPushButton("Eksportuj ZIP…")
        self.export_button.setAccessibleName("Eksportuj zweryfikowane archiwum dowodów")
        self.export_button.clicked.connect(self.export_selected)
        archive_row.addWidget(self.export_button)
        self.import_button = QPushButton("Importuj ZIP…")
        self.import_button.setAccessibleName("Sprawdź i importuj archiwum dowodów")
        self.import_button.clicked.connect(self.import_archive)
        archive_row.addWidget(self.import_button)
        self.compare_choice = QComboBox()
        self.compare_choice.setAccessibleName("Przebieg porównawczy")
        archive_row.addWidget(self.compare_choice, 1)
        compare = QPushButton("Porównaj")
        compare.setAccessibleName("Porównaj wybrane przebiegi testów")
        compare.clicked.connect(self.compare_runs)
        archive_row.addWidget(compare)
        layout.addLayout(archive_row)
        self.summary = QLabel("Historia jest odczytywana na żądanie. Nie uruchamia testów ani usług.")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Scenariusz", "Wykonanie", "Pełna bramka", "Przyczyna"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAccessibleName("Historyczne wyniki wszystkich scenariuszy")
        self.table.currentCellChanged.connect(self.show_details)
        layout.addWidget(self.table, 1)
        self.previous_outcomes = QLabel("")
        self.previous_outcomes.setWordWrap(True)
        self.previous_outcomes.setTextFormat(Qt.TextFormat.PlainText)
        self.previous_outcomes.setAccessibleName("Ostatni sukces i porażka scenariusza")
        layout.addWidget(self.previous_outcomes)
        self.artifact = QComboBox()
        self.artifact.setAccessibleName("Artefakt wybranego scenariusza")
        self.artifact.currentIndexChanged.connect(self.show_artifact)
        layout.addWidget(self.artifact)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Raport TXT, JSON, JUnit lub log scenariusza")
        self.details.setMaximumHeight(180)
        layout.addWidget(self.details)
        self.errors = QLabel("")
        self.errors.setWordWrap(True)
        self.errors.setTextFormat(Qt.TextFormat.PlainText)
        self.errors.setAccessibleName("Błędy integralności historii")
        layout.addWidget(self.errors)
        for choice in (self.run_choice, self.compare_choice, self.status, self.artifact):
            choice.setMinimumContentsLength(10)
            choice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            choice.setMinimumWidth(0)
            choice.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Katalog przebiegów do odczytu")
        if selected:
            self.base.setText(selected)

    def refresh(self) -> None:
        if self.worker is not None:
            return
        base = Path(self.base.text())
        if not base.is_absolute() or ".." in base.parts:
            self.errors.setText("Wybierz absolutną ścieżkę katalogu bez '..'.")
            return
        self.refresh_button.setEnabled(False)
        self.worker = _ReadHistory(base, self.root)
        self.worker.signals.finished.connect(self.loaded)
        QThreadPool.globalInstance().start(self.worker)

    def loaded(self, payload: dict) -> None:
        self.worker = None
        self.refresh_button.setEnabled(True)
        self.runs, self.current_sha = payload["runs"], payload["sha"]
        self.current_dirty = payload["dirty"]
        self.loaded_base = payload["base"]
        self.errors.setText("\n".join(payload["errors"]))
        self.run_choice.blockSignals(True)
        self.run_choice.clear()
        self.compare_choice.clear()
        for run in self.runs:
            summary = run["summary"]
            self.run_choice.addItem(summary["saved_utc"] + " • " + summary["run_id"])
            self.compare_choice.addItem(summary["saved_utc"] + " • " + summary["run_id"])
        self.run_choice.blockSignals(False)
        if len(self.runs) > 1:
            self.compare_choice.setCurrentIndex(1)
        self.render_results()

    def render_results(self, *_unused: object) -> None:
        index = self.run_choice.currentIndex()
        self.visible = []
        self.table.setRowCount(0)
        self.details.clear()
        self.previous_outcomes.clear()
        self.artifact.clear()
        if not 0 <= index < len(self.runs):
            self.summary.setText("Brak zweryfikowanych przebiegów w wybranym katalogu.")
            return
        run = self.runs[index]
        source = run["summary"]["source"]
        sha = source.get("git_sha")
        relation = ("nie ustalono zgodności źródła" if not sha or not self.current_sha else
                    "bieżący SHA" if sha == self.current_sha and source.get("git_dirty") is False and self.current_dirty is False else
                    "inny SHA lub zmienione źródło")
        self.summary.setText(str(source.get("version")) + " • SHA: " + str(sha or "nie ustalono") +
                             " • " + relation + " • RELEASE_NOT_ACCEPTED")
        query = self.query.text().casefold()
        selected_status = self.status.currentText()
        matching = [row for row in run["results"]
                        if (not query or query in (row["scenario_id"] + " " + row["reason"]).casefold())
                        and (selected_status == "Wszystkie" or row["execution_status"] == selected_status)]
        self.visible = matching[:300]
        self.summary.setText(self.summary.text() + f" • pokazano {len(self.visible)} z {len(matching)}; filtr obejmuje cały przebieg")
        self.table.setRowCount(len(self.visible))
        for i, row in enumerate(self.visible):
            for column, value in enumerate((row["scenario_id"], row["execution_status"], row["full_gate_status"], row["reason"])):
                self.table.setItem(i, column, QTableWidgetItem(str(value)))
        if self.visible:
            self.table.selectRow(0)

    def show_details(self, index: int, *_unused: object) -> None:
        self.artifact.clear()
        if not 0 <= index < len(self.visible):
            self.details.clear()
            return
        row = self.visible[index]
        outcomes = []
        for label, statuses in (("Ostatni PASS wykonania", {"PASS"}), ("Ostatni FAIL/ERROR", {"FAIL", "ERROR"})):
            candidates = [(run["summary"], previous) for run in self.runs for previous in run["results"]
                          if previous["scenario_id"] == row["scenario_id"] and previous["execution_status"] in statuses]
            if candidates:
                summary, _ = max(candidates, key=lambda item: item[0]["saved_utc"])
                outcomes.append(label + ": " + summary["saved_utc"] + " • SHA " + str(summary["source"].get("git_sha") or "UNKNOWN"))
            else:
                outcomes.append(label + ": brak w odczytanej historii")
        self.previous_outcomes.setText("\n".join(outcomes))
        for name in ["scenarios/" + row["scenario_id"] + ".txt", "results/" + row["scenario_id"] + ".json", *row["artifacts"]]:
            self.artifact.addItem(name)
        self.show_artifact()

    def show_artifact(self, *_unused: object) -> None:
        index = self.run_choice.currentIndex()
        if not 0 <= index < len(self.runs):
            return
        raw = self.runs[index]["files"].get(self.artifact.currentText(), b"")
        self.details.setPlainText(raw.decode("utf-8", errors="replace")[:200_000])

    def compare_runs(self) -> None:
        left, right = self.run_choice.currentIndex(), self.compare_choice.currentIndex()
        if not (0 <= left < len(self.runs) and 0 <= right < len(self.runs)):
            return
        a, b = self.runs[left], self.runs[right]
        previous = {row["scenario_id"]: row for row in b["results"]}
        lines = ["Porównanie: " + b["summary"]["run_id"] + " → " + a["summary"]["run_id"],
                 "SHA: " + str(b["summary"]["source"].get("git_sha")) + " → " + str(a["summary"]["source"].get("git_sha"))]
        for row in a["results"]:
            before = previous.pop(row["scenario_id"], {})
            old = (before.get("execution_status", "BRAK"), before.get("full_gate_status", "BRAK"))
            new = (row["execution_status"], row["full_gate_status"])
            if old != new:
                lines.append(row["scenario_id"] + ": " + str(old) + " → " + str(new))
        lines += [case_id + ": brak w porównywanym katalogu" for case_id in previous]
        self.details.setPlainText("\n".join(lines))

    def _archive_job(self, operation: str, args: tuple) -> None:
        if self.archive_worker is not None:
            return
        self.export_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.archive_worker = _ArchiveJob(operation, args)
        self.archive_worker.signals.finished.connect(self.archive_completed)
        QThreadPool.globalInstance().start(self.archive_worker)

    def archive_completed(self, result: dict) -> None:
        self.archive_worker = None
        self.export_button.setEnabled(True)
        self.import_button.setEnabled(True)
        if "error" in result:
            self.errors.setText(result["error"])
        elif result["operation"] == "import":
            self.base.setText(result["path"])
            self.refresh()
        else:
            self.errors.setText("Zapisano zweryfikowane archiwum: " + result["path"])

    def export_selected(self) -> None:
        index = self.run_choice.currentIndex()
        if not 0 <= index < len(self.runs) or self.loaded_base is None:
            return
        destination, _ = QFileDialog.getSaveFileName(self, "Eksport dowodów", "", "ZIP (*.zip)")
        if destination:
            selected = self.runs[index]["summary"]
            self._archive_job("export", (self.loaded_base / selected["run_id"], selected["snapshot"], Path(destination), self.root))

    def import_archive(self) -> None:
        archive, _ = QFileDialog.getOpenFileName(self, "Weryfikacja archiwum dowodów", "", "ZIP (*.zip)")
        if not archive:
            return
        parent = QFileDialog.getExistingDirectory(self, "Katalog nadrzędny nowego importu (poza SYSTEM i MEMORY)")
        if parent:
            destination = Path(parent) / ("import-" + uuid4().hex)
            self._archive_job("import", (Path(archive), destination, self.root))
