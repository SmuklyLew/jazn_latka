"""Qt presentation, independent from Jaźń, JSS and daemon lifecycle."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .probe import SERVICES, snapshot

LABELS = {
    "ready": "GOTOWY", "reachable": "DOSTĘPNY", "unknown": "NIEZWERYFIKOWANY",
    "disabled": "WYŁĄCZONA", "error": "BŁĄD TOŻSAMOŚCI",
}
COLORS = {
    "ready": "#218449", "reachable": "#a57a28", "unknown": "#717a85",
    "disabled": "#717a85", "error": "#ba3b4b",
}


class ProbeThread(QThread):
    observed = Signal(object)

    def __init__(self, root: Path | None, daemon_port: int, ollama_port: int) -> None:
        super().__init__()
        self.root = root
        self.daemon_port = daemon_port
        self.ollama_port = ollama_port

    def run(self) -> None:
        try:
            result = snapshot(self.root, daemon_port=self.daemon_port,
                              ollama_port=self.ollama_port)
        except (OSError, RuntimeError, ValueError):
            result = {"services": {}, "observed_at_utc": None}
        self.observed.emit(result)


class MonitorWindow(QMainWindow):
    def __init__(self, root: Path | None, daemon_port: int,
                 ollama_port: int, *, smoke: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("Jaźń Monitor — tylko odczyt")
        self.resize(870, 490)
        self.daemon_port = daemon_port
        self.ollama_port = ollama_port
        self._worker: ProbeThread | None = None
        self._closing = False
        area = QWidget(self)
        self.setCentralWidget(area)
        layout = QVBoxLayout(area)

        heading = QLabel("Jaźń Monitor | daemon, runtime i usługi")
        heading.setStyleSheet("font-size: 17px; font-weight: 600")
        layout.addWidget(heading)
        row = QHBoxLayout()
        row.addWidget(QLabel("SYSTEM ROOT:"))
        self.root_field = QLineEdit(str(root) if root else "")
        self.root_field.setPlaceholderText("Wybierz katalog zawierający run.py")
        self.root_field.setAccessibleName("Katalog instalacji Jaźni")
        row.addWidget(self.root_field, 1)
        browse = QPushButton("Wybierz…")
        browse.clicked.connect(self.choose_root)
        row.addWidget(browse)
        self.refresh_button = QPushButton("Odśwież")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)

        self.table = QTableWidget(len(SERVICES), 3)
        self.table.setHorizontalHeaderLabels(["Usługa", "Stan", "Dowody / uwagi"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for i, name in enumerate(SERVICES):
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(LABELS["unknown"]))
            self.table.setItem(i, 2, QTableWidgetItem("Oczekiwanie na odczyt"))
        layout.addWidget(self.table)

        self.footer = QLabel(
            "Tylko obserwacja. Zamknięcie monitora nie zatrzyma daemona. "
            "/live ≠ /ready ≠ zaakceptowana odpowiedź.")
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)
        if not smoke:
            self.timer.start()
            QTimer.singleShot(0, self.refresh)

    def choose_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Wybierz SYSTEM ROOT",
                                                 self.root_field.text())
        if path:
            self.root_field.setText(path)
            self.refresh()

    def refresh(self) -> None:
        if self._closing or (self._worker is not None and self._worker.isRunning()):
            return
        raw = self.root_field.text().strip()
        self._worker = ProbeThread(Path(raw) if raw else None,
                                   self.daemon_port, self.ollama_port)
        self._worker.observed.connect(self.apply_snapshot)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def apply_snapshot(self, report: dict[str, Any]) -> None:
        services = report.get("services") or {}
        for i, name in enumerate(SERVICES):
            data = services.get(name) or {}
            status = str(data.get("state") or "unknown")
            if status not in LABELS:
                status = "unknown"
            state = QTableWidgetItem(LABELS[status])
            state.setForeground(QColor(COLORS[status]))
            self.table.setItem(i, 1, state)
            self.table.setItem(i, 2, QTableWidgetItem(
                str(data.get("detail") or "Brak zweryfikowanego statusu")))
        self.footer.setText(
            "Odczyt UTC: " + str(report.get("observed_at_utc") or "UNKNOWN") +
            " • tylko obserwacja • zamknięcie nie zatrzymuje daemona")

    def closeEvent(self, event: Any) -> None:
        self._closing = True
        self.timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(6000)
        event.accept()
