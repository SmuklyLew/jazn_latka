"""Dashboard area of the JSS desktop workbench.

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

INSTALL_LINKS = {
    "Python": "https://www.python.org/downloads/",
    "Qt / PySide6": "https://doc.qt.io/qtforpython-6/gettingstarted.html",
    "Ollama": "https://ollama.com/download",
    "Cloudflare Tunnel": "https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/",
}


class DashboardViewMixin:
    def _dashboard(self: Any) -> None:
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


    def check_local_readiness(self: Any) -> None:
        """Read-only checks, never starts a second daemon or downloads a model."""
        self.core.start_action("status")
        self.core.probe("ollama")
        self.quick_start_status.setText(
            "Sprawdzam osobno status daemona i listę modeli Ollama. "
            "Nie uruchamiam usług ani nie zmieniam MEMORY."
        )


    def refresh_quick_start(self: Any) -> None:
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


    def render_discovery(self: Any) -> None:
        data = discovery(self.core.settings)
        rows = [(name, "Dostępny" if data.get(name) else "Brak", str(data.get(name) or "Wskaż plik w ustawieniach"))
                for name in ("python", "ollama", "cloudflared", "git")]
        rows += [(name, "Dostępna" if present else "Brak", "Biblioteka Pythona") for name, present in data["dependencies"].items()]
        self.setup.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.setup.setItem(row, column, QTableWidgetItem(value))
        self.setup.resizeColumnsToContents()
