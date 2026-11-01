"""Services area of the JSS desktop workbench.

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

class ServiceViewMixin:
    def _services(self: Any) -> None:
        layout = self.page("Usługi i procesy", "Status, własność procesu i gotowość są niezależnymi dowodami. Start/Stop/Restart korzystają z kanonicznych kontrolerów.")
        self.services_table = QTableWidget(6, 6)
        self.services_table.setHorizontalHeaderLabels(["Usługa", "Status", "PID", "Port", "Readiness", "Akcje"])
        self.services_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.services_table.horizontalHeader().setStretchLastSection(False)
        self.services_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.services_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.services_table.setMinimumWidth(0)
        self.services_table.setMinimumHeight(350)
        self.service_rows = {}
        self.supervisor_observation: dict = {}
        self.memory_observed = False
        for row, (service, title) in enumerate((("runtime", "Jaźń"), ("ollama", "Ollama"), ("gateway", "MCP lokalne"), ("cloudflare", "MCP HTTPS"), ("supervisor", "Supervisor"), ("memory", "MEMORY"))):
            self.service_rows[service] = row
            self.services_table.setItem(row, 0, QTableWidgetItem(title))
            status = QLabel("Nie sprawdzono")
            status.setTextFormat(Qt.TextFormat.PlainText)
            status.setWordWrap(True)
            status.setMinimumWidth(0)
            self.statuses[service] = status
            self.services_table.setCellWidget(row, 1, status)
            for column in (2, 3, 4):
                self.services_table.setItem(row, column, QTableWidgetItem("—"))
            button = QPushButton("Akcje ▾")
            menu = QMenu(button)
            if service in {"runtime", "ollama", "gateway"}:
                for op, label in (("start", "Start"), ("stop", "Stop"), ("restart", "Restart")):
                    action = menu.addAction(label)
                    action.triggered.connect(lambda _checked=False, s=service, o=op: self.guard(lambda: self.service(s, o)))
            config = menu.addAction("Konfiguracja")
            config.triggered.connect(lambda: self.navigate("Ustawienia"))
            logs = menu.addAction("Logi")
            logs.triggered.connect(lambda _checked=False, s=service: self.show_log("status" if s in {"runtime", "memory"} else "supervisor" if s == "supervisor" else "service:" + s))
            details = menu.addAction("Szczegóły / odśwież")
            details.triggered.connect(lambda _checked=False, s=service: self.guard(lambda: self.inspect_service(s)))
            button.setMenu(menu)
            self.services_table.setCellWidget(row, 5, button)
        self.services_table.setColumnWidth(0, 105)
        self.services_table.setColumnWidth(1, 190)
        self.services_table.setColumnWidth(2, 45)
        self.services_table.setColumnWidth(3, 55)
        self.services_table.setColumnWidth(5, 85)
        self.services_table.verticalHeader().setDefaultSectionSize(64)
        layout.addWidget(self.services_table)
        self.service_selected_label = QLabel("Wybierz moduł i dostępną operację.")
        self.service_selected_label.setWordWrap(True)
        layout.addWidget(self.service_selected_label)
        controls = QHBoxLayout()
        self.service_start_button = self.button("Start", lambda: self.selected_service_action("start"), controls)
        self.service_stop_button = self.button("Stop", lambda: self.selected_service_action("stop"), controls)
        self.service_restart_button = self.button("Restart", lambda: self.selected_service_action("restart"), controls)
        self.button("Status", lambda: self.selected_service_action("inspect"), controls)
        self.button("Logi", lambda: self.show_log(
            "status" if self.selected_service() in {"runtime", "memory"} else
            "supervisor" if self.selected_service() == "supervisor" else
            "service:" + self.selected_service()), controls)
        layout.addLayout(controls)
        self.services_table.itemSelectionChanged.connect(self.refresh_service_controls)
        self.services_table.selectRow(0)
        self.refresh_service_controls()
        self.button("Odśwież stan wszystkich modułów", self.refresh_services, layout)
        self.button("Sprawdź usługę Windows cloudflared", lambda: self.core.probe("tunnel_service"), layout)
        remote_note = QLabel("Cloudflare, supervisor i MEMORY: odczyt bez przejmowania procesów lub prywatnych danych. Lokalny MCP nie jest publikowany publicznie. Nie ma automatycznego Start All/Stop All; zamknięcie Studio nie zatrzymuje daemona.")
        remote_note.setWordWrap(True)
        layout.addWidget(remote_note)
        self.processes = QPlainTextEdit()
        self.processes.setReadOnly(True)
        self.processes.setMaximumHeight(150)
        if self.unified_operator_mode:
            self.processes.hide()
            self.button("Dane techniczne i historia usług", lambda: self.workspace.show(4), layout)
        else:
            layout.addWidget(self.processes)


    def selected_service(self: Any) -> str:
        row = self.services_table.currentRow()
        return next((key for key, index in self.service_rows.items() if index == row), "")


    def inspect_service(self: Any, service: str) -> None:
        if service in {"runtime", "memory"}:
            self.core.start_action("status")
        elif service == "supervisor":
            self.core.start_action("supervisor")
        else:
            self.core.probe(service)


    def selected_service_action(self: Any, operation: str) -> None:
        service = self.selected_service()
        if not service:
            raise StudioError("Wybierz moduł")
        if operation == "inspect":
            self.inspect_service(service)
        elif service in {"runtime", "ollama", "gateway"}:
            self.service(service, operation)
        else:
            raise StudioError("Ten moduł ma tylko diagnostykę; nie przejmuj obcego procesu")


    def refresh_service_controls(self: Any) -> None:
        service = self.selected_service()
        with self.core.lock:
            job = self.core.jobs.get("service:" + service)
            owned = (job is not None and job.proc is not None and not job.done.is_set()
                     and job.proc.poll() is None)
        running = service == "runtime" and self.quick_runtime_ready
        managed = service in {"ollama", "gateway"}
        self.service_start_button.setEnabled((service == "runtime" and not running) or (managed and not owned))
        self.service_stop_button.setEnabled(running or (managed and owned))
        self.service_restart_button.setEnabled(running or (managed and owned))
        note = {
            "runtime": "kanoniczny daemon; Stop/Restart wymagają zweryfikowanej gotowości",
            "ollama": "Stop dotyczy wyłącznie procesu uruchomionego przez Studio",
            "gateway": "lokalny MCP 127.0.0.1, bez publicznej ekspozycji",
            "cloudflare": "publiczny HTTPS, tylko diagnostyka; wdrożenie i OAuth osobno",
            "supervisor": "tożsamość i heartbeat nadzorcy; bez przejmowania procesu",
            "memory": "oddzielna zdolność; stan techniczny nie potwierdza recall",
        }.get(service, "wybierz moduł")
        self.service_selected_label.setText(service.upper() + " — " + note if service else note)


    def refresh_services(self: Any) -> None:
        """Explicit, read-only probes; no silent auto-start or PID adoption."""
        self.core.start_action("status")
        self.core.start_action("supervisor")
        self.core.probe("ollama")
        self.core.probe("gateway")
        if self.core.settings.cloudflare_url:
            self.core.probe("cloudflare")
        else:
            self.update_service_summary("cloudflare", "Nie skonfigurowano • brak adresu HTTPS")


    def service(self: Any, service: str, op: str) -> None:
        if service == "runtime":
            if op in {"stop", "restart"} and QMessageBox.question(self, "Runtime Jaźni", "Potwierdzić kanoniczny " + op + " runtime Jaźni?") != QMessageBox.StandardButton.Yes:
                return
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
        self.show_log("service:" + service)


    def update_service_summary(self: Any, service: str, detail: str) -> None:
        """Mirror the same observed state; never infer readiness from a PID."""
        if service in self.statuses:
            self.statuses[service].setText(detail)
        if service in self.dashboard_statuses:
            self.dashboard_statuses[service].setText(service.upper() + ": " + detail)


    def refresh_service_table(self: Any) -> None:
        from urllib.parse import urlsplit
        ports = {"runtime": str(urlsplit(self.core.settings.daemon_url).port), "ollama": "11434",
                 "gateway": self.core.settings.mcp_port, "cloudflare": "HTTPS", "supervisor": "—", "memory": "—"}
        for service, row in self.service_rows.items():
            from .service_visual_state import visual_state, COLORS, TITLES
            observed = self.supervisor_observation if service == "supervisor" else self.workspace.observations.get(service, {})
            status = visual_state(service, observed if isinstance(observed, dict) else {})
            indicator = self.services_table.item(row, 0)
            if indicator is not None:
                pix = QPixmap(16, 16)
                pix.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pix)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(COLORS[status]))
                painter.drawEllipse(3, 3, 10, 10)
                painter.end()
                indicator.setIcon(QIcon(pix))
                indicator.setToolTip(TITLES[status] + " (nie jest to dowód zaakceptowanej odpowiedzi)")
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
            if service == "memory":
                readiness = "status techniczny" if self.memory_observed else "niezweryfikowana"
            if service == "ollama" and observed.get("endpoint_reachable"):
                readiness = ("API; generacja potwierdzona" if observed.get("generation_verified") is True
                             else "API; brak testu generacji")
            for column, value in ((2, str(pid or "—")), (3, ports[service]), (4, readiness)):
                item = self.services_table.item(row, column)
                if item is not None and item.text() != value:
                    item.setText(value)
                    item.setToolTip(value)
            self.statuses[service].setToolTip(self.statuses[service].text())
        models = self.workspace.observations.get("ollama", {})
        if models:
            self.models_summary.setText("Modele: " + ", ".join(models.get("models", [])) + "\nGeneracja: " + ("potwierdzona" if models.get("generation_verified") else "niezweryfikowana"))


    def open_service_status(self: Any) -> None:
        """Display the read-only, non-modal service indicators."""
        if self.service_status_dialog is None:
            self.service_status_dialog = ServiceStatusDialog(self, lambda: self.guard(self.refresh_services))
        self.service_status_dialog.show()
        self.service_status_dialog.raise_()
        self.service_status_dialog.activateWindow()
        self.service_status_dialog.request_refresh()
