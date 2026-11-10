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
from .core import OLLAMA_GENERATION_PROOF_SECONDS


def assess_service(key: str, evidence: dict[str, Any] | None, *, failed: bool = False,
                   age_seconds: float = 0.0) -> tuple[str, str]:
    """Classify explicit evidence only. No PID-only or model-name-only green."""
    if failed:
        # The observer distinguishes a normal "not ready" response from an
        # unexpected probe failure before calling assess_service(). Only the
        # latter enters the failures set; optionality cannot hide a real fault.
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

    if key == "mcp_https":
        if (evidence.get("ready") is True
                and evidence.get("authenticated_mcp_ready") is True
                and evidence.get("runtime_ready") is True):
            return "good", "Zweryfikowana brama HTTPS, OAuth i runtime"
        if evidence.get("endpoint_reachable") is True:
            return "warn", "HTTPS dostępny; OAuth i runtime wymagają osobnego dowodu"
        return "warn", "MCP HTTPS niepotwierdzone lub nieskonfigurowane"

    if key == "supervisor":
        if (evidence.get("ready") is True
                and evidence.get("identity_confirmed") is True
                and evidence.get("heartbeat_fresh") is True):
            return "good", "Supervisor: tożsamość i heartbeat potwierdzone"
        if evidence.get("active") is False:
            return "warn", "Supervisor nieaktywny — nie uruchamiano go"
        return "warn", "Supervisor bez pełnego dowodu tożsamości"

    if key == "memory":
        if evidence.get("mode") == "off":
            return "warn", "MEMORY wyłączona konfiguracją (off)"
        if (evidence.get("full_autobiographical_recall_ready") is True
                and evidence.get("continuity_ready") is True):
            return "good", "Autobiograficzny recall i ciągłość potwierdzone"
        if evidence.get("memory_search_ready") is True:
            return "warn", "Wyszukiwanie dostępne, ciągłość niepotwierdzona"
        return "warn", "Brak dowodu recall i ciągłości MEMORY"

    if key == "ollama":
        proof_age = evidence.get("generation_evidence_age_seconds")
        if (proof_age is not None and (
                not isinstance(proof_age, (int, float))
                or proof_age + age_seconds > OLLAMA_GENERATION_PROOF_SECONDS)):
            return "warn", "API odpowiada; ostatni dowód generowania wygasł — ponów test"
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
        ("ollama", "Ollama i wybrany model"),
        ("mcp", "MCP lokalne"),
        ("mcp_https", "MCP HTTPS / OAuth"),
        ("supervisor", "Supervisor"),
        ("memory", "MEMORY / ciągłość"),
    )

    def __init__(self, host: QWidget, request_refresh: Callable[[], None]):
        super().__init__(host)
        self._request_refresh = request_refresh
        self.setObjectName("jssServiceStatusDialog")
        self.setWindowTitle("Jaźń — Stany usług")
        self.setModal(False)
        self.setMinimumWidth(430)
        self.resize(700, 460)
        self.samples: dict[str, tuple[float, dict[str, Any]]] = {}
        self.failures: set[str] = set()
        self.indicators: dict[str, tuple[QLabel, QLabel]] = {}

        layout = QVBoxLayout(self)
        subtitle = QLabel("Monitor tylko do odczytu: co 30 s odświeża status dostępnych usług. Nie uruchamia, nie zatrzymuje ani nie konfiguruje procesów. Nie potwierdza odpowiedzi ChatGPT.")
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
        refresh.setAccessibleName("Odczytaj status usług bez ich uruchamiania")
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
        # Separate polling from rendering. Only the visible monitor requests
        # existing asynchronous, read-only Controller probes; no lifecycle.
        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(30_000)
        self.monitor_timer.timeout.connect(self._monitor_once)
        self.render_statuses()

    def _monitor_once(self) -> None:
        if self.isVisible():
            # Controller deduplicates in-flight read probes; no model generation
            # or mutation is performed by this observer.
            self._request_refresh()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.monitor_timer.start()

    def hideEvent(self, event: Any) -> None:
        self.monitor_timer.stop()
        super().hideEvent(event)

    def request_refresh(self) -> None:
        # Keep the previous sample visible (and aging) until an actual result
        # arrives. Clearing first would temporarily misrepresent a live daemon.
        self._request_refresh()

    def invalidate_ollama_model(self) -> None:
        """Drop old model evidence immediately when operator changes selection."""
        self.samples.pop("ollama", None)
        self.failures.discard("ollama")
        self.render_statuses()

    def observe(self, key: str, kind: str, value: object) -> None:
        if kind == "evidence" and isinstance(value, dict) and key == "status":
            for service in ("server", "runtime"):
                self.samples[service] = (time.monotonic(), dict(value))
                self.failures.discard(service)
        elif kind == "supervisor_evidence" and isinstance(value, dict):
            self.samples["supervisor"] = (time.monotonic(), dict(value))
            self.failures.discard("supervisor")
        elif kind == "status_summary" and isinstance(value, dict):
            description = str(value.get("memory") or "")
            previous = self.samples.get("memory")
            payload = dict(previous[1]) if previous else {}
            payload["mode"] = "off" if ("(off)" in description or "wyłączona przez konfigurację" in description) else "unknown"
            self.samples["memory"] = (time.monotonic(), payload)
        elif kind == "memory_evidence" and isinstance(value, dict):
            previous = self.samples.get("memory")
            payload = dict(value)
            if previous and previous[1].get("mode") == "off":
                payload["mode"] = "off"
            self.samples["memory"] = (time.monotonic(), payload)
            self.failures.discard("memory")
        elif kind == "probe" and isinstance(value, dict):
            service = {
                "gateway": "mcp", "ollama": "ollama",
                "cloudflare": "mcp_https",
            }.get(str(value.get("service", "")))
            if service:
                self.samples[service] = (time.monotonic(), dict(value))
                self.failures.discard(service)
        elif kind == "state" and isinstance(value, dict) and value.get("state") == "failed":
            failed_service = {
                "status": ("server", "runtime"),
                "supervisor": ("supervisor",),
                "probe:gateway": ("mcp",),
                "probe:cloudflare": ("mcp_https",),
                "probe:ollama": ("ollama",),
                "probe:ollama_generate": ("ollama",),
            }.get(key, ())
            # A completed optional probe can truthfully report "not ready"
            # without establishing a service fault. Keep its negative sample
            # visible as a warning; transport exceptions remain real failures.
            unready = {
                "service_not_ready", "selected_model_missing",
                "ollama_models_empty", "ollama_generation_unverified",
            }
            if not (key.startswith("probe:") and str(value.get("error") or "") in unready):
                self.failures.update(failed_service)
        # Keep the read-only projection current while hidden as well: opening
        # or reopening the window must not briefly expose an earlier sample.
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
