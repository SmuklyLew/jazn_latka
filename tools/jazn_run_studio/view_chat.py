"""Chat area of the JSS desktop workbench.

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

class ChatViewMixin:
    def _chat(self: Any) -> None:
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


    def select_local_model(self: Any) -> None:
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


    def connect_local_chat(self: Any) -> None:
        """Never bypass the first-run model and matching daemon evidence via sidebar."""
        if not (self.quick_runtime_ready and self.quick_generation_ready
                and self.core.settings.model):
            raise StudioError(
                "Najpierw w Pulpicie sprawdź zgodność runtime oraz uruchom "
                "test generacji wybranego modelu Ollama."
            )
        self.core.connect_chat()


    def send_chat(self: Any) -> None:
        if self.core.chat is None:
            raise StudioError("Najpierw połącz czat")
        text = self.message.toPlainText()
        request = self.core.chat.send(text)
        self.conversation.appendPlainText("Ty:\n" + text + "\n")
        self.message.clear()
        self.chat_state.setText("Oczekiwanie na wynik: " + request)


    def resume_chat(self: Any) -> None:
        if self.core.chat is None:
            from .chat import ChatClient
            self.core.chat = ChatClient(self.core)
        self.core.chat.resume()
