"""Chat area of the JSS desktop workbench.

UI-only mixin. The Window owns widgets, the Controller owns processes and runtime.
An explicit dynamic host type prevents importing Window back into this module.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
import threading
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
from .chat_bubbles import ChatTranscript, HistoryDelivery, visible_time
from .studio_worker import preview_fingerprint
from .workbench_theme import THEME_CHOICES, workbench_stylesheet

from typing import Any

class ChatViewMixin:
    def _chat(self: Any) -> None:
        layout = self.page("Czat lokalny", "Rozmowa przez runtime Jaźni i wybrany model Ollama. Tylko zaakceptowane odpowiedzi runtime pojawiają się jako wypowiedzi Łatki.")
        self.chat_state = QLabel(
            "Rozłączony. Wybierz model w ustawieniach, uruchom runtime i Ollamę, a następnie połącz.")
        self.chat_state.setWordWrap(True)
        self.chat_state.setObjectName("workbenchChatStatus")
        # Transport diagnostics belong to the collapsible operations history,
        # not the conversation header. Existing callers/tests still receive
        # the most recent chat_state without exposing raw request IDs.
        self.chat_state.setAccessibleName("Ostatni techniczny status rozmowy")

        # The conversation is the focus of this view. Technical connection
        # controls remain discoverable without occupying half the editor.
        self.chat_controls_toggle = QPushButton("Połączenie i model ▸")
        self.chat_controls_toggle.setCheckable(True)
        self.chat_controls_toggle.setAccessibleName("Rozwiń lub zwiń połączenie i model czatu")
        layout.addWidget(self.chat_controls_toggle)
        self.chat_controls = QWidget()
        controls = QVBoxLayout(self.chat_controls)
        controls.setContentsMargins(0, 0, 0, 4)
        model_row = QHBoxLayout()
        self.chat_model_selector = QComboBox()
        self.chat_model_selector.setAccessibleName("Model dla czatu lokalnego Ollama")
        self.chat_model_selector.addItem("Wykryj modele Ollama…", "")
        if self.core.settings.model:
            self.chat_model_selector.addItem(
                self.core.settings.model + " (z ustawień, niezweryfikowany)",
                self.core.settings.model)
            self.chat_model_selector.setCurrentIndex(1)
        model_row.addWidget(self.chat_model_selector, 1)
        self.button("Wykryj modele", lambda: self.core.probe("ollama"), model_row)
        self.button("Sprawdź generację", lambda: self.core.probe("ollama_generate"), model_row)
        self.button("Zapisz wybór", self.select_local_model, model_row)
        controls.addLayout(model_row)
        connection_row = QHBoxLayout()
        self.button("Połącz", self.connect_local_chat, connection_row)
        self.button("Rozłącz transport", lambda: self.core.stop_owned("chat"), connection_row)
        self.button("Wznów wynik", self.resume_chat, connection_row)
        self.button("Zamknij nieudaną turę", self.close_failed_chat, connection_row)
        controls.addLayout(connection_row)
        layout.addWidget(self.chat_controls)
        self.chat_controls_toggle.toggled.connect(self.chat_controls.setVisible)
        self.chat_controls_toggle.toggled.connect(
            lambda opened: self.chat_controls_toggle.setText(
                "Połączenie i model ▾" if opened else "Połączenie i model ▸"))
        self.chat_controls.hide()

        self.conversation = ChatTranscript()
        self.conversation.setObjectName("workbenchChatTranscript")
        self.conversation.setAccessibleName("Historia lokalnej rozmowy")
        self.conversation.setPlaceholderText(
            "Tutaj pojawią się wiadomości i odpowiedzi pochodzące z zaakceptowanych tur.")
        self.conversation.setMinimumHeight(220)
        layout.addWidget(self.conversation, 3)
        self._chat_history_generation = 0
        self._selected_chat_session_id: str | None = None
        self._chat_history_loader = HistoryDelivery(self)
        self._chat_history_loader.arrived.connect(self._present_chat_history)

        # Non-authoritative UI activity: a timer is a visual heartbeat, NOT
        # evidence of daemon admission, model thinking or accepted finalization.
        self.chat_activity = QLabel("")
        self.chat_activity.setObjectName("workbenchChatActivity")
        self.chat_activity.setAccessibleName("Postęp obsługi wiadomości")
        self.chat_activity.setWordWrap(True)
        self.chat_activity.hide()
        layout.addWidget(self.chat_activity)
        self._chat_activity_request = None
        self._chat_activity_message = ""
        self._chat_activity_frame = 0
        self.chat_activity_timer = QTimer(self)
        self.chat_activity_timer.setInterval(450)
        self.chat_activity_timer.timeout.connect(self._animate_chat_activity)

        self.chat_history_toggle = QPushButton("Historia operacji ▸")
        self.chat_history_toggle.setCheckable(True)
        self.chat_history_toggle.setAccessibleName("Pokaż lub ukryj historię techniczną rozmowy")
        layout.addWidget(self.chat_history_toggle)
        self.chat_history_panel = QWidget()
        chat_history_layout = QVBoxLayout(self.chat_history_panel)
        chat_history_layout.setContentsMargins(0, 0, 0, 4)
        chat_history_layout.addWidget(self.chat_state)
        self.chat_operation_history = QPlainTextEdit()
        self.chat_operation_history.setObjectName("workbenchChatOperationHistory")
        self.chat_operation_history.setAccessibleName("Historia zdarzeń transportu i request ID")
        self.chat_operation_history.setReadOnly(True)
        self.chat_operation_history.setMaximumBlockCount(150)
        self.chat_operation_history.setMaximumHeight(95)
        chat_history_layout.addWidget(self.chat_operation_history)
        layout.addWidget(self.chat_history_panel)
        self.chat_history_toggle.toggled.connect(self.chat_history_panel.setVisible)
        self.chat_history_toggle.toggled.connect(
            lambda opened: self.chat_history_toggle.setText(
                "Historia operacji ▾" if opened else "Historia operacji ▸"))
        self.chat_history_panel.hide()

        composer = QHBoxLayout()
        self.message = QPlainTextEdit()
        self.message.setObjectName("workbenchChatComposer")
        self.message.setPlaceholderText("Napisz wiadomość do lokalnej Jaźni…")
        self.message.setAccessibleName("Wiadomość do runtime Jaźni")
        self.message.setMaximumHeight(100)
        composer.addWidget(self.message, 1)
        self.send_button = self.button("Wyślij", self.send_chat, composer)
        self.send_button.setObjectName("jssPrimaryAction")
        layout.addLayout(composer)

    def _record_chat_diagnostic(self: Any, message: str) -> None:
        """Keep raw transport identifiers only in the opted-in history."""
        safe = self.core.redactor.text(str(message))[:500]
        self.chat_state.setText(safe)
        self.chat_operation_history.appendPlainText(safe)

    def _animate_chat_activity(self: Any) -> None:
        if self._chat_activity_request is None:
            self.chat_activity_timer.stop()
            return
        self._chat_activity_frame = (self._chat_activity_frame + 1) % 4
        dots = "." * (self._chat_activity_frame or 3)
        self.chat_activity.setText(self._chat_activity_message + dots)

    def _begin_chat_activity(self: Any, request: str, message: str) -> None:
        """Start a purely visual indicator, never a second runtime request."""
        self._chat_activity_request = request
        self._chat_activity_message = message
        self._chat_activity_frame = 0
        self.chat_activity.setText(message + "...")
        self.chat_activity.show()
        self.chat_activity_timer.start()
        self.send_button.setEnabled(False)

    def _end_chat_activity(self: Any, warning: str = "") -> None:
        self._chat_activity_request = None
        self.chat_activity_timer.stop()
        if warning:
            self.chat_activity.setText(warning)
            self.chat_activity.show()
        else:
            self.chat_activity.hide()
            self.chat_activity.clear()
        chat = self.core.chat
        self.send_button.setEnabled(chat is None or not chat.pending)

    def _remember_active_chat_session(self: Any) -> None:
        """Metadata only; real message content stays in canonical SYSTEM."""
        if self.core.chat is None:
            return
        session_id = getattr(self.core.chat, "session_id", None)
        if not isinstance(session_id, str) or not session_id:
            return  # Synthetic transports in compatibility tests.
        from .chat_session_catalog import remember_session
        try:
            remember_session(self.core.root, session_id, self.core.chat.daemon_url)
            self.refresh_local_conversations()
        except (OSError, ValueError, StudioError):
            self._record_chat_diagnostic(
                "Nie udało się zapisać listy sesji; aktywna tura i jej checkpoint pozostają nienaruszone.")

    def refresh_local_conversations(self: Any) -> None:
        """No daemon calls, no private text copied to the sidebar."""
        from .chat_session_catalog import load_sessions
        from .core import settings_path
        try:
            sessions = load_sessions(self.core.root)
        except (OSError, ValueError, StudioError):
            sessions = []
            self.statusBar().showMessage("Lista rozmów niezweryfikowana; nie modyfikowano zapisów.")
        current = self.core.chat.session_id if self.core.chat is not None else None
        if current is None:
            checkpoint = settings_path(self.core.root).with_name("chat-checkpoint.json")
            try:
                if checkpoint.is_file() and checkpoint.stat().st_size <= 4096:
                    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
                    value = saved.get("session_id")
                    if (isinstance(value, str)
                            and saved.get("daemon_url") == self.core.settings.daemon_url):
                        from .chat_session_catalog import SESSION_ID
                        if SESSION_ID.fullmatch(value):
                            current = value
            except (OSError, ValueError, UnicodeError):
                pass
        known = {entry["session_id"] for entry in sessions}
        if current and current not in known:
            sessions.insert(0, {"session_id": current, "created_at_utc": "",
                                "daemon_url": self.core.settings.daemon_url})
        self.chat_session_list.blockSignals(True)
        self.chat_session_list.clear()
        for entry in sessions:
            sid = entry["session_id"]
            label = ("Bieżąca rozmowa" if sid == current else "Rozmowa") + (
                " • " + visible_time(entry["created_at_utc"]) if entry["created_at_utc"] else "")
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(label, self.chat_session_list)
            item.setData(Qt.ItemDataRole.UserRole, sid)
            if sid == current:
                self.chat_session_list.setCurrentItem(item)
        self.chat_session_list.blockSignals(False)
        if hasattr(self, "workbench"):
            self.workbench.apply_activity_filter()

    def _load_local_chat_history(self: Any, session_id: str) -> None:
        """Read accepted canonical turns off the GUI thread; never replay them."""
        self._chat_history_generation += 1
        generation = self._chat_history_generation
        self.conversation.clear()

        def load() -> None:
            from latka_jazn.core.conversation_state_store import ConversationStateStore
            try:
                projection = ConversationStateStore(self.core.root).load_context_projection(
                    # UI history must not use the model's small context
                    # budget to truncate visible user/assistant messages.
                    # Only pagination (80 whole turns) limits this view.
                    session_id, max_turns=80, max_chars=1_000_000_000)
            except (OSError, ValueError, RuntimeError):
                projection = {"session_id": session_id, "turns": [], "error": "history_unavailable"}
            self._chat_history_loader.arrived.emit(session_id, generation, projection)

        threading.Thread(target=load, daemon=True).start()

    def _present_chat_history(self: Any, session_id: str, generation: int,
                              projection: object) -> None:
        if (generation != self._chat_history_generation or
                session_id != self._selected_chat_session_id):
            return
        if self.core.chat is not None and self.core.chat.pending:
            return
        if not isinstance(projection, dict) or projection.get("session_id") != session_id:
            return
        if projection.get("error"):
            self._record_chat_diagnostic("Historia niedostępna; nie zmieniono trwałych danych.")
            return
        self.conversation.clear()
        for record in projection.get("turns", []):
            if not isinstance(record, dict):
                continue
            user_text = record.get("user_text")
            assistant_text = record.get("assistant_text")
            if isinstance(user_text, str) and user_text:
                # Old canonical records contain acceptance time, not the
                # original user's send time. Do NOT present it as such.
                self.conversation.append_message("user", user_text, timestamp=None)
            if isinstance(assistant_text, str) and assistant_text:
                self.conversation.append_message(
                    "assistant", assistant_text,
                    timestamp=record.get("accepted_at_utc"),
                    timestamp_kind="zaakceptowano")
        if projection.get("omitted_turn_count"):
            self._record_chat_diagnostic(
                "Załadowano wyłącznie najnowsze zweryfikowane tury; starsze pozostają w kanonicznym magazynie.")

    def select_local_conversation(self: Any, session_id: str,
                                  *, create: bool = False) -> None:
        """Never transfer a conversation between daemon endpoint identities."""
        from .chat_session_catalog import SESSION_ID, remember_session, load_sessions
        from .chat import ChatClient
        if not isinstance(session_id, str) or SESSION_ID.fullmatch(session_id) is None:
            raise StudioError("Nieprawidłowy identyfikator rozmowy")
        known = next((entry for entry in load_sessions(self.core.root)
                      if entry["session_id"] == session_id), None)
        if not create and known is not None and known["daemon_url"] != self.core.settings.daemon_url:
            raise StudioError("Rozmowa należy do innego endpointu; nie przełączono sesji")
        client = self.core.chat if self.core.chat is not None else ChatClient(self.core)
        if (not create and client.session_id == session_id
                and self._selected_chat_session_id == session_id):
            # Clicking the current conversation is navigation, not a
            # dangerous session transition during an in-flight request.
            self.navigate("Czat lokalny")
            return
        if not create and known is None and client.session_id != session_id:
            raise StudioError("Rozmowa nie ma zweryfikowanego powiązania z daemonem")
        client.select_session(session_id)
        self.core.chat = client
        remember_session(self.core.root, session_id, self.core.chat.daemon_url)
        self._selected_chat_session_id = session_id
        self._end_chat_activity()
        self.refresh_local_conversations()
        self._load_local_chat_history(session_id)
        self.navigate("Czat lokalny")

    def new_local_conversation(self: Any) -> None:
        """New local session ID, never a clone/replay of a pending request."""
        session_id = "studio-" + uuid4().hex
        self.select_local_conversation(session_id, create=True)
        self._record_chat_diagnostic(
            "Nowa rozmowa jest gotowa do połączenia. Nie wysłano żadnej wiadomości.")

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
        self._record_chat_diagnostic(
            "Wybrano model " + chosen + ". Połącz czat, aby sprawdzić rzeczywistą generację.")


    def connect_local_chat(self: Any) -> None:
        """Never bypass the first-run model and matching daemon evidence via sidebar."""
        if not (self.quick_runtime_ready and self.quick_generation_ready
                and self.core.settings.model):
            raise StudioError(
                "Najpierw w Pulpicie sprawdź zgodność runtime oraz uruchom "
                "test generacji wybranego modelu Ollama."
            )
        self.core.connect_chat()
        self.refresh_local_conversations()
        if self.core.chat is not None:
            self._selected_chat_session_id = self.core.chat.session_id
            self._remember_active_chat_session()


    def send_chat(self: Any) -> None:
        if self.core.chat is None:
            raise StudioError("Najpierw połącz czat")
        text = self.message.toPlainText()
        request = self.core.chat.send(text)
        self.conversation.append_message(
            "user", text, timestamp=datetime.now(timezone.utc),
            timestamp_kind="wysłano")
        self.message.clear()
        self._record_chat_diagnostic("Oczekiwanie na wynik: " + request)
        self._begin_chat_activity(request, "Jaźń obsługuje wiadomość")
        self._remember_active_chat_session()


    def resume_chat(self: Any) -> None:
        if self.core.chat is None:
            from .chat import ChatClient
            self.core.chat = ChatClient(self.core)
        self.core.chat.resume()
        if self.core.chat.pending:
            self._begin_chat_activity(self.core.chat.pending, "Sprawdzanie poprzedniego wyniku")

    def close_failed_chat(self: Any) -> None:
        chat = self.core.chat
        if chat is None or not chat.can_resolve_terminal_failure():
            raise StudioError(
                "Brak potwierdzonego terminalnego błędu. Samo chat_job_not_found "
                "nie upoważnia do porzucenia checkpointu."
            )
        request_id = chat.pending
        if not request_id:
            raise StudioError("Brak oczekującego request_id")
        choice = QMessageBox.question(
            self, "Zamknięcie nieudanej tury",
            "Daemon potwierdził terminalne niepowodzenie. "
            "Zarchiwizować ten błąd i odblokować możliwość wysłania "
            "nowej wiadomości? Poprzednia tura nie zostanie powtórzona.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        chat.resolve_terminal_failure(request_id)
        self._end_chat_activity()
        self._record_chat_diagnostic(
            "Nieudaną turę zarchiwizowano bez przypisania jej "
            "zaakceptowanej odpowiedzi."
        )
