"""Navigation area of the JSS desktop workbench.

UI-only mixin. The Window owns widgets, the Controller owns processes and runtime.
An explicit dynamic host type prevents importing Window back into this module.
"""
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

from typing import Any

class NavigationViewMixin:
    def _about(self: Any) -> None:
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


    def update_current_section(self: Any, row: int) -> None:
        item = self.nav.item(row)
        if item is not None:
            self.current_section.setText(item.text())


    def toggle_sidebar(self: Any) -> None:
        visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(visible)
        if hasattr(self, "workbench") and self.workbench.compact_sidebar is not None:
            self.workbench.compact_sidebar = visible
        self.menu_button.setToolTip("Ukryj boczną nawigację (Ctrl+B)" if visible
                                    else "Pokaż boczną nawigację (Ctrl+B)")
        if visible:
            self.nav.setFocus()


    def set_logs_visible(self: Any, visible: bool) -> None:
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


    def toggle_logs(self: Any) -> None:
        self.set_logs_visible(not self.workspace.dock.isVisible() if self.unified_operator_mode else self.tabs.isHidden())


    def show_log(self: Any, key: str) -> QPlainTextEdit:
        """Select a source in the shared output pane where available."""
        view = self.log_view(key)
        if self.unified_operator_mode:
            self.workspace.open_log_source(key)
            return view
        self.tabs.setCurrentWidget(view)
        self.set_logs_visible(True)
        return view


    def log_view(self: Any, key: str) -> QPlainTextEdit:
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


    def navigate(self: Any, title: str) -> None:
        if title == "MCP i ChatGPT":  # Legacy navigation callers.
            title = "Połączenie z ChatGPT"
        self.section_search.clear()
        for row in range(self.nav.count()):
            if self.nav.item(row).text() == title:
                self.nav.setCurrentRow(row)
                return


    def filter_navigation(self: Any, query: str) -> None:
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            item.setHidden(query.casefold().strip() not in item.text().casefold())


    def select_search_result(self: Any) -> None:
        for row in range(self.nav.count()):
            if not self.nav.item(row).isHidden():
                self.nav.setCurrentRow(row)
                return


    def _workspace_menu(self: Any) -> None:
        from .workbench_shell import WorkbenchShell
        self.workbench = WorkbenchShell(self)


    def switch_sidebar(self: Any) -> None:
        right = self.shell_splitter.indexOf(self.sidebar) == 0
        self.shell_splitter.insertWidget(1 if right else 0, self.sidebar)
        self.sidebar.show()


    def reset_layout(self: Any) -> None:
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


    def restore_layout(self: Any) -> None:
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


    def persist_layout(self: Any) -> None:
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


    def setup_completed(self: Any, scope: str) -> None:
        self.layout_state["setup_scope"] = scope
        self.persist_layout()


    def open_setup(self: Any) -> None:
        from .first_run import SetupWizard
        if self.setup_wizard is None or not self.setup_wizard.isVisible():
            self.setup_wizard = SetupWizard(self.core, self.apply_settings, self.setup_completed, self)
        self.setup_wizard.show()
        self.setup_wizard.raise_()


    def _models(self: Any) -> None:
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


    def _connections(self: Any) -> None:
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


    def refresh_connection_checks(self: Any) -> None:
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


    def _developer(self: Any) -> None:
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


    def export(self: Any) -> None:
        name, _ = QFileDialog.getSaveFileName(self, "Nowy raport diagnostyczny", "studio-report.json", "JSON (*.json)")
        if name:
            self.core.export_report(Path(name))
            self.statusBar().showMessage("Zapisano raport: " + name)
