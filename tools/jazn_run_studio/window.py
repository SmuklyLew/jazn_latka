"""Qt desktop shell. Only the GUI thread accesses widgets."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import queue
from typing import Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QColor, QDesktopServices, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSplashScreen, QSplitter, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import STUDIO_VERSION
from .core import ACTIONS, STUDIOS, Controller, Settings, StudioError, discovery, save_settings
from .studio_worker import preview_fingerprint
from .workbench_theme import workbench_stylesheet

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
        self.logs_user_hidden = False

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
        header_layout.addStretch(1)
        self.workbench_status = QLabel("Lokalne Studio  •  status niezweryfikowany")
        self.workbench_status.setObjectName("workbenchStatus")
        self.workbench_status.setAccessibleName("Informacja o trybie Studio, nie o gotowości daemona")
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
        self.restore_layout()
        self.log_toggle = QPushButton("Pokaż logi")
        self.log_toggle.setAccessibleName("Pokaż lub ukryj dolny panel logów")
        self.log_toggle.clicked.connect(self.toggle_logs)
        self.statusBar().addPermanentWidget(self.log_toggle)
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage(str(core.root))
        self.apply_theme()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        # Discovery is read-only and local. Network probes require explicit actions.
        self.render_discovery()
        if not smoke:
            from .requirements_worker import setup_scope
            from .core import python_executable
            if self.layout_state.get("setup_scope") != setup_scope(self.core.root, python_executable(self.core.settings)):
                QTimer.singleShot(0, self.open_setup)
        if isinstance(app := QApplication.instance(), QApplication):
            app.styleHints().colorSchemeChanged.connect(lambda _scheme: self.apply_theme())

    def page(self, title: str, description: str) -> QVBoxLayout:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(24, 20, 24, 16)
        heading = QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)
        subtitle = QLabel(description)
        subtitle.setWordWrap(True)
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
        self.log_view(key)

    def _dashboard(self) -> None:
        layout = self.page("Pulpit", "JAŹŃ / STARTER    •    Sprawdź środowisko, wybierz usługę i obserwuj wynik.")
        self.button("Kreator konfiguracji…", self.open_setup, layout)
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
        self.services_table = QTableWidget(4, 6)
        self.services_table.setHorizontalHeaderLabels(["Usługa", "Status", "PID", "Port", "Readiness", "Akcje"])
        self.services_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.services_table.horizontalHeader().setStretchLastSection(False)
        self.services_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.services_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.services_table.setMinimumWidth(0)
        self.services_table.setMinimumHeight(230)
        self.service_rows = {}
        for row, (service, title) in enumerate((("runtime", "Jaźń"), ("ollama", "Ollama"), ("gateway", "MCP"), ("cloudflare", "Tunel"))):
            self.service_rows[service] = row
            self.services_table.setItem(row, 0, QTableWidgetItem(title))
            status = QLabel("Nie sprawdzono")
            status.setWordWrap(True)
            status.setMinimumWidth(0)
            self.statuses[service] = status
            self.services_table.setCellWidget(row, 1, status)
            for column in (2, 3, 4):
                self.services_table.setItem(row, column, QTableWidgetItem("—"))
            button = QPushButton("Akcje ▾")
            menu = QMenu(button)
            for op, label in (("start", "Start"), ("stop", "Stop"), ("restart", "Restart")):
                action = menu.addAction(label)
                action.triggered.connect(lambda _checked=False, s=service, o=op: self.guard(lambda: self.service(s, o)))
            config = menu.addAction("Konfiguracja")
            config.triggered.connect(lambda: self.navigate("Ustawienia"))
            logs = menu.addAction("Logi")
            logs.triggered.connect(lambda _checked=False, s=service: self.log_view("status" if s == "runtime" else "service:" + s))
            details = menu.addAction("Szczegóły / odśwież")
            details.triggered.connect(lambda _checked=False, s=service: self.guard(lambda: self.core.start_action("status") if s == "runtime" else self.core.probe(s)))
            button.setMenu(menu)
            self.services_table.setCellWidget(row, 5, button)
        self.services_table.setColumnWidth(0, 65)
        self.services_table.setColumnWidth(1, 190)
        self.services_table.setColumnWidth(2, 45)
        self.services_table.setColumnWidth(3, 55)
        self.services_table.setColumnWidth(5, 85)
        self.services_table.verticalHeader().setDefaultSectionSize(90)
        layout.addWidget(self.services_table)
        self.button("Odśwież status usług", self.refresh_services, layout)
        self.button("Sprawdź usługę Windows cloudflared", lambda: self.core.probe("tunnel_service"), layout)
        remote_note = QLabel("Cloudflare jest opcjonalny. Start tunelu wymaga jawnej zgody; Studio nie przejmuje obcych PID. Zamknięcie Studio nie zatrzymuje trwałego daemona.")
        remote_note.setWordWrap(True)
        layout.addWidget(remote_note)
        self.processes = QPlainTextEdit()
        self.processes.setReadOnly(True)
        self.processes.setMaximumHeight(150)
        layout.addWidget(self.processes)

    def refresh_services(self) -> None:
        """Explicit, read-only probes; no silent auto-start or PID adoption."""
        self.core.start_action("status")
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
        row = QHBoxLayout()
        self.button("Połącz", self.core.connect_chat, row)
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
        self.log_view("service:" + service)

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
        )
        self.local_acceptance_panel = LocalAcceptancePanel(self.core.root, python=self.core.settings.python)
        layout.addWidget(self.local_acceptance_panel)

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
            field.setAccessibleName(label)
            self.fields[key] = field
            form.addRow(label, field)
        self.theme = QComboBox()
        self.theme.addItems(["violet-night", "system", "light", "dark", "purple", "custom"])
        self.theme.setCurrentText(self.core.settings.theme)
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
        data["theme"] = self.theme.currentText()
        data["runtime_profile"] = str(self.profile_mode.currentData())
        settings = Settings.validate(data)
        self.apply_settings(settings)

    def apply_settings(self, settings: Settings) -> None:
        self.digest = save_settings(self.core.root, settings, self.digest)
        self.core.settings = settings
        for key, field in self.fields.items():
            field.setText(str(getattr(settings, key)))
        self.theme.setCurrentText(settings.theme)
        self.profile_mode.setCurrentIndex(1 if settings.runtime_profile == "operator" else 0)
        self.apply_theme()
        self.settings_baseline = self.settings_draft()
        self.settings_hint.setText("Zapisano. Konfiguracja usług obowiązuje przy ich kolejnym uruchomieniu.")
        self.statusBar().showMessage("Zapisano ustawienia Studio")

    def apply_theme(self) -> None:
        app = QApplication.instance()
        system_dark = (isinstance(app, QApplication)
                       and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        self.setStyleSheet(workbench_stylesheet(
            self.core.settings.theme, self.core.settings.accent, system_dark=system_dark,
        ))

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
        self.menu_button.setToolTip("Ukryj boczną nawigację (Ctrl+B)" if visible
                                    else "Pokaż boczną nawigację (Ctrl+B)")
        if visible:
            self.nav.setFocus()

    def toggle_logs(self) -> None:
        visible = not self.tabs.isVisible()
        self.logs_user_hidden = not visible
        self.tabs.setVisible(visible)
        self.log_toggle.setText("Ukryj logi" if visible else "Pokaż logi")
        if visible and self.tabs.count():
            self.tabs.setFocus()

    def update_service_summary(self, service: str, detail: str) -> None:
        """Mirror the same observed state; never infer readiness from a PID."""
        if service in self.statuses:
            self.statuses[service].setText(detail)
        if service in self.dashboard_statuses:
            self.dashboard_statuses[service].setText(service.upper() + ": " + detail)

    def log_view(self, key: str) -> QPlainTextEdit:
        if key not in self.logs:
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.document().setMaximumBlockCount(2500)
            view.setAccessibleName("Log " + key)
            self.logs[key] = view
            self.tabs.addTab(view, key)
            if not self.logs_user_hidden:
                self.tabs.show()
                self.log_toggle.setText("Ukryj logi")
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
            elif kind == "evidence":
                yes = lambda flag: "tak" if flag else "niepotwierdzone"
                ready = all(value.get(flag) is True for flag in (
                    "endpoint_reachable", "process_identity_confirmed",
                    "endpoint_identity_matches", "heartbeat_fresh",
                    "conversation_ready",
                ))
                state = str(value.get("active_state") or "niepotwierdzony")
                heading = ("Pracuje — zweryfikowany runtime" if ready else
                           "Zatrzymane — runtime nieaktywny" if state in {"dead", "stopped", "inactive"} else
                           "Gotowość niezweryfikowana")
                detail = (heading + " • endpoint: " + yes(value.get("endpoint_reachable")) +
                    " • tożsamość procesu: " + yes(value.get("process_identity_confirmed")) +
                    " • gotowość rozmowy: " + yes(value.get("conversation_ready")))
                self.evidence.setText("Runtime: " + detail)
                self.update_service_summary("runtime", detail)
            elif kind == "probe":
                service = value.get("service")
                if service in self.statuses:
                    if value.get("ready") is True:
                        detail = "Pracuje • endpoint i gotowość usługi potwierdzone; funkcja wymaga osobnego testu"
                    elif value.get("ready") is False:
                        detail = "BŁĄD • usługa nie zgłasza gotowości"
                    elif service == "ollama":
                        detail = "Endpoint odpowiada • generacja odpowiedzi niezweryfikowana"
                    else:
                        detail = "Odpowiedź testu • gotowość niezweryfikowana"
                    self.update_service_summary(str(service), detail)
                if service == "ollama":
                    self.chat_state.setText("Modele Ollama: " + ", ".join(value.get("models", [])) + ". Wybierz nazwę w ustawieniach.")
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
                    self.log_view("Zdarzenia").appendPlainText(line)
                    if value["state"] == "failed":
                        self.log_view("Błędy").appendPlainText(line)
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
                elif key.startswith("probe:") and value["state"] == "failed":
                    service = key.removeprefix("probe:")
                    self.update_service_summary(service, "BŁĄD testu • " + str(value.get("error") or "niepowodzenie"))
        with self.core.lock:
            snapshots = [j.snapshot() for j in self.core.jobs.values()]
        self.processes.setPlainText(json.dumps(snapshots, ensure_ascii=False, indent=2))
        self.workspace.refresh()
        self.refresh_service_table()
        if self.pages.currentWidget() is self.developer_page:
            public = {"jobs": snapshots, "services": self.workspace.observations,
                      "accepted_visible_turn": False}
            self.developer_details.setPlainText(self.core.redactor.text(json.dumps(public, ensure_ascii=False, indent=2)))

    def navigate(self, title: str) -> None:
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
        view = self.menuBar().addMenu("Widok")
        view.addAction(self.workspace.dock.toggleViewAction())
        for label, callback in (("Problemy", lambda: self.workspace.show(0)),
                                ("Output / Logi", lambda: self.workspace.show(1)),
                                ("Terminal / Konsole", lambda: self.workspace.show(2)),
                                ("Nawigacja po lewej / prawej", self.switch_sidebar),
                                ("Przywróć bezpieczny układ", self.reset_layout)):
            action = view.addAction(label)
            action.triggered.connect(callback)
        setup = self.menuBar().addMenu("Konfiguracja")
        action = setup.addAction("Kreator pierwszego uruchomienia…")
        action.triggered.connect(self.open_setup)

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
        self.logs_user_hidden = True
        self.tabs.hide()
        # Restoring the visual theme is a draft; no runtime settings are changed.
        self.theme.setCurrentText(Settings().theme)
        self.setStyleSheet(workbench_stylesheet(Settings().theme, Settings().accent))

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
        self.workspace.dock.setVisible(data.get("dock_visible", False))

    def persist_layout(self) -> None:
        from .workspace_layout import SCHEMA, save_layout
        areas = [Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea,
                 Qt.DockWidgetArea.TopDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea]
        area = self.dockWidgetArea(self.workspace.dock)
        self.layout_state = {"schema": SCHEMA, "width": self.width(), "height": self.height(),
                             "sidebar_right": self.shell_splitter.indexOf(self.sidebar) == 1,
                             "sidebar_visible": self.sidebar.isVisible(),
                             "dock_visible": self.workspace.dock.isVisible(),
                             "dock_area": areas.index(area) if area in areas else 3,
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
        values["theme"] = self.theme.currentText()
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
        self.theme.setCurrentText(defaults.theme)
        self.profile_mode.setCurrentIndex(0)

    def filter_settings(self, *_args: object) -> None:
        categories = {"python": "Środowisko", "mcp_python": "Środowisko", "ollama": "Modele",
                      "model": "Modele", "daemon_url": "Runtime", "mcp_port": "MCP",
                      "cloudflared": "Cloudflare", "tunnel_config": "Cloudflare", "tunnel_id": "Cloudflare",
                      "cloudflare_url": "Cloudflare", "secrets_file": "Bezpieczeństwo", "accent": "Wygląd"}
        query = self.settings_search.text().casefold().strip()
        category = self.settings_category.currentText()
        widgets = {**self.fields, "theme": self.theme, "runtime_profile": self.profile_mode}
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
        self.button("Sprawdź konfigurację adaptera", lambda: self.action("model"), layout)
        self.button("Wybierz model w ustawieniach", lambda: self.navigate("Ustawienia"), layout)
        self.button("Przejdź do rzeczywistej rozmowy runtime", lambda: self.navigate("Czat lokalny"), layout)
        layout.addStretch()

    def _connections(self) -> None:
        layout = self.page("MCP i ChatGPT", "Oddzielne warstwy: runtime → MCP → transport zdalny → uwierzytelnienie → autoryzacja narzędzi → zaakceptowana tura hosta.")
        self.connection_summary = QLabel("Połączenie z ChatGPT: niezweryfikowane. Katalog narzędzi, HTTP i /readyz nie potwierdzają zaakceptowanej odpowiedzi.")
        self.connection_summary.setWordWrap(True)
        layout.addWidget(self.connection_summary)
        self.button("Sprawdź lokalny endpoint MCP", lambda: self.core.probe("gateway"), layout)
        self.button("Zweryfikuj katalog narzędzi MCP", lambda: self.action("mcp"), layout)
        self.button("Sprawdź skonfigurowany Worker Cloudflare", lambda: self.core.probe("cloudflare"), layout)
        self.button("Konfiguracja transportu i usług", lambda: self.navigate("Ustawienia"), layout)
        note = QLabel("Cloudflare Tunnel jest opcjonalny i wymaga jawnej zgody przed uruchomieniem. Subskrypcja ChatGPT nie zapewnia automatycznie klucza ani rozliczenia OpenAI API. Gotowość zewnętrznego hosta musi potwierdzić rzeczywisty test połączenia.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

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
                 "gateway": self.core.settings.mcp_port, "cloudflare": "zdalny"}
        for service, row in self.service_rows.items():
            observed = self.workspace.observations.get(service, {})
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
            if service == "ollama" and observed.get("endpoint_reachable"):
                readiness = "API; brak testu generacji"
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
