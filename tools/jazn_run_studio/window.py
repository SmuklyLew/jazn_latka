"""Qt desktop shell. Only the GUI thread accesses widgets."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from pathlib import Path
import queue
from typing import Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSplashScreen, QSplitter, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import STUDIO_VERSION
from .core import ACTIONS, STUDIOS, Controller, Settings, StudioError, discovery, save_settings
from .studio_worker import preview_fingerprint
from .workbench_theme import THEME_CHOICES, workbench_stylesheet

INSTALL_LINKS = {
    "Python": "https://www.python.org/downloads/",
    "Qt / PySide6": "https://doc.qt.io/qtforpython-6/gettingstarted.html",
    "Ollama": "https://ollama.com/download",
    "Cloudflare Tunnel": "https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/",
}


class Window(QMainWindow):
    def __init__(self, core: Controller, *, smoke: bool = False):
        super().__init__()
        self.core = core
        self.smoke = smoke
        # One dock in production; preserve the legacy smoke-test route.
        self.unified_operator_mode = not smoke
        from .core import load_settings
        _, self.digest = load_settings(core.root)
        self.setWindowTitle("Jaźń — Serce Systemu")
        self.resize(1240, 840)
        self.setMinimumSize(860, 580)
        self.logs: dict[str, QPlainTextEdit] = {}
        self.fields: dict[str, QLineEdit] = {}
        self.statuses: dict[str, QLabel] = {}
        self.dashboard_statuses: dict[str, QLabel] = {}
        self.nav = QListWidget()
        self.nav.setObjectName("workbenchNavigation")
        self.nav.setAccessibleName("Nawigacja Studio")
        self.nav.setMinimumWidth(188)
        self.nav.setMaximumWidth(250)
        self.pages = QStackedWidget()
        self.pages.setAccessibleName("Obszar roboczy Jaźni")
        self.tabs = QTabWidget()
        self.tabs.setObjectName("workbenchOutputTabs")
        self.tabs.setAccessibleName("Dolny panel logów, zdarzeń i diagnostyki")
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(False)
        self.tabs.setMinimumHeight(140)
        self.tabs.hide()
        self.logs_user_hidden = True

        self.sidebar = QWidget()
        self.sidebar.setObjectName("workbenchSidebar")
        self.sidebar.setMinimumWidth(188)
        self.sidebar.setMaximumWidth(250)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 14, 8, 10)
        sidebar_layout.setSpacing(8)
        brand = QLabel("JAŹŃ  /  SERCE SYSTEMU")
        brand.setObjectName("workbenchBrand")
        brand.setWordWrap(True)
        sidebar_layout.addWidget(brand)
        description = QLabel("PANEL OPERACYJNY")
        description.setObjectName("workbenchCaption")
        sidebar_layout.addWidget(description)
        sidebar_layout.addWidget(self.nav, 1)
        self.sidebar_footnote = QLabel("Runtime • gotowość niezweryfikowana")
        self.sidebar_footnote.setObjectName("workbenchFootnote")
        self.sidebar_footnote.setWordWrap(True)
        sidebar_layout.addWidget(self.sidebar_footnote)

        self.topbar = QWidget()
        self.topbar.setObjectName("workbenchTopbar")
        header_layout = QHBoxLayout(self.topbar)
        header_layout.setContentsMargins(14, 7, 14, 7)
        header_layout.setSpacing(12)
        self.menu_button = QPushButton("☰")
        self.menu_button.setAccessibleName("Pokaż lub ukryj boczną nawigację")
        self.menu_button.setToolTip("Boczna nawigacja (Ctrl+B)")
        self.menu_button.setFixedWidth(40)
        self.menu_button.clicked.connect(self.toggle_sidebar)
        header_layout.addWidget(self.menu_button)
        self.current_section = QLabel("Pulpit")
        self.current_section.setObjectName("workbenchSection")
        header_layout.addWidget(self.current_section)
        self.section_search = QLineEdit()
        self.section_search.setPlaceholderText("Szukaj sekcji…")
        self.section_search.setAccessibleName("Wyszukiwanie sekcji Studio")
        self.section_search.setMaximumWidth(230)
        self.section_search.setMinimumWidth(90)
        self.section_search.textChanged.connect(self.filter_navigation)
        self.section_search.returnPressed.connect(self.select_search_result)
        header_layout.addWidget(self.section_search, 1)
        self.style_selector = QComboBox()
        self.style_selector.setObjectName("jssStyleSelector")
        self.style_selector.setAccessibleName("Wybór wyglądu całego JSS")
        self.style_selector.setToolTip("Zmiana wyglądu nie uruchamia ani nie zatrzymuje usług.")
        for label, key in THEME_CHOICES:
            self.style_selector.addItem(label, key)
        self.style_selector.setCurrentIndex(self.style_selector.findData(core.settings.theme))
        self.style_selector.currentIndexChanged.connect(self.style_selected)
        header_layout.addWidget(self.style_selector)
        header_layout.addStretch(1)
        self.workbench_status = QLabel("Lokalne Studio  •  status niezweryfikowany")
        self.workbench_status.setObjectName("workbenchStatus")
        self.workbench_status.setAccessibleName("Ostatnio sprawdzona gotowość lokalnego runtime; nie oznacza zaakceptowanej odpowiedzi")
        header_layout.addWidget(self.workbench_status)

        self.content_splitter = QSplitter(Qt.Orientation.Vertical)
        self.content_splitter.setObjectName("workbenchVerticalSplitter")
        self.content_splitter.addWidget(self.pages)
        self.content_splitter.addWidget(self.tabs)
        self.content_splitter.setCollapsible(0, False)
        self.content_splitter.setCollapsible(1, True)
        self.content_splitter.setStretchFactor(0, 4)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setHandleWidth(5)

        canvas = QWidget()
        canvas.setObjectName("workbenchCanvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        canvas_layout.addWidget(self.topbar)
        canvas_layout.addWidget(self.content_splitter, 1)

        self.shell_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.shell_splitter.addWidget(self.sidebar)
        self.shell_splitter.addWidget(canvas)
        self.shell_splitter.setCollapsible(0, True)
        self.shell_splitter.setCollapsible(1, False)
        self.shell_splitter.setStretchFactor(0, 0)
        self.shell_splitter.setStretchFactor(1, 1)
        self.shell_splitter.setHandleWidth(5)
        self.shell_splitter.setSizes([214, 1026])
        self.setCentralWidget(self.shell_splitter)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.currentRowChanged.connect(self.update_current_section)

        self.panel_shortcut = QAction("Przełącz panel logów", self)
        self.panel_shortcut.setShortcut(QKeySequence("Ctrl+J"))
        self.panel_shortcut.triggered.connect(self.toggle_logs)
        self.addAction(self.panel_shortcut)
        self.sidebar_shortcut = QAction("Przełącz pasek nawigacji", self)
        self.sidebar_shortcut.setShortcut(QKeySequence("Ctrl+B"))
        self.sidebar_shortcut.triggered.connect(self.toggle_sidebar)
        self.addAction(self.sidebar_shortcut)
        self._dashboard()
        self._services()
        self._chat()
        self._diagnostics()
        self._studios()
        self._tests_catalog()
        self._local_acceptance()
        self._memory()
        self._settings()
        self._about()
        # Preserve legacy navigation indices for Test/MEMORY/TPA operator
        # workspaces. New native pages are appended, never inserted mid-list.
        self._configuration()
        self._version_studio()
        self._models()
        self._connections()
        self._developer()
        self.operator_status = QPushButton("Problemy: nie sprawdzono")
        self.operator_status.setFlat(True)
        self.statusBar().addPermanentWidget(self.operator_status, 1)
        from .operator_workspace import OperatorWorkspace
        self.workspace = OperatorWorkspace(self)
        self.operator_status.clicked.connect(lambda: self.workspace.show(0))
        self._workspace_menu()
        self.settings_baseline = self.settings_draft()
        self.setup_wizard = None
        self.layout_state = {}
        self.log_toggle = QPushButton("Pokaż logi")
        self.log_toggle.setAccessibleName("Pokaż lub ukryj dolny panel logów")
        self.log_toggle.clicked.connect(self.toggle_logs)
        self.statusBar().addPermanentWidget(self.log_toggle)
        self.restore_layout()
        self.navigate(self.layout_state.get("active_section", "Pulpit"))
        self.statusBar().showMessage(str(core.root))
        self.apply_theme()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        # Discovery is read-only and local. Network probes require explicit actions.
        self.render_discovery()
        if os.environ.get("JAZN_STUDIO_ACCEPTANCE_PROFILE") == "isolated":
            target = os.environ.get("JAZN_TPA_TARGET_SECTION", "")
            if target:
                self.navigate(target)
            studio = self.studio_choice.findData(os.environ.get("JAZN_TPA_TARGET_STUDIO", ""))
            if studio >= 0:
                self.studio_choice.setCurrentIndex(studio)
        if not smoke:
            from .requirements_worker import setup_scope
            from .core import python_executable
            if self.layout_state.get("setup_scope") != setup_scope(self.core.root, python_executable(self.core.settings)):
                QTimer.singleShot(0, self.open_setup)
        if isinstance(app := QApplication.instance(), QApplication):
            app.styleHints().colorSchemeChanged.connect(lambda _scheme: self.apply_theme())

    def page(self, title: str, description: str, *, compact: bool = False) -> QVBoxLayout:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        from .workbench_theme import METRICS
        layout.setContentsMargins(METRICS.page_margin, 12, METRICS.page_margin, 12)
        layout.setSpacing(METRICS.gap)
        heading = QLabel(title)
        heading.setObjectName("heading")
        if not compact:
            layout.addWidget(heading)
        subtitle = QLabel(description)
        subtitle.setWordWrap(True)
        if not compact:
            layout.addWidget(subtitle)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(pane)
        self.pages.addWidget(scroll)
        self.nav.addItem(title)
        return layout

    def button(self, label: str, callback: Callable[[], object], parent: QVBoxLayout | QHBoxLayout) -> QPushButton:
        button = QPushButton(label)
        button.clicked.connect(lambda _checked=False: self.guard(callback))
        parent.addWidget(button)
        return button

    def guard(self, action: Callable[[], object]) -> None:
        try:
            action()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Operacja niedostępna", self.core.redactor.text(str(exc)))

    def action(self, key: str) -> None:
        item = next(a for a in ACTIONS if a.key == key)
        if item.mutates and QMessageBox.question(self, item.label,
                item.description + "\nWykonać tę operację?") != QMessageBox.StandardButton.Yes:
            return
        self.core.start_action(key)
        self.show_log(key)

    def _dashboard(self) -> None:
        layout = self.page("Pulpit", "JAŹŃ / STARTER    •    Sprawdź środowisko, wybierz usługę i obserwuj wynik.")
        self.button("Kreator konfiguracji…", self.open_setup, layout)
        self.dashboard_summary: dict[str, QLabel] = {}
        self.quick_runtime_ready = False
        self.quick_generation_ready = False
        self.quick_start_status = QLabel(
            "Krok 1: runtime niezweryfikowany. Krok 2: model niezweryfikowany. "
            "Krok 3: rozmowa zostanie odblokowana po dwóch testach."
        )
        self.quick_start_status.setWordWrap(True)
        layout.addWidget(self.quick_start_status)
        steps = QHBoxLayout()
        self.button("1. Uruchom runtime", lambda: self.action("start"), steps)
        self.button("Sprawdź runtime", lambda: self.action("status"), steps)
        self.button("2. Uruchom / sprawdź Ollama", self.core.ensure_ollama, steps)
        self.button("Sprawdź generację", lambda: self.core.probe("ollama_generate"), steps)
        layout.addLayout(steps)
        self.button("Sprawdź gotowość lokalną (bez uruchamiania usług)",
                    self.check_local_readiness, layout)
        chat_steps = QHBoxLayout()
        self.quick_chat_button = self.button(
            "3. Przejdź do rozmowy", lambda: self.navigate("Czat lokalny"), chat_steps
        )
        self.quick_chat_button.setEnabled(False)
        self.button("Status pamięci i ciągłości", lambda: self.navigate("Dowody MEMORY"), chat_steps)
        layout.addLayout(chat_steps)
        self.quick_memory_status = QLabel(
            "MEMORY: sprawdź status runtime; obecność bazy nie potwierdza ciągłości."
        )
        self.quick_memory_status.setWordWrap(True)
        layout.addWidget(self.quick_memory_status)
        summary = QFormLayout()
        for key, title in (("version", "Wersja SYSTEM"), ("integrity", "Integralność SYSTEM"),
                           ("provenance", "Pochodzenie źródeł"), ("memory", "MEMORY"),
                           ("continuity", "Ciągłość / wake-state"), ("model", "Adapter językowy")):
            field = QLabel("Nie wykonano kontroli statusu.")
            field.setTextFormat(Qt.TextFormat.PlainText)
            field.setWordWrap(True)
            field.setAccessibleName("Pulpit: " + title)
            self.dashboard_summary[key] = field
            summary.addRow(title, field)
        layout.addLayout(summary)
        self.dashboard_last_operation = QLabel("Ostatnia operacja: brak wykonanych zadań.")
        self.dashboard_last_operation.setTextFormat(Qt.TextFormat.PlainText)
        self.dashboard_last_operation.setWordWrap(True)
        layout.addWidget(self.dashboard_last_operation)
        self.button("Problemy i ostrzeżenia", lambda: self.workspace.show(0), layout)
        self.evidence = QLabel("Runtime: jeszcze nie sprawdzono. Gotowość rozmowy wymaga osobnego potwierdzenia.")
        self.evidence.setWordWrap(True)
        layout.addWidget(self.evidence)
        layout.addWidget(QLabel("Stan usług (ostatnio potwierdzony; brak testu ≠ zatrzymanie)"))
        for service, title in (("runtime", "Jaźń"), ("ollama", "Ollama"),
                               ("gateway", "Brama MCP"), ("cloudflare", "Cloudflare Tunnel")):
            label = QLabel(title + ": Nie sprawdzono")
            label.setWordWrap(True)
            label.setAccessibleName("Pulpit: " + title)
            self.dashboard_statuses[service] = label
            layout.addWidget(label)
        row = QHBoxLayout()
        self.button("Sprawdź status runtime", lambda: self.action("status"), row)
        self.button("Stan usług", self.refresh_services, row)
        self.button("Uruchom diagnostykę krok po kroku", self.core.run_batch, row)
        layout.addLayout(row)
        layout.addWidget(QLabel("Wykryte programy i zależności"))
        self.setup = QTableWidget(0, 3)
        self.setup.setHorizontalHeaderLabels(["Składnik", "Stan", "Lokalizacja / szczegóły"])
        self.setup.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setup.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.setup)
        links = QHBoxLayout()
        for name, url in INSTALL_LINKS.items():
            self.button("Instalacja: " + name, lambda u=url: QDesktopServices.openUrl(QUrl(u)), links)
        layout.addLayout(links)
        self.button("Odśwież wykrywanie", self.render_discovery, layout)

    def check_local_readiness(self) -> None:
        """Read-only checks, never starts a second daemon or downloads a model."""
        self.core.start_action("status")
        self.core.probe("ollama")
        self.quick_start_status.setText(
            "Sprawdzam osobno status daemona i listę modeli Ollama. "
            "Nie uruchamiam usług ani nie zmieniam MEMORY."
        )

    def refresh_quick_start(self) -> None:
        """Only actual runtime identity and explicit Ollama generation unlock chat."""
        ready = (self.quick_runtime_ready and self.quick_generation_ready
                 and bool(self.core.settings.model))
        self.quick_chat_button.setEnabled(ready)
        self.quick_start_status.setText(
            "1. Runtime: " + ("potwierdzony" if self.quick_runtime_ready else "niezweryfikowany") +
            "  •  2. Model: " + ("generacja potwierdzona" if self.quick_generation_ready
                                 else "brak potwierdzonej generacji") +
            "  •  3. Czat: " + ("możesz połączyć" if ready else "wymaga obu etapów")
        )

    def render_discovery(self) -> None:
        data = discovery(self.core.settings)
        rows = [(name, "Dostępny" if data.get(name) else "Brak", str(data.get(name) or "Wskaż plik w ustawieniach"))
                for name in ("python", "ollama", "cloudflared", "git")]
        rows += [(name, "Dostępna" if present else "Brak", "Biblioteka Pythona") for name, present in data["dependencies"].items()]
        self.setup.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.setup.setItem(row, column, QTableWidgetItem(value))
        self.setup.resizeColumnsToContents()

    def _services(self) -> None:
        layout = self.page("Usługi i procesy", "Status, własność procesu i gotowość są niezależnymi dowodami. Start/Stop/Restart korzystają z kanonicznych kontrolerów.")
        self.services_table = QTableWidget(6, 6)
        self.services_table.setHorizontalHeaderLabels(["Usługa", "Status", "PID", "Port", "Readiness", "Akcje"])
        self.services_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.services_table.horizontalHeader().setStretchLastSection(False)
        self.services_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.services_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.services_table.setMinimumWidth(0)
        self.services_table.setMinimumHeight(350)
        self.service_rows = {}
        self.supervisor_observation: dict = {}
        self.memory_observed = False
        for row, (service, title) in enumerate((("runtime", "Jaźń"), ("ollama", "Ollama"), ("gateway", "MCP lokalne"), ("cloudflare", "MCP HTTPS"), ("supervisor", "Supervisor"), ("memory", "MEMORY"))):
            self.service_rows[service] = row
            self.services_table.setItem(row, 0, QTableWidgetItem(title))
            status = QLabel("Nie sprawdzono")
            status.setTextFormat(Qt.TextFormat.PlainText)
            status.setWordWrap(True)
            status.setMinimumWidth(0)
            self.statuses[service] = status
            self.services_table.setCellWidget(row, 1, status)
            for column in (2, 3, 4):
                self.services_table.setItem(row, column, QTableWidgetItem("—"))
            button = QPushButton("Akcje ▾")
            menu = QMenu(button)
            if service in {"runtime", "ollama", "gateway"}:
                for op, label in (("start", "Start"), ("stop", "Stop"), ("restart", "Restart")):
                    action = menu.addAction(label)
                    action.triggered.connect(lambda _checked=False, s=service, o=op: self.guard(lambda: self.service(s, o)))
            config = menu.addAction("Konfiguracja")
            config.triggered.connect(lambda: self.navigate("Ustawienia"))
            logs = menu.addAction("Logi")
            logs.triggered.connect(lambda _checked=False, s=service: self.show_log("status" if s in {"runtime", "memory"} else "supervisor" if s == "supervisor" else "service:" + s))
            details = menu.addAction("Szczegóły / odśwież")
            details.triggered.connect(lambda _checked=False, s=service: self.guard(lambda: self.inspect_service(s)))
            button.setMenu(menu)
            self.services_table.setCellWidget(row, 5, button)
        self.services_table.setColumnWidth(0, 105)
        self.services_table.setColumnWidth(1, 190)
        self.services_table.setColumnWidth(2, 45)
        self.services_table.setColumnWidth(3, 55)
        self.services_table.setColumnWidth(5, 85)
        self.services_table.verticalHeader().setDefaultSectionSize(64)
        layout.addWidget(self.services_table)
        self.service_selected_label = QLabel("Wybierz moduł i dostępną operację.")
        self.service_selected_label.setWordWrap(True)
        layout.addWidget(self.service_selected_label)
        controls = QHBoxLayout()
        self.service_start_button = self.button("Start", lambda: self.selected_service_action("start"), controls)
        self.service_stop_button = self.button("Stop", lambda: self.selected_service_action("stop"), controls)
        self.service_restart_button = self.button("Restart", lambda: self.selected_service_action("restart"), controls)
        self.button("Status", lambda: self.selected_service_action("inspect"), controls)
        self.button("Logi", lambda: self.show_log(
            "status" if self.selected_service() in {"runtime", "memory"} else
            "supervisor" if self.selected_service() == "supervisor" else
            "service:" + self.selected_service()), controls)
        layout.addLayout(controls)
        self.services_table.itemSelectionChanged.connect(self.refresh_service_controls)
        self.services_table.selectRow(0)
        self.refresh_service_controls()
        self.button("Odśwież stan wszystkich modułów", self.refresh_services, layout)
        self.button("Sprawdź usługę Windows cloudflared", lambda: self.core.probe("tunnel_service"), layout)
        remote_note = QLabel("Cloudflare, supervisor i MEMORY: odczyt bez przejmowania procesów lub prywatnych danych. Lokalny MCP nie jest publikowany publicznie. Nie ma automatycznego Start All/Stop All; zamknięcie Studio nie zatrzymuje daemona.")
        remote_note.setWordWrap(True)
        layout.addWidget(remote_note)
        self.processes = QPlainTextEdit()
        self.processes.setReadOnly(True)
        self.processes.setMaximumHeight(150)
        if self.unified_operator_mode:
            self.processes.hide()
            self.button("Dane techniczne i historia usług", lambda: self.workspace.show(4), layout)
        else:
            layout.addWidget(self.processes)

    def selected_service(self) -> str:
        row = self.services_table.currentRow()
        return next((key for key, index in self.service_rows.items() if index == row), "")

    def inspect_service(self, service: str) -> None:
        if service in {"runtime", "memory"}:
            self.core.start_action("status")
        elif service == "supervisor":
            self.core.start_action("supervisor")
        else:
            self.core.probe(service)

    def selected_service_action(self, operation: str) -> None:
        service = self.selected_service()
        if not service:
            raise StudioError("Wybierz moduł")
        if operation == "inspect":
            self.inspect_service(service)
        elif service in {"runtime", "ollama", "gateway"}:
            self.service(service, operation)
        else:
            raise StudioError("Ten moduł ma tylko diagnostykę; nie przejmuj obcego procesu")

    def refresh_service_controls(self) -> None:
        service = self.selected_service()
        with self.core.lock:
            job = self.core.jobs.get("service:" + service)
            owned = (job is not None and job.proc is not None and not job.done.is_set()
                     and job.proc.poll() is None)
        running = service == "runtime" and self.quick_runtime_ready
        managed = service in {"ollama", "gateway"}
        self.service_start_button.setEnabled((service == "runtime" and not running) or (managed and not owned))
        self.service_stop_button.setEnabled(running or (managed and owned))
        self.service_restart_button.setEnabled(running or (managed and owned))
        note = {
            "runtime": "kanoniczny daemon; Stop/Restart wymagają zweryfikowanej gotowości",
            "ollama": "Stop dotyczy wyłącznie procesu uruchomionego przez Studio",
            "gateway": "lokalny MCP 127.0.0.1, bez publicznej ekspozycji",
            "cloudflare": "publiczny HTTPS, tylko diagnostyka; wdrożenie i OAuth osobno",
            "supervisor": "tożsamość i heartbeat nadzorcy; bez przejmowania procesu",
            "memory": "oddzielna zdolność; stan techniczny nie potwierdza recall",
        }.get(service, "wybierz moduł")
        self.service_selected_label.setText(service.upper() + " — " + note if service else note)

    def refresh_services(self) -> None:
        """Explicit, read-only probes; no silent auto-start or PID adoption."""
        self.core.start_action("status")
        self.core.start_action("supervisor")
        self.core.probe("ollama")
        self.core.probe("gateway")
        if self.core.settings.cloudflare_url:
            self.core.probe("cloudflare")
        else:
            self.update_service_summary("cloudflare", "Nie skonfigurowano • brak adresu HTTPS")

    def _chat(self) -> None:
        layout = self.page("Czat lokalny", "Rozmowa przez runtime Jaźni i wybrany model Ollama. Tylko zaakceptowane odpowiedzi runtime pojawiają się jako wypowiedzi Łatki.")
        self.chat_state = QLabel("Rozłączony. Wybierz model w ustawieniach, uruchom runtime i Ollamę, a następnie połącz.")
        self.chat_state.setWordWrap(True)
        layout.addWidget(self.chat_state)
        model_row = QHBoxLayout()
        self.chat_model_selector = QComboBox()
        self.chat_model_selector.setAccessibleName("Model dla czatu lokalnego Ollama")
        self.chat_model_selector.addItem("Wykryj modele Ollama…", "")
        if self.core.settings.model:
            self.chat_model_selector.addItem(self.core.settings.model + " (z ustawień, niezweryfikowany)",
                                             self.core.settings.model)
            self.chat_model_selector.setCurrentIndex(1)
        model_row.addWidget(self.chat_model_selector, 1)
        self.button("Wykryj modele", lambda: self.core.probe("ollama"), model_row)
        self.button("Sprawdź generację", lambda: self.core.probe("ollama_generate"), model_row)
        self.button("Zapisz wybór", self.select_local_model, model_row)
        layout.addLayout(model_row)
        row = QHBoxLayout()
        self.button("Połącz", self.connect_local_chat, row)
        self.button("Rozłącz transport", lambda: self.core.stop_owned("chat"), row)
        self.button("Wznów wynik", self.resume_chat, row)
        layout.addLayout(row)
        self.conversation = QPlainTextEdit()
        self.conversation.setReadOnly(True)
        self.conversation.setAccessibleName("Historia lokalnej rozmowy")
        layout.addWidget(self.conversation, 2)
        self.message = QPlainTextEdit()
        self.message.setPlaceholderText("Twoja wiadomość…")
        self.message.setAccessibleName("Wiadomość do runtime Jaźni")
        self.message.setMaximumHeight(100)
        layout.addWidget(self.message)
        self.button("Wyślij", self.send_chat, layout)

    def select_local_model(self) -> None:
        """Only change future chat configuration, never an outstanding request."""
        chosen = self.chat_model_selector.currentData()
        if not isinstance(chosen, str) or not chosen:
            raise StudioError("Wybierz model z listy dostępnych modeli Ollama")
        chat = self.core.chat
        if chat is not None and (chat.pending or
                (chat.job is not None and not chat.job.done.is_set())):
            raise StudioError("Zakończ lub rozłącz obecną rozmowę przed zmianą modelu; nie porzucaj request_id")
        self.apply_settings(replace(self.core.settings, model=chosen))
        self.chat_state.setText("Wybrano model " + chosen + ". Połącz czat, aby sprawdzić rzeczywistą generację.")

    def connect_local_chat(self) -> None:
        """Never bypass the first-run model and matching daemon evidence via sidebar."""
        if not (self.quick_runtime_ready and self.quick_generation_ready
                and self.core.settings.model):
            raise StudioError(
                "Najpierw w Pulpicie sprawdź zgodność runtime oraz uruchom "
                "test generacji wybranego modelu Ollama."
            )
        self.core.connect_chat()

    def send_chat(self) -> None:
        if self.core.chat is None:
            raise StudioError("Najpierw połącz czat")
        text = self.message.toPlainText()
        request = self.core.chat.send(text)
        self.conversation.appendPlainText("Ty:\n" + text + "\n")
        self.message.clear()
        self.chat_state.setText("Oczekiwanie na wynik: " + request)

    def resume_chat(self) -> None:
        if self.core.chat is None:
            from .chat import ChatClient
            self.core.chat = ChatClient(self.core)
        self.core.chat.resume()

    def service(self, service: str, op: str) -> None:
        if service == "runtime":
            if op in {"stop", "restart"} and QMessageBox.question(self, "Runtime Jaźni", "Potwierdzić kanoniczny " + op + " runtime Jaźni?") != QMessageBox.StandardButton.Yes:
                return
            self.action(op)
            return
        if op in {"stop", "restart"} or service == "cloudflare":
            if QMessageBox.question(self, "Zmiana usługi",
                    "Wykonać " + op + " dla " + service + "?") != QMessageBox.StandardButton.Yes:
                return
        if op == "start":
            self.core.start_service(service)
        elif op == "stop":
            self.core.stop_owned("service:" + service)
        else:
            self.core.restart_service(service)
        self.show_log("service:" + service)

    def _diagnostics(self) -> None:
        layout = self.page("Diagnostyka", "Każdy krok ma osobny wynik, log i kod zakończenia. Pakiet zatrzymuje się przy błędzie.")
        for item in ACTIONS:
            row = QHBoxLayout()
            self.button(item.label, lambda key=item.key: self.action(key), row)
            note = QLabel(item.description)
            note.setWordWrap(True)
            row.addWidget(note, 2)
            layout.addLayout(row)
        self.button("Zapisz raport techniczny JSON…", self.export, layout)
        legend = QLabel("Zdarzenia — komunikaty dla operatora; Błędy — krótkie powody niepowodzeń; pełny dziennik — Ctrl+J.")
        legend.setWordWrap(True)
        layout.addWidget(legend)
        layout.addStretch()

    def _studios(self) -> None:
        layout = self.page("Studia Jaźni", "Wybierz Studio i operację, uzupełnij formularz, a następnie sprawdź i uruchom planowane działanie.")
        row = QHBoxLayout()
        self.studio_choice = QComboBox()
        for item in STUDIOS:
            if item.key in {"memory", "rebuild", "tests", "packages", "dependencies", "python"}:
                self.studio_choice.addItem(item.label, item.key)
        row.addWidget(self.studio_choice)
        self.button("Wczytaj operacje", self.load_studio_operations, row)
        layout.addLayout(row)
        self.operation = QComboBox()
        self.operation.currentIndexChanged.connect(self.render_operation)
        layout.addWidget(self.operation)
        self.operation_form = QFormLayout()
        layout.addLayout(self.operation_form)
        self.operation_widgets: dict[str, QWidget] = {}
        self.command_schema: list[dict] = []
        self.schema_key = ""
        self.preview_approved = ""
        self.preview_note = QLabel("Sprawdź plan polecenia przed wykonaniem operacji.")
        self.preview_note.setWordWrap(True)
        layout.addWidget(self.preview_note)
        self.button("Sprawdź plan (bez wykonania)", self.preview_operation, layout)
        self.execute_button = self.button("Wykonaj wybraną operację", self.execute_operation, layout)
        self.execute_button.setEnabled(False)
        self.studio_choice.currentIndexChanged.connect(self.reset_studio_operations)
        layout.addWidget(QLabel("Oddzielne klasyczne okna pozostają dostępne jako jawny wybór:"))
        for item in STUDIOS:
            row = QHBoxLayout()
            launch = self.button("Archiwalne / do przeglądu: " + item.label, lambda key=item.key: self.core.start_studio(key), row)
            entry = (self.core.root / (item.entry[1].replace(".", "/") + ".py")
                     if item.entry[0] == "-m" else self.core.root / item.entry[0])
            available = entry.is_file()
            launch.setEnabled(available)
            launch.setToolTip("Wymagany plik: " + str(entry))
            note = QLabel(item.description + (" • plik dostępny" if available else " • brak pliku w tym SYSTEM"))
            note.setWordWrap(True)
            row.addWidget(note, 2)
            layout.addLayout(row)
        layout.addStretch()

    def _configuration(self) -> None:
        from .configuration_view import ConfigurationPanel
        layout = self.page(
            "Konfiguracja Qt",
            "Profil przyszłych uruchomień — walidacja, mapa ścieżek, "
            "kontrolowany podgląd, zapis CAS i przywracanie kopii. Bez aktywacji daemona.",
        )
        self.configuration_panel = ConfigurationPanel(self.core)
        layout.addWidget(self.configuration_panel)

    def _version_studio(self) -> None:
        from .version_view import VersionPanel
        layout = self.page(
            "Wersje Qt",
            "Natywna kontrola wersji (odczyt bez zapisu). "
            "Zmiany wydania i przywracanie metadanych nadal wymagają osobnego przeglądu.",
        )
        self.version_panel = VersionPanel(self.core)
        layout.addWidget(self.version_panel)

    def _tests_catalog(self) -> None:
        from .test_catalog_view import TestCatalogPanel
        layout = self.page(
            "Katalog testów",
            "Natywny podgląd Test Studio: filtrowanie testów i ich oczekiwań bez uruchamiania lub edycji.",
        )
        self.tests_catalog_panel = TestCatalogPanel(self.core.root)
        layout.addWidget(self.tests_catalog_panel)

    def _local_acceptance(self) -> None:
        from .local_acceptance_view import LocalAcceptancePanel
        layout = self.page(
            "TPA",
            "Testy przepuszczania aktualizacji — bezpieczne podtesty w izolacji + ręczny odbiór 22 scenariuszy. Automatyczny PASS nie zalicza bramki.",
            compact=True,
        )
        self.local_acceptance_panel = LocalAcceptancePanel(self.core.root, python=self.core.settings.python)
        self.local_acceptance_panel.models_requested.connect(lambda: self.core.probe("ollama"))
        self.local_acceptance_panel.dependency_requested.connect(self.open_tpa_dependencies)
        layout.addWidget(self.local_acceptance_panel)

    def open_tpa_dependencies(self) -> None:
        self.navigate("Studia Jaźni")
        index = self.studio_choice.findData("dependencies")
        if index >= 0:
            self.studio_choice.setCurrentIndex(index)
            self.load_studio_operations()
        self.statusBar().showMessage("Przygotuj profil testowy dla Pythona: " + self.local_acceptance_panel.python_field.text() + "; instalacja wymaga podglądu i potwierdzenia.")

    def _memory(self) -> None:
        from .memory_view import MemoryPanel
        layout = self.page("Dowody MEMORY", "Odczytowe P1: role baz, porównanie i niezależna gotowość runtime.")
        self.memory_panel = MemoryPanel(self.core, self.guard)
        layout.addWidget(self.memory_panel)

    def reset_studio_operations(self, _index: int = -1) -> None:
        self.invalidate_operation_preview()
        self.schema_key = ""
        self.command_schema = []
        self.operation.clear()
        self.execute_button.setEnabled(False)
        self.render_operation()

    def load_studio_operations(self) -> None:
        self.reset_studio_operations()
        self.core.studio_helper("schema", str(self.studio_choice.currentData()))

    def render_operation(self, _index: int = 0) -> None:
        self.invalidate_operation_preview()
        while self.operation_form.rowCount():
            self.operation_form.removeRow(0)
        self.operation_widgets.clear()
        index = self.operation.currentIndex()
        if not 0 <= index < len(self.command_schema):
            return
        for field in self.command_schema[index]["fields"]:
            if field["flag"]:
                widget = QCheckBox()
            elif field["choices"]:
                widget = QComboBox()
                widget.addItems([""] + field["choices"])
            elif field["append"] or field["nargs"] in ("+", "*"):
                widget = QPlainTextEdit()
                widget.setPlaceholderText("Jeden argument w każdym wierszu")
                widget.setMaximumHeight(80)
            else:
                widget = QLineEdit()
            widget.setToolTip(str(field["help"]))
            widget.setAccessibleName(str(field["help"]))
            self.operation_widgets[field["id"]] = widget
            if isinstance(widget, QCheckBox):
                widget.toggled.connect(self.invalidate_operation_preview)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self.invalidate_operation_preview)
            elif isinstance(widget, QPlainTextEdit):
                widget.textChanged.connect(self.invalidate_operation_preview)
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.invalidate_operation_preview)
            label = field["dest"].replace("_", " ") + (" *" if field["required"] else "")
            self.operation_form.addRow(label, widget)

    def invalidate_operation_preview(self, *_args: object) -> None:
        self.preview_approved = ""
        if hasattr(self, "preview_note"):
            self.preview_note.setText("Plan niezatwierdzony; sprawdź go po każdej zmianie.")

    def operation_payload(self) -> dict:
        index = self.operation.currentIndex()
        if not 0 <= index < len(self.command_schema) or not self.schema_key:
            raise StudioError("Najpierw wczytaj operacje wybranego Studio")
        selected = self.command_schema[index]
        values: dict = {}
        for key, widget in self.operation_widgets.items():
            if isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                values[key] = widget.currentText()
            elif isinstance(widget, QPlainTextEdit):
                entries = [line for line in widget.toPlainText().splitlines() if line]
                if entries:
                    values[key] = entries
            elif isinstance(widget, QLineEdit):
                values[key] = widget.text()
        return {"path": selected["path"], "values": values}

    def preview_operation(self) -> None:
        spec = self.operation_payload()
        self.invalidate_operation_preview()
        self.core.studio_helper("preview", self.schema_key, spec)
        self.preview_note.setText("Walidacja planu przez kanoniczny parser trwa…")

    def execute_operation(self) -> None:
        spec = self.operation_payload()
        if not self.preview_approved or preview_fingerprint(spec) != self.preview_approved:
            raise StudioError("Brak aktualnego zatwierdzonego planu. Sprawdź go ponownie.")
        if QMessageBox.question(self, "Uruchom operację",
                "Wykonać zatwierdzony plan " + " / ".join(spec["path"]) +
                "? Operacja może zapisać dane. To nie jest symulacja."
                ) != QMessageBox.StandardButton.Yes:
            return
        self.invalidate_operation_preview()
        self.core.studio_helper("execute", self.schema_key, spec)

    def _settings(self) -> None:
        layout = self.page("Ustawienia", "Profil lokalny Studio jest ignorowany przez Git. Sekrety nie są polami tego profilu. Zmiana ścieżek nie przejmuje działających procesów.")
        self.settings_search = QLineEdit()
        self.settings_search.setPlaceholderText("Szukaj ustawienia…")
        layout.addWidget(self.settings_search)
        self.settings_category = QComboBox()
        self.settings_category.addItems(["Wszystkie", "Środowisko", "Runtime", "Modele", "MCP", "Cloudflare", "Bezpieczeństwo", "Wygląd"])
        layout.addWidget(self.settings_category)
        self.settings_hint = QLabel("Zmiany dotyczą przyszłych uruchomień. Nie uruchamiają usług.")
        self.settings_hint.setWordWrap(True)
        layout.addWidget(self.settings_hint)
        form = QFormLayout()
        self.settings_form = form
        labels = {"python": "Interpreter Python", "mcp_python": "Python MCP (opcjonalny, z mcp/uvicorn)", "ollama": "Plik Ollama", "cloudflared": "Plik cloudflared",
                  "tunnel_config": "Konfiguracja tunelu (plik)", "tunnel_id": "Nazwa / UUID tunelu",
                  "model": "Model Ollama", "accent": "Kolor własny (#RRGGBB)"}
        labels["cloudflare_url"] = "Adres HTTPS Workera Cloudflare"
        labels["mcp_port"] = "Port lokalnej bramy MCP (127.0.0.1)"
        labels["daemon_url"] = "URL lokalnego daemona (127.0.0.1)"
        labels["secrets_file"] = "Plik sekretów JSON (ignorowany przez Git)"
        for key, label in labels.items():
            field = QLineEdit(str(getattr(self.core.settings, key)))
            if key == "model":
                field.setReadOnly(True)
                field.setToolTip("Nazwa tylko z listy wykrytych lokalnie modeli Ollama; nie wpisuj jej ręcznie.")
            field.setAccessibleName(label)
            self.fields[key] = field
            form.addRow(label, field)
        self.settings_model_selector = QComboBox()
        self.settings_model_selector.setEditable(False)
        self.settings_model_selector.addItem("Wykryj zainstalowane modele…", "")
        self.settings_model_selector.setAccessibleName("Wybierz zainstalowany model Ollama")
        self.settings_model_selector.currentIndexChanged.connect(self.settings_model_selected)
        form.addRow("Wybierz model z Ollamy", self.settings_model_selector)
        model_refresh = QPushButton("Wykryj modele Ollama")
        model_refresh.clicked.connect(lambda _checked=False: self.core.probe("ollama"))
        form.addRow("Odśwież modele", model_refresh)
        self.theme = QComboBox()
        for label, key in THEME_CHOICES:
            self.theme.addItem(label, key)
        self.theme.setCurrentIndex(self.theme.findData(self.core.settings.theme))
        form.addRow("Motyw", self.theme)
        self.profile_mode = QComboBox()
        self.profile_mode.addItem("Bez dodatkowego profilu", "off")
        self.profile_mode.addItem("Walidowany profil operator", "operator")
        self.profile_mode.setCurrentIndex(1 if self.core.settings.runtime_profile == "operator" else 0)
        form.addRow("Przyszłe uruchomienia runtime", self.profile_mode)
        layout.addLayout(form)
        self.button("Wybierz kolor z palety…", self.choose_custom_color, layout)
        self.button("Uzupełnij bezpieczne wartości domyślne (bez zapisu)", self.fill_discovered_defaults, layout)
        self.button("Zapisz i zastosuj", self.save, layout)
        self.button("Przywróć domyślne w formularzu", self.reset_settings_draft, layout)
        self.settings_search.textChanged.connect(self.filter_settings)
        self.settings_category.currentIndexChanged.connect(self.filter_settings)
        for field in self.fields.values():
            field.textChanged.connect(self.settings_changed)
        self.theme.currentTextChanged.connect(self.settings_changed)
        self.profile_mode.currentIndexChanged.connect(self.settings_changed)
        layout.addWidget(QLabel("Profile środowiska runtime są obsługiwane przez kanoniczne Studio Konfiguracji."))
        self.button("Klasyczne Studio Konfiguracji (do przeglądu)", lambda: self.core.start_studio("configuration"), layout)
        self.button("Wczytaj profil środowiska runtime", lambda: self.core.studio_helper("profile-read"), layout)
        self.profile_form = QFormLayout()
        self.profile_widgets: dict[str, QLineEdit | QComboBox] = {}
        self.profile_digest: str | None = None
        layout.addLayout(self.profile_form)
        self.button("Zapisz profil przyszłych uruchomień runtime", self.save_profile, layout)
        layout.addStretch()

    def settings_model_selected(self, _index: int) -> None:
        selected = self.settings_model_selector.currentData()
        if isinstance(selected, str) and selected:
            self.fields["model"].setText(selected)

    def set_settings_installed_models(self, names: object) -> None:
        items = sorted({name for name in names if isinstance(name, str) and name.strip()}) if isinstance(names, list) else []
        selected = self.fields["model"].text().strip()
        self.settings_model_selector.blockSignals(True)
        self.settings_model_selector.clear()
        self.settings_model_selector.addItem("Wybierz zainstalowany model…" if items else "Brak dostępnych modeli", "")
        for name in items:
            self.settings_model_selector.addItem(name, name)
        idx = self.settings_model_selector.findData(selected)
        self.settings_model_selector.setCurrentIndex(idx if idx >= 0 else 0)
        self.settings_model_selector.blockSignals(False)

    def fill_discovered_defaults(self) -> None:
        """Suggest detected executables only in empty draft fields; never start services."""
        found = discovery(self.core.settings)
        changed: list[str] = []
        for name in ("python", "ollama", "cloudflared"):
            candidate = found.get(name)
            if (not self.fields[name].text().strip()
                    and isinstance(candidate, str) and Path(candidate).is_file()):
                self.fields[name].setText(candidate)
                changed.append(name)
        self.statusBar().showMessage(
            "Propozycje w formularzu (nie zapisano): " + (", ".join(changed) if changed else "brak nowych")
        )

    def choose_custom_color(self) -> None:
        """Only the user's explicit acceptance changes the draft settings."""
        initial = QColor(self.fields["accent"].text())
        if not initial.isValid():
            initial = QColor(self.core.settings.accent)
        selected = QColorDialog.getColor(initial, self, "Kolor akcentu Jaźni")
        if selected.isValid():
            self.fields["accent"].setText(selected.name())
            self.theme.setCurrentText("custom")

    def save_profile(self) -> None:
        if not self.profile_widgets:
            raise StudioError("Najpierw wczytaj profil środowiska")
        if QMessageBox.question(self, "Profil środowiska", "Zapisać walidowany profil przyszłych uruchomień? Działający daemon zachowuje swoją konfigurację.") != QMessageBox.StandardButton.Yes:
            return
        values = {key: widget.currentText() if isinstance(widget, QComboBox) else widget.text()
                  for key, widget in self.profile_widgets.items()}
        self.core.studio_helper("profile-save", data={"values": {k: v for k, v in values.items() if v}, "digest": self.profile_digest})

    def save(self) -> None:
        data = {k: field.text().strip() for k, field in self.fields.items()}
        data["theme"] = str(self.theme.currentData())
        data["runtime_profile"] = str(self.profile_mode.currentData())
        settings = Settings.validate(data)
        self.apply_settings(settings)

    def apply_settings(self, settings: Settings, *, appearance_only: bool = False) -> None:
        self.digest = save_settings(self.core.root, settings, self.digest)
        self.core.settings = settings
        if not appearance_only:
            self.quick_runtime_ready = False
            self.quick_generation_ready = False
            self.refresh_quick_start()
        for key, field in self.fields.items():
            field.setText(str(getattr(settings, key)))
        self.theme.setCurrentIndex(self.theme.findData(settings.theme))
        self.style_selector.blockSignals(True)
        self.style_selector.setCurrentIndex(self.style_selector.findData(settings.theme))
        self.style_selector.blockSignals(False)
        self.profile_mode.setCurrentIndex(1 if settings.runtime_profile == "operator" else 0)
        self.apply_theme()
        self.settings_baseline = self.settings_draft()
        self.settings_hint.setText("Zapisano. Konfiguracja usług obowiązuje przy ich kolejnym uruchomieniu.")
        self.statusBar().showMessage("Zapisano ustawienia Studio")

    def select_style(self, theme: str) -> None:
        index = self.style_selector.findData(theme)
        if index >= 0:
            self.style_selector.setCurrentIndex(index)

    def style_selected(self, index: int) -> None:
        """Persist a visual profile only; do not rewrite unsaved configuration."""
        selected = self.style_selector.itemData(index)
        if not isinstance(selected, str) or selected == self.core.settings.theme:
            return
        if self.settings_draft() != self.settings_baseline:
            self.style_selector.blockSignals(True)
            self.style_selector.setCurrentIndex(self.style_selector.findData(self.core.settings.theme))
            self.style_selector.blockSignals(False)
            self.statusBar().showMessage("Najpierw zapisz lub odrzuć niezapisane ustawienia.", 5000)
            return
        self.guard(lambda: self.apply_settings(replace(self.core.settings, theme=selected), appearance_only=True))

    def apply_theme(self) -> None:
        app = QApplication.instance()
        system_dark = (isinstance(app, QApplication)
                       and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        from .visual_system import VisualSystem
        if not hasattr(self, "visual_system"):
            self.visual_system = VisualSystem(self)
        self.visual_system.apply(self.core.settings.theme, self.core.settings.accent, system_dark=system_dark)

    def _about(self) -> None:
        layout = self.page("O programie", "Studio Jaźni Starter  " + STUDIO_VERSION)
        text = QLabel("Projekt: Jaźń • repozytorium SmuklyLew/jazn_latka\n"
                      "Autor / opiekun projektu: SmuklyLew.\n"
                      "Studio jest aplikacją operatorską; runtime pozostaje właścicielem pamięci, tożsamości i finalizacji.\n\n"
                      "W repozytorium bazowym nie znaleziono pliku LICENSE. Studio nie nadaje projektowi nowej licencji.\n"
                      "Qt for Python / PySide6: informacje o licencjach i zależnościach należy dołączyć do dystrybucji.\n\n"
                      "Stan wydania: alpha 0.3.0a1. Pełna migracja i testy P4/P5 pozostają otwarte.")
        text.setWordWrap(True)
        layout.addWidget(text)
        self.button("Źródła projektu", lambda: QDesktopServices.openUrl(QUrl("https://github.com/SmuklyLew/jazn_latka")), layout)
        self.button("Licencje Qt", lambda: QDesktopServices.openUrl(QUrl("https://doc.qt.io/qtforpython-6/licenses.html")), layout)
        layout.addStretch()

    def update_current_section(self, row: int) -> None:
        item = self.nav.item(row)
        if item is not None:
            self.current_section.setText(item.text())

    def toggle_sidebar(self) -> None:
        visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(visible)
        if hasattr(self, "workbench") and self.workbench.compact_sidebar is not None:
            self.workbench.compact_sidebar = visible
        self.menu_button.setToolTip("Ukryj boczną nawigację (Ctrl+B)" if visible
                                    else "Pokaż boczną nawigację (Ctrl+B)")
        if visible:
            self.nav.setFocus()

    def set_logs_visible(self, visible: bool) -> None:
        """One operator dock in production; no duplicate log surface."""
        if self.unified_operator_mode:
            self.logs_user_hidden = not visible
            self.tabs.hide()
            if visible:
                self.workspace.show(1)
            else:
                self.workspace.dock.hide()
            self.log_toggle.setText("Ukryj panel" if visible else "Pokaż panel")
            return
        self.logs_user_hidden = not visible
        if visible:
            self.workspace.dock.hide()
            if not self.tabs.count():
                self.log_view("Zdarzenia")
        self.tabs.setVisible(visible)
        self.log_toggle.setText("Ukryj logi" if visible else "Pokaż logi")
        if visible:
            self.content_splitter.setSizes([max(1, self.height() * 2 // 3),
                                            max(140, self.height() // 3)])
            self.tabs.currentWidget().setFocus()

    def toggle_logs(self) -> None:
        self.set_logs_visible(not self.workspace.dock.isVisible() if self.unified_operator_mode else self.tabs.isHidden())

    def show_log(self, key: str) -> QPlainTextEdit:
        """Select a source in the shared output pane where available."""
        view = self.log_view(key)
        if self.unified_operator_mode:
            self.workspace.open_log_source(key)
            return view
        self.tabs.setCurrentWidget(view)
        self.set_logs_visible(True)
        return view

    def update_service_summary(self, service: str, detail: str) -> None:
        """Mirror the same observed state; never infer readiness from a PID."""
        if service in self.statuses:
            self.statuses[service].setText(detail)
        if service in self.dashboard_statuses:
            self.dashboard_statuses[service].setText(service.upper() + ": " + detail)

    def log_view(self, key: str) -> QPlainTextEdit:
        """Register a data sink; incoming events never change panel visibility."""
        if key not in self.logs:
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.document().setMaximumBlockCount(2500)
            view.setAccessibleName("Log " + key)
            self.logs[key] = view
            if not self.unified_operator_mode:
                self.tabs.addTab(view, key)
        return self.logs[key]

    def poll(self) -> None:
        for _ in range(150):
            # A saturated log queue must not delay terminal state / chat-final
            # delivery. Overflow critical events are consumed first.
            try:
                key, kind, value = self.core.critical_events.get_nowait()
            except queue.Empty:
                try:
                    key, kind, value = self.core.events.get_nowait()
                except queue.Empty:
                    break
            self.workspace.observe(key, kind, value)
            if kind == "log":
                self.log_view(key).appendPlainText(str(value))
            elif kind == "memory_report":
                self.memory_panel.receive(key, value)
            elif kind == "status_summary":
                for name, label in self.dashboard_summary.items():
                    label.setText(self.core.redactor.text(str(value.get(name, "niezweryfikowane"))))
                self.quick_memory_status.setText(
                    "MEMORY: " + self.core.redactor.text(str(value.get("continuity", "niezweryfikowana")))
                )
                self.memory_observed = True
                self.update_service_summary("memory", str(value.get("memory", "niezweryfikowane")))
            elif kind == "evidence":
                yes = lambda flag: "tak" if flag else "niepotwierdzone"
                ready = (all(value.get(flag) is True for flag in (
                    "endpoint_reachable", "process_identity_confirmed",
                    "endpoint_identity_matches", "heartbeat_fresh",
                    "conversation_ready",
                )) and value.get("root_matches") is not False
                    and value.get("version_matches") is not False)
                state = str(value.get("active_state") or "niepotwierdzony")
                heading = ("Pracuje — zweryfikowany runtime" if ready else
                           "Zatrzymane — runtime nieaktywny" if state in {"dead", "stopped", "inactive"} else
                           "Gotowość niezweryfikowana")
                detail = (heading + " • endpoint: " + yes(value.get("endpoint_reachable")) +
                    " • tożsamość procesu: " + yes(value.get("process_identity_confirmed")) +
                    " • gotowość rozmowy: " + yes(value.get("conversation_ready")))
                self.quick_runtime_ready = ready and state == "active_trusted"
                if not self.quick_runtime_ready:
                    self.quick_generation_ready = False
                self.refresh_quick_start()
                if value.get("root_matches") is False:
                    detail += " • BŁĄD: daemon należy do innego katalogu (np. aktywnego master)"
                if value.get("version_matches") is False:
                    detail += " • BŁĄD: uruchomiony daemon ma inną wersję SYSTEM"
                self.evidence.setText("Runtime: " + detail)
                self.update_service_summary("runtime", detail)
                # Header and sidebar show the *same* most recent runtime observation.
                self.sidebar_footnote.setText(
                    "Runtime • zweryfikowany; odpowiedź wymaga akceptacji"
                    if ready else "Runtime • gotowość niezweryfikowana"
                )
                self.workbench_status.setText(
                    "Lokalne Studio • runtime zweryfikowany"
                    if ready else "Lokalne Studio • status niezweryfikowany"
                )
            elif kind == "supervisor_evidence":
                self.supervisor_observation = dict(value) if isinstance(value, dict) else {}
                detail = ("Pracuje • potwierdzona tożsamość i heartbeat"
                          if self.supervisor_observation.get("ready") is True
                          else "Niezweryfikowany • sprawdź tożsamość i heartbeat")
                self.update_service_summary("supervisor", detail)
            elif kind == "probe":
                if key == "probe:ollama_generate":
                    self.quick_generation_ready = (
                        value.get("generation_verified") is True
                        and value.get("selected_model_present") is True
                    )
                    self.refresh_quick_start()
                service = value.get("service")
                if service in self.statuses:
                    if value.get("ready") is True:
                        detail = "Pracuje • endpoint i gotowość usługi potwierdzone; funkcja wymaga osobnego testu"
                    elif value.get("ready") is False:
                        detail = "BŁĄD • usługa nie zgłasza gotowości"
                    elif service == "ollama":
                        detail = ("Ollama API • generacja modelu potwierdzona; finalizacja Jaźni osobno"
                                  if value.get("generation_verified") is True else
                                  "Endpoint odpowiada • generacja odpowiedzi niezweryfikowana")
                    else:
                        detail = "Odpowiedź testu • gotowość niezweryfikowana"
                    self.update_service_summary(str(service), detail)
                if service == "ollama":
                    names = value.get("models", [])
                    if isinstance(names, list):
                        self.chat_model_selector.blockSignals(True)
                        self.chat_model_selector.clear()
                        self.chat_model_selector.addItem("Wybierz dostępny model…", "")
                        for name in names:
                            if isinstance(name, str):
                                self.chat_model_selector.addItem(name, name)
                        index = self.chat_model_selector.findData(self.core.settings.model)
                        self.chat_model_selector.setCurrentIndex(index if index >= 0 else 0)
                        self.chat_model_selector.blockSignals(False)
                    if isinstance(names, list):
                        self.local_acceptance_panel.set_installed_models(names, self.core.settings.model)
                        self.set_settings_installed_models(names)
                        if self.setup_wizard is not None:
                            self.setup_wizard.set_installed_models(names)
                    if not names:
                        self.chat_state.setText("Ollama odpowiada, lecz nie widzi żadnego modelu. Sprawdź OLLAMA_MODELS i użytkownika usługi; niczego automatycznie nie pobierano.")
                    else:
                        self.chat_state.setText(
                            "Modele Ollama: " + ", ".join(names) + ". Generacja: " +
                            ("potwierdzona w API (nie jest to odpowiedź Jaźni)." if value.get("generation_verified") is True
                             else "niezweryfikowana.")
                        )
            elif kind == "chat_state":
                self.chat_state.setText(str(value))
            elif kind == "chat_final":
                self.conversation.appendPlainText(value["text"] + "\n")
                # A checkpoint is acknowledged only after the actual GUI append.
                # Without this ACK a restart can poll the same canonical result.
                try:
                    if self.core.chat is None:
                        raise StudioError("Transport rozmowy nie jest dostępny")
                    self.core.chat.acknowledge_final(value["request_id"])
                except (OSError, StudioError):
                    self.chat_state.setText("Wynik pokazano, lecz nie zapisano potwierdzenia. Wznów ten sam request_id.")
                else:
                    self.core.confirm_visible_turn(value)
                    self.chat_state.setText("Zaakceptowano wynik • tura " + str(value["turn_id"]) + " • ślad " + str(value["trace_id"]))
            elif kind == "helper":
                if key == "helper:version-inspect:":
                    self.version_panel.receive(value)
                    continue
                if key in {
                    "helper:profile-paths:", "helper:profile-validate:",
                    "helper:profile-preview:", "helper:profile-restore:", "helper:profile-migrate:",
                }:
                    self.configuration_panel.receive(key, value)
                    continue
                if key in {"helper:profile-read:", "helper:profile-save:"}:
                    self.configuration_panel.receive(key, value)
                    # Preserve the existing Settings profile editor compatibility.
                if key.startswith("helper:preview:"):
                    if key.removeprefix("helper:preview:") != self.schema_key:
                        continue
                    try:
                        current = preview_fingerprint(self.operation_payload())
                    except StudioError:
                        continue
                    if (value.get("schema") == "jazn_studio_command_preview/v1"
                            and value.get("fingerprint") == current
                            and value.get("execution_performed") is False
                            and value.get("requires_confirmation") is True):
                        self.preview_approved = current
                        self.preview_note.setText("Plan sprawdzony: " + " / ".join(value["path"]) +
                            " • argumentów: " + str(value["argument_count"]) +
                            ". Przed wykonaniem zostaniesz poproszony o potwierdzenie.")
                    continue
                if key.startswith("helper:schema:"):
                    if key.split(":", 2)[2] != self.studio_choice.currentData():
                        continue
                    self.schema_key = key.split(":", 2)[2]
                    self.command_schema = value
                    self.operation.blockSignals(True)
                    self.operation.clear()
                    self.operation.addItems([" / ".join(c["path"]) for c in value])
                    self.operation.blockSignals(False)
                    self.render_operation()
                    self.execute_button.setEnabled(bool(value))
                elif key in {"helper:profile-read:", "helper:profile-save:"}:
                    self.profile_digest = value["digest"]
                    while self.profile_form.rowCount():
                        self.profile_form.removeRow(0)
                    self.profile_widgets.clear()
                    for field in value["fields"]:
                        if field["choices"]:
                            widget = QComboBox()
                            widget.addItems([""] + field["choices"])
                            widget.setCurrentText(value["values"].get(field["key"], ""))
                        else:
                            widget = QLineEdit(value["values"].get(field["key"], ""))
                        widget.setToolTip(field["hint"])
                        self.profile_widgets[field["key"]] = widget
                        self.profile_form.addRow(field["title"], widget)
            elif kind == "state":
                if key == "helper:version-inspect:":
                    self.version_panel.receive_state(value)
                if key.startswith("helper:profile-"):
                    self.configuration_panel.receive_state(key, value)
                if value.get("state") in {"succeeded", "failed", "stopped"}:
                    result = ("Ukończono" if value["state"] == "succeeded"
                              else "Zatrzymano" if value["state"] == "stopped" else "BŁĄD")
                    reason = self.core.redactor.text(str(value.get("error") or ""))
                    line = key + " • " + result + ((" • " + reason) if reason else "")
                    self.dashboard_last_operation.setText("Ostatnia operacja: " + line)
                    self.log_view("Zdarzenia").appendPlainText(line)
                    if value["state"] == "failed":
                        self.log_view("Błędy").appendPlainText(line)
                if key.startswith("service:ollama"):
                    self.quick_generation_ready = False
                    self.refresh_quick_start()
                if key in {"start", "stop", "restart"}:
                    # A lifecycle transition invalidates previously observed readiness.
                    self.quick_runtime_ready = False
                    self.quick_generation_ready = False
                    self.refresh_quick_start()
                if key.startswith("probe:ollama_generate") and value.get("state") == "failed":
                    self.quick_generation_ready = False
                    self.refresh_quick_start()
                if key.startswith("memory:p1:"):
                    self.memory_panel.receive_state(key, value)
                self.statusBar().showMessage(key + ": " + value["state"] + (" / " + value["error"] if value["error"] else ""))
                service = key.removeprefix("service:")
                if service in self.statuses and key.startswith("service:"):
                    state = str(value["state"])
                    if state == "failed":
                        detail = "BŁĄD • " + str(value.get("error") or "niepowodzenie")
                    elif state == "stopped":
                        detail = "Zatrzymane • proces należący do Studio; stan obcej usługi niezweryfikowany"
                    else:
                        detail = ("Pracuje proces" if state == "running" else "Proces: " + state) + " • PID " + str(value.get("pid")) + " • gotowość funkcji niezweryfikowana"
                    self.update_service_summary(service, detail)
                elif key in {"start", "stop", "restart"}:
                    state = str(value["state"])
                    if state == "failed":
                        detail = "BŁĄD • " + str(value.get("error") or "operacja nieudana")
                    else:
                        detail = "Operacja " + key + ": " + state + " • odśwież status, aby potwierdzić gotowość"
                    self.update_service_summary("runtime", detail)
                elif key == "supervisor" and value["state"] == "failed":
                    self.supervisor_observation = {}
                    self.update_service_summary("supervisor", "BŁĄD odczytu • niezweryfikowany")
                elif key.startswith("probe:") and value["state"] == "failed":
                    service = key.removeprefix("probe:")
                    self.update_service_summary(service, "BŁĄD testu • " + str(value.get("error") or "niepowodzenie"))
        with self.core.lock:
            snapshots = [j.snapshot() for j in self.core.jobs.values()]
        self.processes.setPlainText(json.dumps(snapshots, ensure_ascii=False, indent=2))
        self.workspace.refresh()
        self.refresh_service_table()
        self.refresh_service_controls()
        self.refresh_connection_checks()
        if self.pages.currentWidget() is self.developer_page:
            public = {"jobs": snapshots, "services": self.workspace.observations,
                      "accepted_visible_turn": True if self.core.accepted_turn_proof else None}
            self.developer_details.setPlainText(self.core.redactor.text(json.dumps(public, ensure_ascii=False, indent=2)))

    def navigate(self, title: str) -> None:
        if title == "MCP i ChatGPT":  # Legacy navigation callers.
            title = "Połączenie z ChatGPT"
        self.section_search.clear()
        for row in range(self.nav.count()):
            if self.nav.item(row).text() == title:
                self.nav.setCurrentRow(row)
                return

    def filter_navigation(self, query: str) -> None:
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            item.setHidden(query.casefold().strip() not in item.text().casefold())

    def select_search_result(self) -> None:
        for row in range(self.nav.count()):
            if not self.nav.item(row).isHidden():
                self.nav.setCurrentRow(row)
                return

    def _workspace_menu(self) -> None:
        from .workbench_shell import WorkbenchShell
        self.workbench = WorkbenchShell(self)

    def switch_sidebar(self) -> None:
        right = self.shell_splitter.indexOf(self.sidebar) == 0
        self.shell_splitter.insertWidget(1 if right else 0, self.sidebar)
        self.sidebar.show()

    def reset_layout(self) -> None:
        from .core import Settings
        self.shell_splitter.insertWidget(0, self.sidebar)
        self.sidebar.show()
        self.shell_splitter.setSizes([214, 1026])
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.workspace.dock)
        self.workspace.dock.setFloating(False)
        self.workspace.dock.hide()
        self.set_logs_visible(False)
        self.content_splitter.setSizes([max(1, self.height() - 140), 140])
        self.apply_theme()

    def restore_layout(self) -> None:
        if self.smoke:
            return
        from .workspace_layout import load_layout
        try:
            data = load_layout(self.core.root)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage("Układ odrzucony; użyto domyślnego: " + type(exc).__name__)
            return
        self.layout_state = data
        geometry = self.screen().availableGeometry()
        self.resize(min(data.get("width", 1240), geometry.width()), min(data.get("height", 840), geometry.height()))
        if data.get("sidebar_right"):
            self.switch_sidebar()
        self.sidebar.setVisible(data.get("sidebar_visible", True))
        areas = [Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea,
                 Qt.DockWidgetArea.TopDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea]
        self.addDockWidget(areas[data.get("dock_area", 3)], self.workspace.dock)
        self.workspace.dock_height = data.get("dock_height", 300)
        self.workspace.tabs.setCurrentIndex(min(data.get("operator_tab", 0), self.workspace.tabs.count() - 1))
        self.workspace.dock.setVisible(data.get("dock_visible", False))
        if self.unified_operator_mode:
            self.tabs.hide()
        for title in data.get("open_sections", []):
            self.navigate(title)
        for key, splitter in (("shell_sizes", self.shell_splitter), ("content_sizes", self.content_splitter)):
            if key in data:
                splitter.setSizes(data[key])

    def persist_layout(self) -> None:
        from .workspace_layout import SCHEMA, save_layout
        areas = [Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea,
                 Qt.DockWidgetArea.TopDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea]
        area = self.dockWidgetArea(self.workspace.dock)
        self.layout_state = {"schema": SCHEMA, "width": self.width(), "height": self.height(),
                             "sidebar_right": self.shell_splitter.indexOf(self.sidebar) == 1,
                             "sidebar_visible": self.sidebar.isVisible() if self.workbench.compact_sidebar is None else self.workbench.compact_sidebar,
                             "dock_visible": self.workspace.dock.isVisible(),
                             "dock_height": max(180, min(3000, self.workspace.dock.height() if self.workspace.dock.isVisible() else self.workspace.dock_height)),
                             "operator_tab": self.workspace.tabs.currentIndex(),
                             "dock_area": areas.index(area) if area in areas else 3,
                             "shell_sizes": self.shell_splitter.sizes(),
                             "content_sizes": self.content_splitter.sizes(),
                             "active_section": self.current_section.text(),
                             "open_sections": [self.workbench.section_tabs.tabText(i) for i in range(self.workbench.section_tabs.count())],
                             "setup_scope": self.layout_state.get("setup_scope", "")}
        save_layout(self.core.root, self.layout_state)

    def setup_completed(self, scope: str) -> None:
        self.layout_state["setup_scope"] = scope
        self.persist_layout()

    def open_setup(self) -> None:
        from .first_run import SetupWizard
        if self.setup_wizard is None or not self.setup_wizard.isVisible():
            self.setup_wizard = SetupWizard(self.core, self.apply_settings, self.setup_completed, self)
        self.setup_wizard.show()
        self.setup_wizard.raise_()

    def settings_draft(self) -> dict[str, str]:
        values = {key: field.text().strip() for key, field in self.fields.items()}
        values["theme"] = str(self.theme.currentData())
        values["runtime_profile"] = str(self.profile_mode.currentData())
        return values

    def settings_changed(self, *_args: object) -> None:
        if hasattr(self, "settings_baseline"):
            dirty = self.settings_draft() != self.settings_baseline
            self.settings_hint.setText("Niezapisane zmiany. Ustawienia usług wymagają ponownego uruchomienia usługi." if dirty else
                                       "Formularz zgodny z ostatnio zapisanym profilem.")

    def reset_settings_draft(self) -> None:
        defaults = Settings()
        for key, field in self.fields.items():
            field.setText(str(getattr(defaults, key)))
        self.theme.setCurrentIndex(self.theme.findData(defaults.theme))
        self.profile_mode.setCurrentIndex(0)
        self.settings_model_selector.setCurrentIndex(0)

    def filter_settings(self, *_args: object) -> None:
        categories = {"model_selector": "Modele", "python": "Środowisko", "mcp_python": "Środowisko", "ollama": "Modele",
                      "model": "Modele", "daemon_url": "Runtime", "mcp_port": "MCP",
                      "cloudflared": "Cloudflare", "tunnel_config": "Cloudflare", "tunnel_id": "Cloudflare",
                      "cloudflare_url": "Cloudflare", "secrets_file": "Bezpieczeństwo", "accent": "Wygląd"}
        query = self.settings_search.text().casefold().strip()
        category = self.settings_category.currentText()
        widgets = {**self.fields, "model_selector": self.settings_model_selector, "theme": self.theme, "runtime_profile": self.profile_mode}
        categories.update({"theme": "Wygląd", "runtime_profile": "Runtime"})
        for key, widget in widgets.items():
            label = self.settings_form.labelForField(widget)
            title = label.text() if isinstance(label, QLabel) else key
            visible = (category == "Wszystkie" or categories.get(key) == category) and query in (key + " " + title).casefold()
            widget.setVisible(visible)
            if label is not None:
                label.setVisible(visible)

    def _models(self) -> None:
        layout = self.page("Modele AI", "Adapter generacyjny i daemon są osobnymi składnikami. null_model_adapter nie generuje odpowiedzi modelu.")
        self.models_summary = QLabel("Nie sprawdzono listy modeli ani zdolności generowania.")
        self.models_summary.setWordWrap(True)
        layout.addWidget(self.models_summary)
        self.button("Wykryj modele Ollama", lambda: self.core.probe("ollama"), layout)
        self.button("Sprawdź krótką generację modelu", lambda: self.core.probe("ollama_generate"), layout)
        self.button("Sprawdź konfigurację adaptera", lambda: self.action("model"), layout)
        self.button("Wybierz model w ustawieniach", lambda: self.navigate("Ustawienia"), layout)
        self.button("Przejdź do rzeczywistej rozmowy runtime", lambda: self.navigate("Czat lokalny"), layout)
        layout.addStretch()

    def _connections(self) -> None:
        layout = self.page("Połączenie z ChatGPT", "Osobny panel połączenia, nie drugi czat. Runtime → MCP → tunel → uwierzytelnienie → narzędzia bieżącej rozmowy → zaakceptowana tura.")
        self.connection_summary = QLabel("Połączenie z ChatGPT: niezweryfikowane. Sam tunel, HTTP i /readyz nie potwierdzają dostępności narzędzi ani odpowiedzi.")
        self.connection_summary.setWordWrap(True)
        layout.addWidget(self.connection_summary)
        self.connection_checks: dict[str, QLabel] = {}
        for key, title in (
            ("runtime", "Runtime Jaźni"), ("gateway", "Brama MCP"),
            ("cloudflare", "Tunel"), ("auth", "Uwierzytelnienie"),
            ("toolset", "Narzędzia w ChatGPT"), ("turn", "Zaakceptowana tura ChatGPT"),
        ):
            label = QLabel(title + ": wymaga potwierdzenia")
            label.setAccessibleName("Stan połączenia: " + title)
            label.setWordWrap(True)
            self.connection_checks[key] = label
            layout.addWidget(label)
        operations = QHBoxLayout()
        self.button("Uruchom lokalną bramę MCP", lambda: self.service("gateway", "start"), operations)
        self.button("Zatrzymaj własną bramę MCP", lambda: self.service("gateway", "stop"), operations)
        layout.addLayout(operations)
        tunnel_operations = QHBoxLayout()
        self.button("Bezpieczny tunel: konfiguracja OAuth", lambda: self.navigate("Ustawienia"), tunnel_operations)
        self.button("Zatrzymaj własny tunel", lambda: self.service("cloudflare", "stop"), tunnel_operations)
        layout.addLayout(tunnel_operations)
        self.button("Odśwież lokalne stany połączenia", self.refresh_services, layout)
        self.button("Sprawdź lokalny endpoint MCP", lambda: self.core.probe("gateway"), layout)
        self.button("Zweryfikuj katalog narzędzi MCP", lambda: self.action("mcp"), layout)
        self.button("Sprawdź skonfigurowany Worker Cloudflare", lambda: self.core.probe("cloudflare"), layout)
        self.button("Konfiguracja transportu i usług", lambda: self.navigate("Ustawienia"), layout)
        note = QLabel(
            "Publiczne MCP wymaga osobnej, uwierzytelnionej bramy --public-oauth "
            "(deploy/chatgpt_mcp). Studio uruchamia wyłącznie lokalne --loopback-dev, "
            "którego NIE należy wystawiać przez tunel. Tunel uruchom przez zatwierdzony "
            "proces deploymentu po weryfikacji OAuth, zakresów i hosta. "
            "Sama subskrypcja ChatGPT nie zapewnia klucza OpenAI API."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    def refresh_connection_checks(self) -> None:
        """Mirror local evidence. Never promote it to a ChatGPT host capability."""
        for key in ("runtime", "gateway", "cloudflare"):
            self.connection_checks[key].setText({
                "runtime": "Runtime Jaźni: ",
                "gateway": "Brama MCP: ",
                "cloudflare": "Tunel: ",
            }[key] + self.statuses[key].text())
        self.connection_checks["auth"].setText("Uwierzytelnienie: wymaga niezależnego potwierdzenia dla publicznej trasy")
        self.connection_checks["toolset"].setText("Narzędzia w ChatGPT: wymagają wywołania jazn_status, generate, resume i finalize w bieżącej rozmowie")
        self.connection_checks["turn"].setText("Zaakceptowana tura ChatGPT: brak dowodu w lokalnym Studio")
        self.connection_summary.setText(
            "Połączenie w ChatGPT pozostaje niezweryfikowane bez testu po stronie hosta. "
            "Rozłączenie czatu lokalnego nie wyłącza bramy MCP ani tunelu."
        )

    def _developer(self) -> None:
        layout = self.page("Developer", "Publiczny audyt: dowody, stany, identyfikatory i wyniki operacji. Bez prywatnego toku rozumowania i sekretów.")
        self.developer_page = self.pages.widget(self.pages.count() - 1)
        for label, callback in (("Stan Git", lambda: self.core.git_status()),
                                ("Diagnostyka runtime / NLP / routingu", lambda: self.action("doctor")),
                                ("Konfiguracja i mapa ścieżek", lambda: self.navigate("Konfiguracja Qt")),
                                ("Testy i oczekiwania", lambda: self.navigate("Katalog testów")),
                                ("Konsole i terminal", lambda: self.workspace.show(2)),
                                ("Problemy i wyjątki operacji", lambda: self.workspace.show(0)),
                                ("Eksportuj redagowany raport…", self.export)):
            self.button(label, callback, layout)
        self.developer_details = QPlainTextEdit()
        self.developer_details.setReadOnly(True)
        self.developer_details.setPlaceholderText("Wykonaj diagnostykę, aby otrzymać publiczne dowody.")
        layout.addWidget(self.developer_details)

    def refresh_service_table(self) -> None:
        from urllib.parse import urlsplit
        ports = {"runtime": str(urlsplit(self.core.settings.daemon_url).port), "ollama": "11434",
                 "gateway": self.core.settings.mcp_port, "cloudflare": "HTTPS", "supervisor": "—", "memory": "—"}
        for service, row in self.service_rows.items():
            from .service_visual_state import visual_state, COLORS, TITLES
            observed = self.supervisor_observation if service == "supervisor" else self.workspace.observations.get(service, {})
            status = visual_state(service, observed if isinstance(observed, dict) else {})
            indicator = self.services_table.item(row, 0)
            if indicator is not None:
                pix = QPixmap(16, 16)
                pix.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pix)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(COLORS[status]))
                painter.drawEllipse(3, 3, 10, 10)
                painter.end()
                indicator.setIcon(QIcon(pix))
                indicator.setToolTip(TITLES[status] + " (nie jest to dowód zaakceptowanej odpowiedzi)")
            pid = observed.get("pid")
            with self.core.lock:
                job = self.core.jobs.get("service:" + service)
                if job is not None and job.proc is not None and job.proc.poll() is None:
                    pid = job.pid
            if service == "runtime":
                ready = all(observed.get(flag) is True for flag in ("endpoint_reachable", "process_identity_confirmed", "endpoint_identity_matches", "heartbeat_fresh", "conversation_ready"))
            else:
                ready = observed.get("ready") is True
            readiness = "potwierdzona" if ready else "niezweryfikowana"
            if service == "memory":
                readiness = "status techniczny" if self.memory_observed else "niezweryfikowana"
            if service == "ollama" and observed.get("endpoint_reachable"):
                readiness = ("API; generacja potwierdzona" if observed.get("generation_verified") is True
                             else "API; brak testu generacji")
            for column, value in ((2, str(pid or "—")), (3, ports[service]), (4, readiness)):
                item = self.services_table.item(row, column)
                if item is not None and item.text() != value:
                    item.setText(value)
                    item.setToolTip(value)
            self.statuses[service].setToolTip(self.statuses[service].text())
        models = self.workspace.observations.get("ollama", {})
        if models:
            self.models_summary.setText("Modele: " + ", ".join(models.get("models", [])) + "\nGeneracja: " + ("potwierdzona" if models.get("generation_verified") else "niezweryfikowana"))

    def export(self) -> None:
        name, _ = QFileDialog.getSaveFileName(self, "Nowy raport diagnostyczny", "studio-report.json", "JSON (*.json)")
        if name:
            self.core.export_report(Path(name))
            self.statusBar().showMessage("Zapisano raport: " + name)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.local_acceptance_panel.shutdown():
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        if not self.smoke and self.settings_draft() != self.settings_baseline:
            if QMessageBox.question(self, "Niezapisane ustawienia", "Zamknąć i odrzucić niezapisane zmiany ustawień?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if not self.smoke and not self.configuration_panel.may_discard():
            event.ignore()
            return
        with self.core.lock:
            active = any(not j.done.is_set() for j in self.core.jobs.values())
        if active and not self.core.closed and not self.smoke and QMessageBox.question(self, "Zamknięcie Studio",
                "Zakończyć zadania i procesy uruchomione przez Studio? Daemon jest zarządzany osobną komendą runtime.") != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        # The interactive terminal is a separate operator-owned subprocess,
        # not part of Controller.jobs; it must be reaped before closing JSS.
        if not self.workspace.interactive_terminal.stop():
            event.ignore()
            return
        self.core.close()
        # Do not block Qt: let worker threads confirm termination first.
        with self.core.lock:
            pending = any(not j.done.is_set() for j in self.core.jobs.values())
        if pending:
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        if not self.smoke:
            try:
                self.persist_layout()
            except (OSError, ValueError) as exc:
                self.statusBar().showMessage("Nie zapisano układu: " + type(exc).__name__)
        self.timer.stop()
        event.accept()


def run_window(core: Controller, *, smoke: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    if not isinstance(app, QApplication):
        raise StudioError("Istniejąca instancja Qt nie jest aplikacją GUI")
    splash = None
    if not smoke:
        from .workbench_theme import workbench_colors
        colors = workbench_colors(core.settings.theme, core.settings.accent)
        pixmap = QPixmap(540, 180)
        pixmap.fill(QColor(colors.background))
        splash = QSplashScreen(pixmap)
        splash.showMessage("Jaźń — Serce Systemu\n\nRoot sprawdzony • przygotowywanie interfejsu…",
                           Qt.AlignmentFlag.AlignCenter, QColor(colors.text))
        splash.show()
        app.processEvents()
    window = Window(core, smoke=smoke)
    window.show()
    if splash is not None:
        splash.finish(window)
    if smoke:
        QTimer.singleShot(250, window.close)
    return app.exec()
