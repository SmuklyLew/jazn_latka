"""Events area of the JSS desktop workbench.

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

class EventViewMixin:
    def poll(self: Any) -> None:
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
            if self.service_status_dialog is not None and kind in {"evidence", "probe", "state"}:
                self.service_status_dialog.observe(key, kind, value)
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
