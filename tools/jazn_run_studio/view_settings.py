"""Settings area of the JSS desktop workbench.

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

class SettingsViewMixin:
    def _settings(self: Any) -> None:
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


    def settings_model_selected(self: Any, _index: int) -> None:
        selected = self.settings_model_selector.currentData()
        if isinstance(selected, str) and selected:
            self.fields["model"].setText(selected)


    def set_settings_installed_models(self: Any, names: object) -> None:
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


    def fill_discovered_defaults(self: Any) -> None:
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


    def choose_custom_color(self: Any) -> None:
        """Only the user's explicit acceptance changes the draft settings."""
        initial = QColor(self.fields["accent"].text())
        if not initial.isValid():
            initial = QColor(self.core.settings.accent)
        selected = QColorDialog.getColor(initial, self, "Kolor akcentu Jaźni")
        if selected.isValid():
            self.fields["accent"].setText(selected.name())
            self.theme.setCurrentText("custom")


    def save_profile(self: Any) -> None:
        if not self.profile_widgets:
            raise StudioError("Najpierw wczytaj profil środowiska")
        if QMessageBox.question(self, "Profil środowiska", "Zapisać walidowany profil przyszłych uruchomień? Działający daemon zachowuje swoją konfigurację.") != QMessageBox.StandardButton.Yes:
            return
        values = {key: widget.currentText() if isinstance(widget, QComboBox) else widget.text()
                  for key, widget in self.profile_widgets.items()}
        self.core.studio_helper("profile-save", data={"values": {k: v for k, v in values.items() if v}, "digest": self.profile_digest})


    def save(self: Any) -> None:
        data = {k: field.text().strip() for k, field in self.fields.items()}
        data["theme"] = str(self.theme.currentData())
        data["runtime_profile"] = str(self.profile_mode.currentData())
        settings = Settings.validate(data)
        self.apply_settings(settings)


    def apply_settings(self: Any, settings: Settings, *, appearance_only: bool = False) -> None:
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


    def select_style(self: Any, theme: str) -> None:
        index = self.style_selector.findData(theme)
        if index >= 0:
            self.style_selector.setCurrentIndex(index)


    def style_selected(self: Any, index: int) -> None:
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


    def apply_theme(self: Any) -> None:
        app = QApplication.instance()
        system_dark = (isinstance(app, QApplication)
                       and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        from .visual_system import VisualSystem
        if not hasattr(self, "visual_system"):
            self.visual_system = VisualSystem(self)
        self.visual_system.apply(self.core.settings.theme, self.core.settings.accent, system_dark=system_dark)


    def settings_draft(self: Any) -> dict[str, str]:
        values = {key: field.text().strip() for key, field in self.fields.items()}
        values["theme"] = str(self.theme.currentData())
        values["runtime_profile"] = str(self.profile_mode.currentData())
        return values


    def settings_changed(self: Any, *_args: object) -> None:
        if hasattr(self, "settings_baseline"):
            dirty = self.settings_draft() != self.settings_baseline
            self.settings_hint.setText("Niezapisane zmiany. Ustawienia usług wymagają ponownego uruchomienia usługi." if dirty else
                                       "Formularz zgodny z ostatnio zapisanym profilem.")


    def reset_settings_draft(self: Any) -> None:
        defaults = Settings()
        for key, field in self.fields.items():
            field.setText(str(getattr(defaults, key)))
        self.theme.setCurrentIndex(self.theme.findData(defaults.theme))
        self.profile_mode.setCurrentIndex(0)
        self.settings_model_selector.setCurrentIndex(0)


    def filter_settings(self: Any, *_args: object) -> None:
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
