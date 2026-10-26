"""Nonblocking first-run wizard; uses existing controller and settings owner."""
from __future__ import annotations

from dataclasses import asdict
from typing import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWizard, QWizardPage, QWidget,
)

from .core import Controller, Settings, StudioError


class CheckPage(QWizardPage):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle(title)
        self.complete = False

    def isComplete(self) -> bool:
        return self.complete

    def mark(self, value: bool) -> None:
        self.complete = value
        self.completeChanged.emit()


class SetupWizard(QWizard):
    def __init__(self, core: Controller, save: Callable[[Settings], None],
                 completed: Callable[[str], None], parent: QWidget | None = None):
        super().__init__(parent)
        self.core, self.save, self.completed = core, save, completed
        self.setWindowTitle("Jaźń — Serce Systemu / Pierwsze uruchomienie")
        self.resize(780, 590)
        self.setButtonText(QWizard.WizardButton.BackButton, "Wstecz")
        self.setButtonText(QWizard.WizardButton.NextButton, "Dalej")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Zakończ")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Anuluj")
        self.requirements = CheckPage("A • Wymagania Studio")
        layout = QVBoxLayout(self.requirements)
        self.stage = QLabel("Kontrola nie została rozpoczęta.")
        self.stage.setWordWrap(True)
        layout.addWidget(self.stage)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Wymaganie", "Stan", "Wynik", "Naprawa"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        retry = QPushButton("Ponów kontrolę")
        retry.clicked.connect(self.retry)
        layout.addWidget(retry)
        self.addPage(self.requirements)

        self.integrations = CheckPage("B • Programy i integracje opcjonalne")
        self.integrations.mark(True)
        optional = QVBoxLayout(self.integrations)
        self.integration_summary = QLabel("Programy nie zostały jeszcze sprawdzone.")
        self.integration_summary.setWordWrap(True)
        optional.addWidget(self.integration_summary)
        optional.addWidget(QLabel("Brak opcjonalnej usługi nie blokuje Studio. Test endpointu nie potwierdza generacji ani tury ChatGPT."))
        for key, label in (("ollama", "Sprawdź endpoint i modele Ollama"), ("gateway", "Sprawdź lokalny MCP")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, k=key: self.probe(k))
            optional.addWidget(button)
        skip = QPushButton("Pomiń opcjonalne")
        skip.clicked.connect(self.next)
        optional.addWidget(skip)
        self.probe_result = QLabel("Nie wykonano testów połączeń.")
        self.probe_result.setWordWrap(True)
        optional.addWidget(self.probe_result)
        optional.addStretch()
        self.addPage(self.integrations)

        self.configuration = QWizardPage()
        self.configuration.setTitle("C • Profil i zakończenie")
        config = QVBoxLayout(self.configuration)
        config.addWidget(QLabel("Konfiguracja pełnego backendu, katalogów i profili jest dostępna w Konfiguracji Qt. Zapis dotyczy przyszłych uruchomień."))
        form = QFormLayout()
        self.model = QLineEdit(core.settings.model)
        self.model.setPlaceholderText("np. gemma3:latest — wybierz model widoczny w Ollama")
        form.addRow("Model Ollama", self.model)
        config.addLayout(form)
        self.consent = QCheckBox("Zapisz sprawdzoną konfigurację Studio i zakończ kreator")
        config.addWidget(self.consent)
        self.notice = QLabel("Usługi i modele nie są automatycznie uruchamiane ani instalowane.")
        self.notice.setWordWrap(True)
        config.addWidget(self.notice)
        config.addStretch()
        self.addPage(self.configuration)
        self.finished_setup = False
        self.report: dict = {}
        self.job = None
        self.probe_job = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        QTimer.singleShot(0, self.retry)

    def retry(self) -> None:
        if self.finished_setup:
            return
        try:
            self.job = self.core.check_setup()
        except (OSError, ValueError, RuntimeError) as exc:
            self.stage.setText("Nie rozpoczęto kontroli: " + type(exc).__name__)
            return
        self.requirements.mark(False)
        self.progress.show()
        self.stage.setText("Sprawdzanie deklaracji projektu, interpretera i integralności SYSTEM…")

    def probe(self, key: str) -> None:
        try:
            self.probe_job = self.core.probe(key)
            self.probe_result.setText("Trwa test: " + key)
        except StudioError as exc:
            self.probe_result.setText(self.core.redactor.text(str(exc)))

    def poll(self) -> None:
        if self.job is not None and self.job.done.is_set():
            job, self.job = self.job, None
            self.progress.hide()
            report = self.core.setup_observation
            self.report = report
            ok = job.state == "succeeded" and report.get("required_ok") is True
            self.requirements.mark(ok)
            self.stage.setText("Wymagania sprawdzone." if ok else "Wymagane składniki wymagają naprawy. Szczegóły poniżej; można anulować i otworzyć diagnostykę.")
            rows = report.get("rows", [])
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, key in enumerate(("name", "state", "detail", "remedy")):
                    self.table.setItem(i, j, QTableWidgetItem(str(row.get(key, ""))))
            found = report.get("discovery", {})
            self.integration_summary.setText("\n".join(
                name + ": " + ("zainstalowane — " + str(found[name]) if found.get(name) else "nie znaleziono")
                for name in ("ollama", "cloudflared", "git")))
        if self.probe_job is not None and self.probe_job.done.is_set():
            job, self.probe_job = self.probe_job, None
            self.probe_result.setText(job.key + ": " + job.state + " / " + str(job.error or "test wykonany; gotowość generacji wymaga osobnego testu"))

    def accept(self) -> None:
        if not self.report.get("required_ok") or not self.consent.isChecked():
            self.notice.setText("Wymagana pozytywna kontrola Studio i zgoda na zapis konfiguracji.")
            return
        try:
            from .requirements_worker import setup_scope
            from .core import python_executable
            if self.report.get("scope") != setup_scope(self.core.root, python_executable(self.core.settings)):
                raise StudioError("Interpreter lub wymagania zmieniły się; ponów kontrolę.")
            data = asdict(self.core.settings)
            data["model"] = self.model.text().strip()
            self.save(Settings.validate(data))
            self.completed(str(self.report["scope"]))
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Nie zapisano konfiguracji", self.core.redactor.text(str(exc)))
            return
        self.finished_setup = True
        self.timer.stop()
        super().accept()

    def reject(self) -> None:
        self.finished_setup = True
        self.timer.stop()
        # The shared read may finish normally; closing a dialog does not stop
        # another operator's diagnostic or an existing runtime.
        super().reject()
