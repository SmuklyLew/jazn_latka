"""Nonblocking first-run wizard; uses existing controller and settings owner."""
from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import json
import os
import sys
from typing import Callable

from PySide6.QtCore import QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWizard, QWizardPage, QWidget,
)

from .core import Controller, Settings, StudioError

# Installation and dependency management belong to Dependency Studio, not onboarding.


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


def _provision_result_ok(command: str, result: dict, *, exit_code: int,
                         native_winget: bool) -> bool:
    """Validate the per-command contract; inspection is read-only evidence."""
    if exit_code != 0:
        return False
    if native_winget:
        return True
    if command == "inspect":
        return (
            result.get("schema_version") == "jazn_jss_prerequisites/v1"
            and isinstance(result.get("ready"), bool)
            and isinstance(result.get("python_314_ready"), bool)
            and isinstance(result.get("ollama_api_ready"), bool)
            and isinstance(result.get("models"), list)
        )
    return result.get("ok") is True


class SetupWizard(QWizard):
    def __init__(self, core: Controller, save: Callable[[Settings], None],
                 completed: Callable[[str], None], parent: QWidget | None = None):
        super().__init__(parent)
        self.core, self.save, self.completed = core, save, completed
        self._original_python_setting = core.settings.python
        self._original_mcp_python_setting = core.settings.mcp_python
        # Retain the rollback contract even when the wizard does not install Python.
        self._provisional_python_setting = ""
        self._provisional_mcp_python_setting = ""
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
        note_ollama = QLabel(
            "Ollama na Windows zwykle działa już w tle po instalacji. "
            "Oficjalny instalator otwiera się w przeglądarce. "
            "Start / Stop / Restart CLI: „Usługi i procesy”. "
            "„Monitor Jaźni” obserwuje cały system bez przejmowania procesów."
        )
        note_ollama.setWordWrap(True)
        optional.addWidget(note_ollama)
        self.ollama_official = QPushButton("Pobierz Ollamę — oficjalna strona")
        self.ollama_official.clicked.connect(self.open_official_ollama_download)
        optional.addWidget(self.ollama_official)
        model_box = QGroupBox("Modele Ollama")
        model_layout = QVBoxLayout(model_box)
        self.models_to_download = QLineEdit("gemma3:latest")
        self.models_to_download.setAccessibleName("Modele Ollama do pobrania, rozdzielone przecinkami")
        self.models_to_download.setPlaceholderText("gemma3:latest, gemma3:1b")
        model_layout.addWidget(QLabel("Pobieranie tylko po jawnej zgodzie:"))
        model_layout.addWidget(self.models_to_download)
        pull_models = QPushButton("Pobierz wybrane modele Ollama")
        pull_models.clicked.connect(lambda _checked=False: self.provision("pull-model"))
        model_layout.addWidget(pull_models)
        self.provision_result = QLabel("Nie pobierano modeli w tej sesji.")
        self.provision_result.setWordWrap(True)
        model_layout.addWidget(self.provision_result)
        optional.addWidget(model_box)

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
        self.configuration.setTitle("C • Ustawienia lokalne i ogólne")
        config = QVBoxLayout(self.configuration)
        note = QLabel(
            "Sprawdź ustawienia Studio i przyszłych usług. Puste pola opcjonalne są dozwolone. "
            "Pamięć kanoniczna jest przyłączana przez runtime, nie kopiowana przez kreator. "
            "Zapis nie uruchamia usług ani nie zmienia aktywnego daemona. "
            "Instalacja Pythona i bibliotek należy do Studia Zależności; "
            "zewnętrzny interpreter wymaga jawnie zweryfikowanej polityki External."
        )
        note.setWordWrap(True)
        config.addWidget(note)
        self.setting_fields: dict[str, QLineEdit] = {}
        self.theme_choice = QComboBox()
        from .workbench_theme import THEME_CHOICES
        for label, key in THEME_CHOICES:
            self.theme_choice.addItem(label, key)
        self.theme_choice.setCurrentIndex(self.theme_choice.findData(core.settings.theme))
        self.runtime_profile_choice = QComboBox()
        self.runtime_profile_choice.addItem("Bez profilu", "off")
        self.runtime_profile_choice.addItem("Walidowany profil operatora", "operator")
        self.runtime_profile_choice.setCurrentIndex(
            1 if core.settings.runtime_profile == "operator" else 0
        )
        group_fields = (
            ("Lokalne uruchomienie", (
                ("python", "Python dla Jaźni"), ("ollama", "Plik Ollama"),
                ("model", "Nazwa modelu Ollama"),
                ("daemon_url", "Adres daemona (loopback)"),
            )),
            ("Integracja ChatGPT — ustawienia opcjonalne", (
                ("mcp_python", "Python dla MCP"),
                ("mcp_port", "Port lokalnego MCP"),
                ("cloudflared", "Plik cloudflared"),
                ("tunnel_config", "Konfiguracja tunelu"),
                ("tunnel_id", "Nazwa lub UUID tunelu"),
                ("cloudflare_url", "Publiczny HTTPS (tylko do testu)"),
            )),
            ("Bezpieczeństwo i wygląd", (
                ("secrets_file", "Ścieżka do prywatnego pliku sekretów"),
                ("accent", "Akcent (#RRGGBB)"),
                ("service_refresh_seconds", "Odstęp monitorowania usług (1/10/30/60 s)"),
            )),
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(230)
        surface = QWidget()
        surface_layout = QVBoxLayout(surface)
        for title, items in group_fields:
            box = QGroupBox(title)
            form = QFormLayout(box)
            for key, label in items:
                field = QLineEdit(str(getattr(core.settings, key)))
                field.setAccessibleName(label)
                if key in {"secrets_file", "tunnel_config"}:
                    field.setToolTip("Podaj ścieżkę absolutną do istniejącego pliku; nie wprowadzaj tokenu.")
                self.setting_fields[key] = field
                form.addRow(label, field)
            surface_layout.addWidget(box)
        from latka_jazn.dependencies.environment_manager import load_environment_policy
        external_policy = load_environment_policy(core.root)
        if external_policy is not None:
            selected = external_policy["python_executable"]
            self.setting_fields["python"].setText(selected)
            if not self.setting_fields["mcp_python"].text().strip():
                self.setting_fields["mcp_python"].setText(selected)
            note.setText(
                note.text() + " Tryb External: Python jest wybierany przez operatora "
                "w .settings_local/python_environment.json, bez instalacji pakietów przez Jaźń."
            )
        appearance = QGroupBox("Profil i motyw")
        appearance_form = QFormLayout(appearance)
        appearance_form.addRow("Motyw", self.theme_choice)
        appearance_form.addRow("Przyszłe uruchomienia", self.runtime_profile_choice)
        surface_layout.addWidget(appearance)
        surface_layout.addStretch()
        scroll.setWidget(surface)
        config.addWidget(scroll, 1)
        self.model = self.setting_fields["model"]  # Existing public wizard field.
        self.model.setReadOnly(True)
        self.model.setPlaceholderText("Wybierz model po wykryciu Ollamy")
        self.model_selector = QComboBox()
        self.model_selector.setEditable(False)
        self.model_selector.setAccessibleName("Model Ollama z lokalnej listy zainstalowanych")
        self.model_selector.addItem("Wykryj modele Ollama w etapie B…", "")
        self.model_selector.currentIndexChanged.connect(self._selected_model)
        model_box = QGroupBox("Zainstalowane modele Ollama")
        model_layout = QVBoxLayout(model_box)
        model_layout.addWidget(self.model_selector)
        model_refresh = QPushButton("Wykryj modele")
        model_refresh.clicked.connect(lambda _checked=False: self.probe("ollama"))
        model_layout.addWidget(model_refresh)
        config.addWidget(model_box)
        suggest = QPushButton("Uzupełnij dostępne programy w pustych polach (bez zapisu)")
        suggest.clicked.connect(self.suggest_paths)
        config.addWidget(suggest)
        self.consent = QCheckBox("Zapisz zweryfikowane ustawienia lokalne i ogólne Studio")
        config.addWidget(self.consent)
        self.notice = QLabel("Usługi i modele nie są automatycznie uruchamiane ani instalowane.")
        self.notice.setWordWrap(True)
        config.addWidget(self.notice)
        self.addPage(self.configuration)
        self.finished_setup = False
        self.report: dict = {}
        self.job = None
        self.probe_job = None
        self.provision_process: QProcess | None = None
        self.provision_buffer = ""
        self.provision_command = ""
        self.provision_remaining_models: list[str] = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        QTimer.singleShot(0, self.retry)

    def _setup_python(self) -> str:
        from .core import python_executable
        return python_executable(self.core.settings, root=self.core.root)

    def _render_setup_rows(self, rows: list[dict]) -> None:
        """Display verified facts without first-run package-install buttons."""
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, key in enumerate(("name", "state", "detail", "remedy")):
                self.table.setItem(i, j, QTableWidgetItem(str(row.get(key, ""))))

    def open_official_ollama_download(self) -> None:
        """Vendor URL only. JSS never downloads or executes Ollama installers."""
        url = "https://ollama.com/download/windows" if sys.platform == "win32" else "https://ollama.com/download"
        if not QDesktopServices.openUrl(QUrl(url)):
            self.provision_result.setText("Nie udało się otworzyć oficjalnej strony Ollama.")

    def provision(self, command: str) -> None:
        """Only model pull remains in onboarding; process control lives in Services."""
        if command != "pull-model":
            self.provision_result.setText(
                "Python i biblioteki: Studio Zależności. Serwer Ollama: Usługi i procesy."
            )
            return
        if self.provision_process is not None and self.provision_process.state() != QProcess.ProcessState.NotRunning:
            self.provision_result.setText("Pobieranie modelu jeszcze trwa.")
            return
        from latka_jazn.tools.jss_prerequisite_setup import MODEL_NAME
        names = [name.strip() for name in self.models_to_download.text().split(",")]
        if not names or len(names) > 8 or any(not MODEL_NAME.fullmatch(name) for name in names):
            self.provision_result.setText("Podaj od jednego do ośmiu poprawnych identyfikatorów modeli.")
            return
        answer = QMessageBox.question(
            self, "Pobieranie modeli Ollama",
            "Pobrać wybrane modele przez oficjalne lokalne API Ollama? "
            "Operacja wymaga transferu i miejsca na dysku. "
            "Nie uruchamia ani nie zatrzymuje usług Jaźni.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.provision_remaining_models = list(dict.fromkeys(names))
        model = self.provision_remaining_models.pop(0)
        self._start_provision_process("pull-model", ["--model", model])

    def _start_provision_process(self, command: str, extra: list[str]) -> None:
        if command != "pull-model":
            raise ValueError("Instalatory i lifecycle Ollama nie należą do kreatora.")
        try:
            python = self._setup_python()
        except StudioError as exc:
            self.provision_remaining_models.clear()
            self.provision_result.setText(self.core.redactor.text(str(exc)))
            return
        self.provision_command = command
        self.provision_buffer = ""
        process = QProcess(self)
        process.setWorkingDirectory(str(self.core.root))
        process.readyReadStandardOutput.connect(self._provision_output)
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.finished.connect(self._provision_finished)
        process.errorOccurred.connect(
            lambda _error: self.provision_result.setText("Nie udało się uruchomić pobierania modelu.")
        )
        self.provision_process = process
        arguments = [
            "-X", "utf8", "-m", "latka_jazn.tools.jss_prerequisite_setup",
            "--root", str(self.core.root), "pull-model", *extra, "--yes",
        ]
        self.provision_result.setText("Trwa pobieranie modelu Ollama.")
        process.start(python, arguments)

    def _provision_output(self) -> None:
        process = self.provision_process
        if process is None:
            return
        chunk = bytes(process.readAllStandardOutput().data()).decode("utf-8", "replace")
        self.provision_buffer = (self.provision_buffer + chunk)[-32768:]
        for line in chunk.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(event, dict) and isinstance(event.get("progress"), dict):
                progress = event["progress"]
                status = str(progress.get("status") or "")[:100]
                completed, total = progress.get("completed"), progress.get("total")
                percent = (
                    f" — {completed * 100 // total}%"
                    if isinstance(completed, int) and isinstance(total, int) and total > 0
                    else ""
                )
                self.provision_result.setText("Model Ollama: " + status + percent)

    def _provision_finished(self, exit_code: int, _status: object) -> None:
        self._provision_output()
        try:
            result = json.loads(self.provision_buffer.strip().splitlines()[-1])
        except (ValueError, TypeError, IndexError):
            result = {}
        ok = (exit_code == 0 and isinstance(result, dict)
              and result.get("ok") is True)
        reason = str(result.get("error_code") or result.get("state") or "invalid_model_pull_result")
        self.core.emit(
            "setup:provision", "state",
            {"state": "succeeded" if ok else "failed",
             "error": None if ok else self.core.redactor.text(reason)[:120],
             "returncode": exit_code},
        )
        self.provision_result.setText(
            ("Zakończono: " if ok else "Niepowodzenie: ")
            + "pull-model / " + self.core.redactor.text(reason)[:120]
        )
        process, self.provision_process = self.provision_process, None
        if process is not None:
            process.deleteLater()
        if ok and self.provision_remaining_models:
            model = self.provision_remaining_models.pop(0)
            self._start_provision_process("pull-model", ["--model", model])
        else:
            self.provision_remaining_models.clear()
            if ok:
                self.probe("ollama")

    def set_installed_models(self, names: object) -> None:
        """Only offer model names returned by the live Ollama API."""
        items = sorted({name for name in names if isinstance(name, str) and name.strip()}) if isinstance(names, list) else []
        previous = self.model.text().strip()
        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        self.model_selector.addItem("Wybierz zainstalowany model…" if items else "Brak dostępnych modeli", "")
        for item in items:
            self.model_selector.addItem(item, item)
        index = self.model_selector.findData(previous)
        self.model_selector.setCurrentIndex(index if index >= 0 else 0)
        self.model_selector.blockSignals(False)

    def _selected_model(self, _index: int) -> None:
        selected = self.model_selector.currentData()
        if isinstance(selected, str) and selected:
            self.model.setText(selected)

    def retry(self) -> None:
        if self.finished_setup:
            return
        try:
            # Form edits are provisional until explicitly saved, but the audit
            # must test the interpreter currently shown to the operator.
            proposed_python = self.setting_fields["python"].text().strip()
            proposed_mcp = self.setting_fields["mcp_python"].text().strip()
            if proposed_python:
                selected = replace(
                    self.core.settings, python=proposed_python,
                    mcp_python=proposed_mcp or proposed_python,
                )
                self.core.settings = Settings.validate(asdict(selected))
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
            self._render_setup_rows(rows)
            found = report.get("discovery", {})
            self.integration_summary.setText("\n".join(
                name + ": " + ("zainstalowane — " + str(found[name]) if found.get(name) else "nie znaleziono")
                for name in ("ollama", "cloudflared", "git")))
        if self.probe_job is not None and self.probe_job.done.is_set():
            job, self.probe_job = self.probe_job, None
            self.probe_result.setText(job.key + ": " + job.state + " / " + str(job.error or "test wykonany; gotowość generacji wymaga osobnego testu"))

    def suggest_paths(self) -> None:
        """Discover installed executable paths without installation or implicit writes."""
        from .core import discovery
        from pathlib import Path
        found = discovery(self.core.settings)
        updated: list[str] = []
        for key in ("python", "ollama", "cloudflared"):
            candidate = found.get(key)
            field = self.setting_fields[key]
            if (not field.text().strip() and isinstance(candidate, str)
                    and Path(candidate).is_file()):
                field.setText(candidate)
                updated.append(key)
        self.notice.setText(
            "Propozycje w formularzu, bez zapisu: " +
            (", ".join(updated) if updated else "brak wykrytych programów")
        )

    def accept(self) -> None:
        if self.provision_process is not None and self.provision_process.state() != QProcess.ProcessState.NotRunning:
            self.notice.setText("Zakończ instalację przed zapisaniem konfiguracji.")
            return
        if not self.report.get("required_ok") or not self.consent.isChecked():
            self.notice.setText("Wymagana pozytywna kontrola Studio i zgoda na zapis konfiguracji.")
            return
        try:
            from .requirements_worker import setup_scope
            from latka_jazn.dependencies.environment_manager import (
                inspect_external_environment, load_environment_policy,
            )
            from latka_jazn.dependencies.private_python import (
                private_python_path, private_python_status,
            )
            data = asdict(self.core.settings)
            data.update({key: field.text().strip() for key, field in self.setting_fields.items()})
            selected_python = Path(str(data.get("python") or "")).absolute()
            selected_mcp = Path(str(data.get("mcp_python") or data.get("python") or "")).absolute()
            policy = load_environment_policy(self.core.root)
            if policy is not None:
                external = inspect_external_environment(self.core.root, policy)
                if not external["ready"]:
                    raise StudioError("External nie jest gotowy: " + ", ".join(external["errors"]))
                canonical = Path(external["python_executable"]).absolute()
                if os.path.normcase(str(selected_python)) != os.path.normcase(str(canonical)):
                    raise StudioError("Jaźń musi używać wskazanego interpretera External.")
                if not selected_mcp.is_file():
                    raise StudioError("Interpreter MCP nie istnieje.")
                data["python"], data["mcp_python"] = str(canonical), str(selected_mcp)
            else:
                if private_python_status(self.core.root).get("ready") is not True:
                    raise StudioError(
                        "ROOT/.venv nie jest gotowe. Użyj Studia Zależności "
                        "albo skonfiguruj i zweryfikuj tryb External."
                    )
                canonical = private_python_path(self.core.root).resolve()
                if selected_python.resolve() != canonical or selected_mcp.resolve() != canonical:
                    raise StudioError(
                        "Jaźń i MCP muszą używać jednego ROOT/.venv. "
                        "Dla zewnętrznego Pythona wybierz zweryfikowany tryb External."
                    )
                data["python"], data["mcp_python"] = str(canonical), str(canonical)
            if self.report.get("scope") != setup_scope(self.core.root, str(canonical)):
                raise StudioError("Interpreter zmieniono od ostatniej kontroli; ponów kontrolę.")
            report_mcp = str((self.report.get("mcp") or {}).get("interpreter") or "")
            if report_mcp and os.path.normcase(os.path.abspath(report_mcp)) != os.path.normcase(str(selected_mcp)):
                raise StudioError("Interpreter MCP zmieniono; ponów kontrolę.")
            data["theme"] = str(self.theme_choice.currentData())
            data["runtime_profile"] = str(self.runtime_profile_choice.currentData())
            self.save(Settings.validate(data))
            self.completed(str(self.report["scope"]))
        except (OSError, ValueError, RuntimeError) as exc:
            # Validation failures are ordinary form errors. A modal warning
            # starts a nested Qt event loop and can freeze headless tests.
            # Keep the refusal but report it within the wizard instead.
            self.notice.setText("Nie zapisano konfiguracji: " + self.core.redactor.text(str(exc)))
            return
        self.finished_setup = True
        self.timer.stop()
        super().accept()

    def reject(self) -> None:
        if self.provision_process is not None and self.provision_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(self, "Instalacja w toku",
                                "Zakończ aktualną operację przygotowania środowiska przed zamknięciem kreatora.")
            return
        if (self._provisional_python_setting
                and self.core.settings.python == self._provisional_python_setting):
            self.core.settings = replace(self.core.settings, python=self._original_python_setting)
        if (self._provisional_mcp_python_setting
                and self.core.settings.mcp_python == self._provisional_mcp_python_setting):
            self.core.settings = replace(self.core.settings, mcp_python=self._original_mcp_python_setting)
        self.finished_setup = True
        self.timer.stop()
        # The shared read may finish normally; closing a dialog does not stop
        # another operator's diagnostic or an existing runtime.
        super().reject()
