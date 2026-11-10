"""Nonblocking first-run wizard; uses existing controller and settings owner."""
from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import json
import shutil
import sys
from typing import Callable

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWizard, QWizardPage, QWidget,
)

from .core import Controller, Settings, StudioError

# Only declared, maintained profiles are installable from the wizard.
_ROW_PROFILES = {
    "Testy: pytest": ("core,run-studio,test-evidence", "python"),
    **{
        name: ("core,run-studio", "python")
        for name in ("tzdata", "packaging", "PySide6-Essentials")
    },
    **{
        "MCP: " + module: ("core,mcp-http", "mcp_python")
        for module in ("mcp", "uvicorn", "starlette", "pydantic", "packaging", "tzdata")
    },
}


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
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Wymaganie", "Stan", "Wynik", "Naprawa", "Instalacja"])
        self.table.setColumnWidth(4, 125)
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
        provisioning = QGroupBox("Przygotowanie środowiska Jaźni — wymagane zgody")
        provision_layout = QVBoxLayout(provisioning)
        self.provision_result = QLabel(
            "Środowisko ROOT/.venv, zasoby i programy są obsługiwane osobno. "
            "Instalacja nie zmienia działającego daemona ani MEMORY."
        )
        self.provision_result.setWordWrap(True)
        provision_layout.addWidget(self.provision_result)
        for title, command in (
            ("Sprawdź ROOT/.venv i Ollamę (bez zmian)", "inspect"),
            ("Przygotuj ROOT/local_resources", "prepare-resources"),
            ("Zainstaluj Python 3.14 (WinGet)", "install-python"),
            ("Utwórz lub sprawdź ROOT/.venv", "prepare-venv"),
            ("Pobierz biblioteki terminala + JSS (online)", "download-deps"),
            ("Zainstaluj zweryfikowane biblioteki (offline)", "install-offline"),
            ("Zainstaluj Ollamę (WinGet)", "install-ollama"),
            ("Uruchom Ollamę jako usługę CLI", "start-ollama"),
            ("Uruchom aplikację Ollama", "start-ollama-app"),
        ):
            button = QPushButton(title)
            button.clicked.connect(lambda _checked=False, name=command: self.provision(name))
            provision_layout.addWidget(button)
        self.models_to_download = QLineEdit("gemma3:latest")
        self.models_to_download.setAccessibleName("Modele Ollama do pobrania, rozdzielone przecinkami")
        self.models_to_download.setPlaceholderText("gemma3:latest, gemma3:1b")
        provision_layout.addWidget(QLabel("Modele do pobrania (domyślnie Gemma 3 4B):"))
        provision_layout.addWidget(self.models_to_download)
        pull_models = QPushButton("Pobierz wybrane modele Ollama")
        pull_models.clicked.connect(lambda _checked=False: self.provision("pull-model"))
        provision_layout.addWidget(pull_models)
        provision_scroll = QScrollArea()
        provision_scroll.setWidgetResizable(True)
        provision_scroll.setMinimumHeight(180)
        provision_scroll.setWidget(provisioning)
        optional.addWidget(provision_scroll, 1)

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
            "Zapis nie uruchamia usług ani nie zmienia aktywnego daemona."
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
        self.provision_native = False
        self.provision_remaining_models: list[str] = []
        self._row_stage = ""
        self._row_name = ""
        self._row_profiles = ""
        self._row_setting = ""
        self._row_python = ""
        self._row_output = ""
        self._row_stderr = ""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        QTimer.singleShot(0, self.retry)

    def _setup_python(self) -> str:
        from .core import python_executable
        return python_executable(self.core.settings)

    def _render_setup_rows(self, rows: list[dict]) -> None:
        # Resetting the rows removes stale buttons after a successful recheck.
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, key in enumerate(("name", "state", "detail", "remedy")):
                self.table.setItem(i, j, QTableWidgetItem(str(row.get(key, ""))))
            name = str(row.get("name") or "")
            if row.get("state") in {"OPTIONAL_MISSING", "FAIL"} and name in _ROW_PROFILES:
                button = QPushButton("Zainstaluj…")
                button.setAccessibleName("Zainstaluj zależność: " + name)
                button.clicked.connect(
                    lambda _checked=False, selected=name: self.install_missing(selected)
                )
                self.table.setCellWidget(i, 4, button)

    def install_missing(self, name: str) -> None:
        spec = _ROW_PROFILES.get(name)
        if spec is None or not any(
            row.get("name") == name and row.get("state") in {"OPTIONAL_MISSING", "FAIL"}
            for row in self.report.get("rows", [])
        ):
            return
        if self._row_stage or (
            self.provision_process is not None
            and self.provision_process.state() != QProcess.ProcessState.NotRunning
        ):
            self.stage.setText("Inna operacja instalacji jeszcze trwa.")
            return
        profiles, setting = spec
        try:
            python = (
                (self.setting_fields["mcp_python"].text().strip()
                 or self.core.settings.mcp_python or self._setup_python())
                if setting == "mcp_python" else self._setup_python()
            )
            if not Path(python).is_absolute() or not Path(python).is_file():
                raise StudioError("Wybrany interpreter nie istnieje.")
        except (OSError, ValueError, RuntimeError) as exc:
            self.stage.setText(self.core.redactor.text(str(exc)))
            return
        from latka_jazn.dependencies.common import default_wheelhouse_root
        wheelhouse = default_wheelhouse_root(self.core.root)
        approved = QMessageBox.question(
            self, "Zgoda na instalację zależności",
            f"Brak: {name}\nProfile: {profiles}\nInterpreter bazowy: {python}\n"
            f"Wheelhouse: {wheelhouse}\n\n"
            "Pobrać pakiety i zbudować zweryfikowany wheelhouse, a następnie "
            "zainstalować offline do NOWEGO, izolowanego środowiska? "
            "Może korzystać z internetu. Nie zmienia aktywnego .venv, MEMORY "
            "ani daemona. Nowy interpreter będzie wymagał zatwierdzenia w kroku C.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if approved != QMessageBox.StandardButton.Yes:
            return
        self._row_name, self._row_profiles = name, profiles
        self._row_setting, self._row_python = setting, python
        self._start_row_step("download")

    def _start_row_step(self, stage: str, bundle: Path | None = None) -> None:
        from latka_jazn.dependencies.common import default_wheelhouse_root
        root = self.core.root.resolve()
        wheelhouse = default_wheelhouse_root(root).resolve()
        arguments = [
            "-X", "utf8", "-m", "latka_jazn.tools.dependency_studio",
            "--root", str(root), "--wheelhouse-root", str(wheelhouse), "--json-summary",
        ]
        if stage == "download":
            arguments += [
                "download", "--profile", self._row_profiles,
                "--platform", "current", "--python-executable", self._row_python,
            ]
        elif stage == "install" and bundle is not None:
            candidate = bundle.resolve()
            if not candidate.is_dir() or not candidate.is_relative_to(wheelhouse):
                self._row_stage = ""
                self.stage.setText("Odmowa: nieprawidłowy katalog wheelhouse.")
                return
            arguments += [
                "install", "--bundle", str(candidate),
                "--profile", self._row_profiles,
                "--python-executable", self._row_python,
                "--environment-root",
                str(root / ".settings_local" / "acceptance" / "dependency_environments"),
                "--offline",
            ]
        else:
            self._row_stage = ""
            self.stage.setText("Odmowa: nieprawidłowa operacja.")
            return
        self._row_stage, self._row_output, self._row_stderr = stage, "", ""
        process = QProcess(self)
        process.setWorkingDirectory(str(root))
        process.readyReadStandardOutput.connect(self._row_read)
        process.readyReadStandardError.connect(self._row_read_stderr)
        process.finished.connect(self._row_finished)
        process.errorOccurred.connect(self._row_error)
        self.provision_process = process
        self.stage.setText(
            ("Pobieranie i weryfikowanie: " if stage == "download" else "Instalacja offline: ")
            + self._row_name
        )
        self.core.emit("setup:dependency-row", "log", f"{stage}: {self._row_name} — rozpoczęto")
        # QProcess receives explicit argv; no shell or arbitrary package names.
        process.start(self._row_python, arguments)

    def _row_read_stderr(self) -> None:
        if self.provision_process is not None:
            chunk = bytes(self.provision_process.readAllStandardError().data()).decode(
                "utf-8", "replace"
            )
            # Kept only in memory. Raw installer output is never written to operator logs.
            self._row_stderr = (self._row_stderr + chunk)[-8192:]

    def _row_error(self, _error: object) -> None:
        process = self.provision_process
        if process is not None and process.state() == QProcess.ProcessState.NotRunning:
            stage = self._row_stage
            self.provision_process = None
            self._row_stage = ""
            process.deleteLater()
            if stage:
                self._row_failure(stage, "process_start_failed", -1, "")

    def _row_read(self) -> None:
        if self.provision_process is not None:
            chunk = bytes(self.provision_process.readAllStandardOutput().data()).decode(
                "utf-8", "replace"
            )
            self._row_output = (self._row_output + chunk)[-65536:]

    def _row_failure(self, stage: str, code: str, exit_code: int, detail: str) -> None:
        # Persist bounded, redacted metadata through the canonical operator channel.
        detail = self.core.redactor.text(detail.strip().splitlines()[-1] if detail.strip() else "")[:160]
        reason = f"{stage}/{code}, exit={exit_code}"
        if detail:
            reason += ": " + detail
        reason = self.core.redactor.text(reason)[:245]
        self.core.emit(
            "setup:dependency-row", "state",
            {"state": "failed", "error": reason, "returncode": int(exit_code)},
        )
        self.core.emit("setup:dependency-row", "log", reason)
        self.stage.setText("Instalacja nieudana: " + reason)

    def _row_finished(self, exit_code: int, _status: object) -> None:
        stage = self._row_stage
        if not stage:
            return  # A process_start_failed event already owns the failure.
        self._row_read()
        self._row_read_stderr()
        # An installer may emit progress before its final machine summary.
        # Never infer success from an exit code or an arbitrary log line.
        payload: dict = {}
        for line in reversed(self._row_output.splitlines()):
            line = line.strip()
            if not (line.startswith("{") and line.endswith("}")):
                continue
            try:
                candidate = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(candidate, dict) and type(candidate.get("ok")) is bool:
                payload = candidate
                break
        process, self.provision_process = self.provision_process, None
        if process is not None:
            process.deleteLater()
        if not isinstance(payload, dict):
            payload = {}
        if exit_code != 0 or payload.get("ok") is not True:
            self._row_stage = ""
            error_type = str(payload.get("error_type") or "invalid_dependency_result")[:80]
            detail = str(payload.get("error") or self._row_stderr or "")
            self._row_failure(stage, error_type, exit_code, detail)
            return
        if stage == "download":
            bundle = payload.get("bundle_dir")
            if not isinstance(bundle, str) or not bundle.strip():
                self._row_stage = ""
                self._row_failure(stage, "bundle_path_missing", exit_code, "")
                return
            self.core.emit("setup:dependency-row", "log", "Zweryfikowano bundle: " + self._row_name)
            self._start_row_step("install", Path(bundle))
            return
        if stage != "install":
            self._row_stage = ""
            self._row_failure(stage, "unexpected_installer_stage", exit_code, "")
            return
        managed = (self.core.root.resolve() / ".settings_local" / "acceptance"
                   / "dependency_environments").resolve()
        interpreter = Path(str(payload.get("python_executable") or ""))
        marker = Path(str(payload.get("environment_marker_path") or ""))
        provided = set(payload.get("profiles") or [])
        expected = set(self._row_profiles.split(","))
        # Full release activation is sufficient for the legacy managed install
        # contract. Optional MCP environments instead have their own verified
        # marker and need not activate the complete runtime dependency profile.
        verified = (
            payload.get("activation_marker_updated") is True
            or (
                payload.get("state") in {"environment_ready", "optional_environment_ready"}
                and expected.issubset(provided)
                and marker.is_absolute() and marker.is_file()
                and marker.resolve().is_relative_to(managed)
            )
        )
        ready = (
            verified and interpreter.is_absolute() and interpreter.is_file()
            and interpreter.resolve().is_relative_to(managed)
        )
        self._row_stage = ""
        if not ready:
            self._row_failure(stage, "managed_environment_not_verified", exit_code, "")
            return
        resolved = str(interpreter.resolve())
        self.setting_fields[self._row_setting].setText(resolved)
        self.core.settings = replace(self.core.settings, **{self._row_setting: resolved})
        if self._row_setting == "python":
            self._provisional_python_setting = resolved
            self.retry()
        else:
            self._provisional_mcp_python_setting = resolved
            self.retry()  # Verify the selected provisional interpreter, before saving.
        self.core.emit(
            "setup:dependency-row", "state",
            {"state": "succeeded", "error": None, "returncode": 0},
        )
        self.core.emit(
            "setup:dependency-row", "log",
            "Weryfikacja nowego środowiska zakończona: " + self._row_name,
        )
        self.stage.setText(
            "Zainstalowano: " + self._row_name
            + ". Zatwierdź interpreter w kroku C. "
            "Dla MCP ponów kontrolę po zapisaniu konfiguracji."
        )

    def provision(self, command: str) -> None:
        from latka_jazn.tools.jss_prerequisite_setup import MODEL_NAME
        if self.provision_process is not None and self.provision_process.state() != QProcess.ProcessState.NotRunning:
            self.provision_result.setText("Inne przygotowanie środowiska jeszcze trwa.")
            return
        if command == "pull-model":
            names = [part.strip() for part in self.models_to_download.text().split(",")]
            if not names or len(names) > 8 or any(not MODEL_NAME.fullmatch(name) for name in names):
                self.provision_result.setText("Podaj od jednego do ośmiu poprawnych identyfikatorów modeli.")
                return
            self.provision_remaining_models = list(dict.fromkeys(names))
        else:
            self.provision_remaining_models.clear()
        if command == "install-offline":
            start = str(self.core.root / "local_resources" / "wheelhouse")
            chosen = QFileDialog.getExistingDirectory(self, "Wybierz zweryfikowany wheelhouse", start)
            if not chosen:
                return
            extra = ["--bundle", chosen]
        elif command in {"prepare-venv", "download-deps"}:
            # Resolve Python 3.14 inside the setup helper. JSS itself may still
            # be running with the older interpreter used to display this UI.
            extra = []
        elif command == "start-ollama-app":
            extra = ["--launch", "app"]
            command = "start-ollama"
        else:
            extra = []
        if command != "inspect":
            answer = QMessageBox.question(
                self, "Zgoda na operację JSS",
                "Wykonać operację: " + command + "? Może instalować programy, "
                "modyfikować ROOT/.venv lub pobierać pliki z sieci. "
                "MEMORY i aktywny daemon Jaźni pozostają nienaruszone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.provision_remaining_models.clear()
                return
        if command == "pull-model":
            model = self.provision_remaining_models.pop(0)
            extra = ["--model", model]
        self._start_provision_process(command, extra)

    def _start_provision_process(self, command: str, extra: list[str]) -> None:
        native_winget = False
        try:
            python = self._setup_python()
        except StudioError as exc:
            if command in {"install-python", "install-ollama"} and sys.platform == "win32":
                python = shutil.which("winget") or ""
                native_winget = bool(python)
            else:
                self.provision_result.setText(self.core.redactor.text(str(exc)))
                return
            if not native_winget:
                self.provision_result.setText("Brak Pythona i WinGet. Potrzebny oficjalny bootstrap SYSTEM.")
                return
        self.provision_command = command
        self.provision_native = native_winget
        self.provision_buffer = ""
        process = QProcess(self)
        process.setWorkingDirectory(str(self.core.root))
        process.readyReadStandardOutput.connect(self._provision_output)
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.finished.connect(self._provision_finished)
        process.errorOccurred.connect(
            lambda _error: self.provision_result.setText("Nie udało się uruchomić instalatora JSS.")
        )
        self.provision_process = process
        if native_winget:
            package = "Python.Python.3.14" if command == "install-python" else "Ollama.Ollama"
            arguments = ["install", "--id", package, "--exact",
                         "--accept-source-agreements", "--accept-package-agreements"]
        else:
            arguments = [
                "-X", "utf8", "-m", "latka_jazn.tools.jss_prerequisite_setup",
                "--root", str(self.core.root), command, *extra,
            ]
            if command != "inspect":
                arguments.append("--yes")
        self.provision_result.setText("Trwa operacja: " + command + " (nie zmienia daemona).")
        process.start(python, arguments)

    def _provision_output(self) -> None:
        process = self.provision_process
        if process is not None:
            chunk = bytes(process.readAllStandardOutput().data()).decode("utf-8", "replace")
            # Operator only sees bounded, sanitized status rather than raw pip/installer output.
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
        ok = _provision_result_ok(
            self.provision_command, result, exit_code=exit_code,
            native_winget=self.provision_native,
        )
        if not ok:
            reason = self.core.redactor.text(
                str(result.get("error_code") or result.get("state") or "invalid_provision_result")
            )[:120]
            self.core.emit("setup:provision", "state",
                           {"state": "failed", "error": reason, "returncode": exit_code})
        if self.provision_native and ok:
            result = {"state": "winget_completed_recheck_required"}
        if ok:
            self.core.emit("setup:provision", "state",
                           {"state": "succeeded", "error": None, "returncode": 0})
        if ok and self.provision_command == "inspect":
            self.provision_result.setText(
                "Sprawdzono ROOT/.venv/Ollama (tylko odczyt) — "
                + ("Python 3.14: gotowy" if result["python_314_ready"]
                   else "Python 3.14: wymaga przygotowania")
                + "; " + ("Ollama API: dostępne" if result["ollama_api_ready"]
                          else "Ollama API: niedostępne")
            )
        else:
            self.provision_result.setText(
                ("Zakończono: " if ok else "Niepowodzenie: ") + self.provision_command
                + " / " + str(result.get("state") or result.get("error_code") or "brak wiarygodnego JSON")
            )
        process, self.provision_process = self.provision_process, None
        if process is not None:
            process.deleteLater()
        if ok and self.provision_command == "pull-model" and self.provision_remaining_models:
            model = self.provision_remaining_models.pop(0)
            self._start_provision_process("pull-model", ["--model", model])
        else:
            self.provision_remaining_models.clear()
            if ok and self.provision_command == "install-offline":
                candidate = self.core.root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
                if candidate.is_file():
                    self.setting_fields["python"].setText(str(candidate))
                    # In-memory only; the user still explicitly approves
                    # persistence in the wizard's final configuration step.
                    self.core.settings = replace(self.core.settings, python=str(candidate))
                    self._provisional_python_setting = str(candidate)
            if ok and self.provision_command in {"prepare-venv", "install-offline", "download-deps"}:
                self.retry()
            if ok and self.provision_command in {"pull-model", "start-ollama", "install-ollama"}:
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
            from .core import python_executable
            if self.report.get("scope") != setup_scope(self.core.root, python_executable(self.core.settings)):
                raise StudioError("Interpreter lub wymagania zmieniły się; ponów kontrolę.")
            data = asdict(self.core.settings)
            data.update({key: field.text().strip() for key, field in self.setting_fields.items()})
            data["theme"] = str(self.theme_choice.currentData())
            data["runtime_profile"] = str(self.runtime_profile_choice.currentData())
            self.save(Settings.validate(data))
            self.completed(str(self.report["scope"]))
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Nie zapisano konfiguracji", self.core.redactor.text(str(exc)))
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
