"""Studios area of the JSS desktop workbench.

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

class StudioViewMixin:
    def _diagnostics(self: Any) -> None:
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


    def _studios(self: Any) -> None:
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


    def _configuration(self: Any) -> None:
        from .configuration_view import ConfigurationPanel
        layout = self.page(
            "Konfiguracja Qt",
            "Profil przyszłych uruchomień — walidacja, mapa ścieżek, "
            "kontrolowany podgląd, zapis CAS i przywracanie kopii. Bez aktywacji daemona.",
        )
        self.configuration_panel = ConfigurationPanel(self.core)
        layout.addWidget(self.configuration_panel)


    def _version_studio(self: Any) -> None:
        from .version_view import VersionPanel
        layout = self.page(
            "Wersje Qt",
            "Natywna kontrola wersji (odczyt bez zapisu). "
            "Zmiany wydania i przywracanie metadanych nadal wymagają osobnego przeglądu.",
        )
        self.version_panel = VersionPanel(self.core)
        layout.addWidget(self.version_panel)


    def _tests_catalog(self: Any) -> None:
        from .test_catalog_view import TestCatalogPanel
        layout = self.page(
            "Katalog testów",
            "Natywny podgląd Test Studio: filtrowanie testów i ich oczekiwań bez uruchamiania lub edycji.",
        )
        self.tests_catalog_panel = TestCatalogPanel(self.core.root)
        layout.addWidget(self.tests_catalog_panel)


    def _local_acceptance(self: Any) -> None:
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


    def open_tpa_dependencies(self: Any) -> None:
        self.navigate("Studia Jaźni")
        index = self.studio_choice.findData("dependencies")
        if index >= 0:
            self.studio_choice.setCurrentIndex(index)
            self.load_studio_operations()
        self.statusBar().showMessage("Przygotuj profil testowy dla Pythona: " + self.local_acceptance_panel.python_field.text() + "; instalacja wymaga podglądu i potwierdzenia.")


    def _memory(self: Any) -> None:
        from .memory_view import MemoryPanel
        layout = self.page("Dowody MEMORY", "Odczytowe P1: role baz, porównanie i niezależna gotowość runtime.")
        self.memory_panel = MemoryPanel(self.core, self.guard)
        layout.addWidget(self.memory_panel)


    def reset_studio_operations(self: Any, _index: int = -1) -> None:
        self.invalidate_operation_preview()
        self.schema_key = ""
        self.command_schema = []
        self.operation.clear()
        self.execute_button.setEnabled(False)
        self.render_operation()


    def load_studio_operations(self: Any) -> None:
        self.reset_studio_operations()
        self.core.studio_helper("schema", str(self.studio_choice.currentData()))


    def render_operation(self: Any, _index: int = 0) -> None:
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


    def invalidate_operation_preview(self: Any, *_args: object) -> None:
        self.preview_approved = ""
        if hasattr(self, "preview_note"):
            self.preview_note.setText("Plan niezatwierdzony; sprawdź go po każdej zmianie.")


    def operation_payload(self: Any) -> dict:
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


    def preview_operation(self: Any) -> None:
        spec = self.operation_payload()
        self.invalidate_operation_preview()
        self.core.studio_helper("preview", self.schema_key, spec)
        self.preview_note.setText("Walidacja planu przez kanoniczny parser trwa…")


    def execute_operation(self: Any) -> None:
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
