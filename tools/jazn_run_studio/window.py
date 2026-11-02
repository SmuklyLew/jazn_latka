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
from .service_status_dialog import ServiceStatusDialog
from .studio_worker import preview_fingerprint
from .workbench_theme import THEME_CHOICES, workbench_stylesheet

from .view_dashboard import DashboardViewMixin
from .view_services import ServiceViewMixin
from .view_chat import ChatViewMixin
from .view_studios import StudioViewMixin
from .view_settings import SettingsViewMixin
from .view_navigation import NavigationViewMixin
from .view_events import EventViewMixin

INSTALL_LINKS = {
    "Python": "https://www.python.org/downloads/",
    "Qt / PySide6": "https://doc.qt.io/qtforpython-6/gettingstarted.html",
    "Ollama": "https://ollama.com/download",
    "Cloudflare Tunnel": "https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/",
}


class Window(DashboardViewMixin, ServiceViewMixin, ChatViewMixin, StudioViewMixin, SettingsViewMixin, NavigationViewMixin, EventViewMixin, QMainWindow):
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
        brand = QLabel("JAŹŃ  •  STUDIO")
        brand.setObjectName("workbenchBrand")
        brand.setWordWrap(True)
        sidebar_layout.addWidget(brand)
        description = QLabel("PANEL OPERACYJNY")
        description.setObjectName("workbenchCaption")
        sidebar_layout.addWidget(description)
        self.sidebar_heading = QLabel("PULPIT")
        self.sidebar_heading.setObjectName("workbenchSidebarGroup")
        sidebar_layout.addWidget(self.sidebar_heading)
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
        self.section_search.setObjectName("workbenchQuickSearch")
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
        self.services_status_button = QPushButton("● Stany usług")
        self.services_status_button.setAccessibleName("Otwórz stany serwera, Runtime, MCP i Ollama")
        self.services_status_button.clicked.connect(self.open_service_status)
        header_layout.addWidget(self.services_status_button)
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
        self.service_status_dialog: ServiceStatusDialog | None = None
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

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.local_acceptance_panel.shutdown():
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        if not self.tests_catalog_panel.shutdown():
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
        if hasattr(self, "visual_system"):
            self.visual_system.shutdown()
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
