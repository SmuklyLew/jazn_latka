"""Qt desktop shell. Only the GUI thread accesses widgets."""
from __future__ import annotations

import json
from pathlib import Path
import queue
from typing import Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QTabWidget,
    QVBoxLayout, QWidget,
)

from . import STUDIO_VERSION
from .core import ACTIONS, STUDIOS, Controller, Settings, StudioError, discovery, save_settings

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
        self.setWindowTitle("Studio Jaźni Starter")
        self.resize(1240, 840)
        self.setMinimumSize(860, 580)
        self.logs: dict[str, QPlainTextEdit] = {}
        self.fields: dict[str, QLineEdit] = {}
        self.statuses: dict[str, QLabel] = {}
        self.nav = QListWidget()
        self.nav.setAccessibleName("Nawigacja Studio")
        self.nav.setMaximumWidth(220)
        self.pages = QStackedWidget()
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(170)
        content = QSplitter(Qt.Orientation.Vertical)
        content.addWidget(self.pages)
        content.addWidget(self.tabs)
        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 1)
        shell = QSplitter()
        shell.addWidget(self.nav)
        shell.addWidget(content)
        shell.setStretchFactor(1, 1)
        self.setCentralWidget(shell)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self._dashboard()
        self._services()
        self._diagnostics()
        self._studios()
        self._settings()
        self._about()
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage(str(core.root))
        self.apply_theme()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        # Discovery is read-only and local. Network probes require explicit actions.
        self.setup.setPlainText(json.dumps(discovery(core.settings), ensure_ascii=False, indent=2))

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
        self.evidence = QLabel("Runtime: jeszcze nie sprawdzono. Gotowość rozmowy wymaga osobnego potwierdzenia.")
        self.evidence.setWordWrap(True)
        layout.addWidget(self.evidence)
        row = QHBoxLayout()
        self.button("Sprawdź status runtime", lambda: self.action("status"), row)
        self.button("Uruchom diagnostykę krok po kroku", self.core.run_batch, row)
        layout.addLayout(row)
        layout.addWidget(QLabel("Wykryte programy i zależności"))
        self.setup = QPlainTextEdit()
        self.setup.setReadOnly(True)
        layout.addWidget(self.setup)
        links = QHBoxLayout()
        for name, url in INSTALL_LINKS.items():
            self.button("Instalacja: " + name, lambda u=url: QDesktopServices.openUrl(QUrl(u)), links)
        layout.addLayout(links)
        self.button("Odśwież wykrywanie", lambda: self.setup.setPlainText(json.dumps(discovery(self.core.settings), ensure_ascii=False, indent=2)), layout)

    def _services(self) -> None:
        layout = self.page("Usługi i procesy", "Stop i restart usług zewnętrznych dotyczą wyłącznie procesów uruchomionych przez to Studio. Proces działający nie oznacza gotowości funkcji.")
        for service, title in (("runtime", "Runtime Jaźni"), ("ollama", "Ollama"),
                               ("gateway", "Lokalna brama MCP"), ("cloudflare", "Cloudflare Tunnel")):
            layout.addWidget(QLabel(title))
            row = QHBoxLayout()
            status = QLabel("Nie sprawdzono")
            self.statuses[service] = status
            row.addWidget(status, 1)
            for operation, label in (("start", "Uruchom"), ("stop", "Zatrzymaj"), ("restart", "Restart")):
                self.button(label, lambda s=service, op=operation: self.service(s, op), row)
            layout.addLayout(row)
        layout.addWidget(QLabel("ChatGPT: host zdalny. Katalog MCP i HTTP to osobne testy; nie potwierdzają zaakceptowanej tury.\nOpenAI API: planowane rozszerzenie."))
        self.processes = QPlainTextEdit()
        self.processes.setReadOnly(True)
        layout.addWidget(self.processes)

    def service(self, service: str, op: str) -> None:
        if service == "runtime":
            self.action(op)
            return
        if op in {"stop", "restart"} and QMessageBox.question(self, "Zmiana usługi",
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
        self.button("Zapisz raport ze wszystkich logów…", self.export, layout)
        layout.addStretch()

    def _studios(self) -> None:
        layout = self.page("Studia Jaźni", "Wspólny katalog istniejących narzędzi. Ten etap otwiera ich dotychczasowe interfejsy; migracja stron do wspólnego Qt jest osobnym warunkiem odbioru.")
        for item in STUDIOS:
            row = QHBoxLayout()
            self.button(item.label, lambda key=item.key: self.core.start_studio(key), row)
            note = QLabel(item.description)
            note.setWordWrap(True)
            row.addWidget(note, 2)
            layout.addLayout(row)
        layout.addStretch()

    def _settings(self) -> None:
        layout = self.page("Ustawienia", "Profil lokalny Studio jest ignorowany przez Git. Sekrety nie są polami tego profilu. Zmiana ścieżek nie przejmuje działających procesów.")
        form = QFormLayout()
        labels = {"python": "Interpreter Python", "ollama": "Plik Ollama", "cloudflared": "Plik cloudflared",
                  "tunnel_config": "Konfiguracja tunelu (plik)", "tunnel_id": "Nazwa / UUID tunelu",
                  "model": "Model Ollama", "accent": "Kolor własny (#RRGGBB)"}
        for key, label in labels.items():
            field = QLineEdit(str(getattr(self.core.settings, key)))
            field.setAccessibleName(label)
            self.fields[key] = field
            form.addRow(label, field)
        self.theme = QComboBox()
        self.theme.addItems(["system", "light", "dark", "purple", "custom"])
        self.theme.setCurrentText(self.core.settings.theme)
        form.addRow("Motyw", self.theme)
        layout.addLayout(form)
        self.button("Zapisz i zastosuj", self.save, layout)
        layout.addWidget(QLabel("Profile środowiska runtime są obsługiwane przez kanoniczne Studio Konfiguracji."))
        self.button("Otwórz Studio Konfiguracji", lambda: self.core.start_studio("configuration"), layout)
        layout.addStretch()

    def save(self) -> None:
        data = {k: field.text().strip() for k, field in self.fields.items()}
        data["theme"] = self.theme.currentText()
        settings = Settings.validate(data)
        self.digest = save_settings(self.core.root, settings, self.digest)
        self.core.settings = settings
        self.apply_theme()
        self.statusBar().showMessage("Zapisano ustawienia Studio")

    def apply_theme(self) -> None:
        theme = self.core.settings.theme
        app = QApplication.instance()
        dark = theme in {"dark", "purple", "custom"}
        if theme == "system" and isinstance(app, QApplication):
            dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        bg, surface, text, border = ("#1e1d25", "#282632", "#eeeaf4", "#494355") if dark else ("#f4f2f8", "#ffffff", "#272332", "#c9c2d6")
        accent = self.core.settings.accent if theme == "custom" else "#9876d4"
        self.setStyleSheet(f"""
            QWidget {{ background: {bg}; color: {text}; font-size: 14px; }}
            QLabel#heading {{ font-size: 27px; font-weight: 600; padding-bottom: 10px; }}
            QListWidget {{ background: {surface}; border: 0; padding: 12px 4px; }}
            QListWidget::item {{ padding: 14px 12px; }}
            QListWidget::item:selected {{ background: {accent}; color: #171020; }}
            QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 5px; padding: 8px 14px; }}
            QPushButton:hover, QPushButton:focus {{ border: 2px solid {accent}; padding: 7px 13px; }}
            QPlainTextEdit, QLineEdit, QComboBox {{ background: {surface}; border: 1px solid {border}; padding: 6px; selection-background-color: {accent}; }}
            QPlainTextEdit {{ font-family: Consolas, monospace; }}
        """)

    def _about(self) -> None:
        layout = self.page("O programie", "Studio Jaźni Starter  " + STUDIO_VERSION)
        text = QLabel("Projekt: Jaźń • repozytorium SmuklyLew/jazn_latka\n"
                      "Autor / opiekun projektu: SmuklyLew.\n"
                      "Studio jest aplikacją operatorską; runtime pozostaje właścicielem pamięci, tożsamości i finalizacji.\n\n"
                      "W repozytorium bazowym nie znaleziono pliku LICENSE. Studio nie nadaje projektowi nowej licencji.\n"
                      "Qt for Python / PySide6: informacje o licencjach i zależnościach należy dołączyć do dystrybucji.\n\n"
                      "Stan wydania: etap implementacji, przed pełnym odbiorem integracji i CI.")
        text.setWordWrap(True)
        layout.addWidget(text)
        self.button("Źródła projektu", lambda: QDesktopServices.openUrl(QUrl("https://github.com/SmuklyLew/jazn_latka")), layout)
        self.button("Licencje Qt", lambda: QDesktopServices.openUrl(QUrl("https://doc.qt.io/qtforpython-6/licenses.html")), layout)
        layout.addStretch()

    def log_view(self, key: str) -> QPlainTextEdit:
        if key not in self.logs:
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.document().setMaximumBlockCount(2500)
            view.setAccessibleName("Log " + key)
            self.logs[key] = view
            self.tabs.addTab(view, key)
        return self.logs[key]

    def poll(self) -> None:
        for _ in range(150):
            try:
                key, kind, value = self.core.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log_view(key).appendPlainText(str(value))
            elif kind == "evidence":
                self.evidence.setText("Dowody runtime:\n" + json.dumps(value, ensure_ascii=False, indent=2))
            elif kind == "state":
                self.statusBar().showMessage(key + ": " + value["state"] + (" / " + value["error"] if value["error"] else ""))
                service = key.removeprefix("service:")
                if service in self.statuses:
                    self.statuses[service].setText(value["state"] + " • PID " + str(value["pid"]) + " • gotowość funkcji niezweryfikowana")
        with self.core.lock:
            snapshots = [j.snapshot() for j in self.core.jobs.values()]
        self.processes.setPlainText(json.dumps(snapshots, ensure_ascii=False, indent=2))

    def export(self) -> None:
        name, _ = QFileDialog.getSaveFileName(self, "Nowy raport diagnostyczny", "studio-report.json", "JSON (*.json)")
        if name:
            self.core.export_report(Path(name))
            self.statusBar().showMessage("Zapisano raport: " + name)

    def closeEvent(self, event: QCloseEvent) -> None:
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
        self.timer.stop()
        event.accept()


def run_window(core: Controller, *, smoke: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    if not isinstance(app, QApplication):
        raise StudioError("Istniejąca instancja Qt nie jest aplikacją GUI")
    window = Window(core, smoke=smoke)
    window.show()
    if smoke:
        QTimer.singleShot(250, window.close)
    return app.exec()
