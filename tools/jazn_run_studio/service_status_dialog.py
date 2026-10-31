"""Non-modal, read-only service status window for Jaźń Studio.

Status reflects fresh operator observations, not ownership or permission to start
services. The window never probes synchronously on the Qt GUI thread.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

# A visible caption always accompanies each colored circle.
STATUS_COLORS = {"good": "#32C77A", "warn": "#E8A13B", "bad": "#E2525D"}
STATUS_LABELS = {"good": "Działa", "warn": "Niezweryfikowany / ograniczony", "bad": "Błąd"}
MAX_OBSERVATION_AGE_SECONDS = 45.0


def assess_service(key: str, evidence: dict[str, Any] | None, *, failed: bool = False,
                   age_seconds: float = 0.0) -> tuple[str, str]:
    """Classify explicit evidence only. No PID-only or model-name-only green."""
    if failed:
        return "bad", "Ostatnia kontrola zakończyła się niepowodzeniem"
    if evidence is None:
        return "warn", "Nie sprawdzono — użyj Odśwież"
    if age_seconds > MAX_OBSERVATION_AGE_SECONDS:
        return "warn", "Wynik nieaktualny — ponów kontrolę"

    if key in {"server", "runtime"}:
        state = evidence.get("active_state")
        if state in {"inactive", "dead", "stopped"}:
            return "bad", "Daemon nieaktywny"
        identity = ("endpoint_reachable", "process_identity_confirmed",
                    "endpoint_identity_matches", "heartbeat_fresh",
                    "root_matches", "version_matches")
        if any(evidence.get(name) is False for name in identity):
            return "bad", "Niepotwierdzona tożsamość lub dostępność daemona"
        if state != "active_trusted" or not all(evidence.get(name) is True for name in identity):
            return "warn", "Brak kompletnego dowodu gotowości i tożsamości"
        if key == "server":
            return "good", "Endpoint, PID, instancja, ROOT i heartbeat zgodne"
        if evidence.get("conversation_ready") is True:
            return "good", "Zweryfikowana gotowość rozmowy"
        return "warn", "Daemon działa, lecz gotowość rozmowy niepotwierdzona"

    if key == "mcp":
        if evidence.get("ready") is True and evidence.get("gateway_live") is True:
            return "good", "Lokalna brama MCP gotowa (nie potwierdza ChatGPT)"
        if evidence.get("endpoint_reachable") is True:
            return "warn", "Endpoint odpowiada, lecz brama nie potwierdza gotowości"
        return "warn", "Gotowość lokalnej bramy niepotwierdzona"

    if key == "ollama":
        if evidence.get("endpoint_reachable") is not True:
            return "warn", "Brak dowodu dostępności API"
        if evidence.get("selected_model_present") is False:
            return "warn", "API odpowiada, lecz wybranego modelu brak"
        if (evidence.get("selected_model_present") is True
                and evidence.get("generation_verified") is True):
            return "good", "API i generacja wybranego modelu potwierdzone"
        return "warn", "API odpowiada; generacja modelu niezweryfikowana"

    raise ValueError("Nieznany wskaźnik usługi")


class ServiceStatusDialog(QDialog):
    """Closable independent window backed only by Controller event evidence."""

    SERVICES = (
        ("server", "Serwer Jaźni / daemon"),
        ("runtime", "Runtime rozmów"),
        ("mcp", "Brama MCP"),
        ("ollama", "Ollama i wybrany model"),
    )

    def __init__(self, host: QWidget, request_refresh: Callable[[], None]):
        super().__init__(host)
        self._request_refresh = request_refresh
        self.setObjectName("jssServiceStatusDialog")
        self.setWindowTitle("Jaźń — Stany usług")
        self.setModal(False)
        self.setMinimumWidth(430)
        self.resize(520, 330)
        self.samples: dict[str, tuple[float, dict[str, Any]]] = {}
        self.failures: set[str] = set()
        self.indicators: dict[str, tuple[QLabel, QLabel]] = {}

        layout = QVBoxLayout(self)
        subtitle = QLabel("Odczyt z lokalnych testów. Żaden wskaźnik nie uruchamia usługi ani nie potwierdza odpowiedzi ChatGPT.")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        for key, title in self.SERVICES:
            row = QHBoxLayout()
            circle = QLabel("●")
            circle.setFixedWidth(25)
            circle.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
            label = QLabel(title)
            label.setMinimumWidth(160)
            status = QLabel("Nie sprawdzono")
            status.setWordWrap(True)
            status.setAccessibleName("Stan: " + title)
            row.addWidget(circle)
            row.addWidget(label)
            row.addWidget(status, 1)
            layout.addLayout(row)
            self.indicators[key] = (circle, status)
        layout.addStretch(1)
        note = QLabel("Zielony = potwierdzony odpowiednim dowodem; pomarańczowy = brak / nieaktualny dowód; czerwony = potwierdzona awaria.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        refresh = QPushButton("Odśwież stany")
        refresh.setAccessibleName("Sprawdź lokalnie Runtime, MCP i Ollamę")
        refresh.clicked.connect(self.request_refresh)
        close = QPushButton("Zamknij")
        close.clicked.connect(self.close)
        buttons.addWidget(refresh)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.render_statuses)
        self.timer.start()
        self.render_statuses()

    def request_refresh(self) -> None:
        # A click is an explicit request for the existing nonblocking Controller
        # jobs; never call HTTP or lifecycle directly in this widget.
        self.samples.clear()
        self.failures.clear()
        self.render_statuses()
        self._request_refresh()

    def observe(self, key: str, kind: str, value: object) -> None:
        if kind == "evidence" and isinstance(value, dict):
            for service in ("server", "runtime"):
                self.samples[service] = (time.monotonic(), dict(value))
                self.failures.discard(service)
        elif kind == "probe" and isinstance(value, dict):
            service = {"gateway": "mcp", "ollama": "ollama"}.get(str(value.get("service", "")))
            if service:
                self.samples[service] = (time.monotonic(), dict(value))
                self.failures.discard(service)
        elif kind == "state" and isinstance(value, dict) and value.get("state") == "failed":
            failed_service = {"status": ("server", "runtime"),
                              "probe:gateway": ("mcp",),
                              "probe:ollama": ("ollama",),
                              "probe:ollama_generate": ("ollama",)}.get(key, ())
            self.failures.update(failed_service)
        if self.isVisible():
            self.render_statuses()

    def render_statuses(self) -> None:
        now = time.monotonic()
        for key, _title in self.SERVICES:
            observed = self.samples.get(key)
            state, detail = assess_service(
                key,
                observed[1] if observed else None,
                failed=key in self.failures,
                age_seconds=now - observed[0] if observed else 0.0,
            )
            circle, caption = self.indicators[key]
            circle.setStyleSheet("color: " + STATUS_COLORS[state] + "; font-size: 19px;")
            circle.setAccessibleName(STATUS_LABELS[state])
            caption.setText(STATUS_LABELS[state] + " — " + detail)
            caption.setToolTip(detail)
