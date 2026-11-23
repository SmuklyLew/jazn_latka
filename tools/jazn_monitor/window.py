"""Qt presentation, independent from Jaźń, JSS and daemon lifecycle."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QLockFile, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QApplication, QMainWindow, QMenu, QPushButton, QSystemTrayIcon, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .probe import SERVICES, snapshot

LABELS = {
    "ready": "GOTOWY", "reachable": "DOSTĘPNY", "unknown": "NIEZWERYFIKOWANY",
    "disabled": "WYŁĄCZONA", "error": "BŁĄD", "stopped": "ZATRZYMANY",
    "unavailable": "NIEDOSTĘPNY",
}
COLORS = {
    "ready": "#218449", "reachable": "#a57a28", "unknown": "#717a85",
    "disabled": "#717a85", "error": "#ba3b4b", "stopped": "#717a85",
    "unavailable": "#a57a28",
}


def _system_tray_available() -> bool:
    return QSystemTrayIcon.isSystemTrayAvailable()


def _monitor_icon() -> QIcon:
    """Draw icon at runtime so PyInstaller needs no external graphics."""
    image = QPixmap(64, 64)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#235A75"))
    painter.drawRoundedRect(3, 3, 58, 58, 15, 15)
    painter.setPen(QColor("#FFFFFF"))
    font = painter.font()
    font.setPixelSize(39)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "J")
    painter.end()
    return QIcon(image)


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
    """One read-only monitor, usable standalone or as a JSS-owned window."""

    snapshot_observed = Signal(object)

    def __init__(self, root: Path | None, daemon_port: int,
                 ollama_port: int, *, smoke: bool = False,
                 integrated: bool = False, parent: QWidget | None = None,
                 interval_seconds: int | None = None) -> None:
        super().__init__(parent)
        self.integrated = integrated
        self._smoke = smoke
        self._fixed_root = Path(root).expanduser().resolve() if integrated and root is not None else None
        self._monitor_lock: QLockFile | None = None
        if integrated and not smoke:
            if self._fixed_root is None:
                raise ValueError("Monitor Jaźni requires the selected JSS root")
            # Exactly the same lock as the standalone jazn_monitor.py entrypoint.
            key = hashlib.sha256(str(self._fixed_root).casefold().encode("utf-8")).hexdigest()[:20]
            lock_dir = Path.home() / ".jazn_monitor"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock = QLockFile(str(lock_dir / (key + ".lock")))
            lock.setStaleLockTime(0)  # long-lived singleton; never steal by age
            if not lock.tryLock(0):
                raise RuntimeError(
                    "Monitor Jaźni już działa dla tej instalacji. "
                    "Zamknij osobny Monitor Jaźni, aby używać go wewnątrz JSS."
                )
            self._monitor_lock = lock
        if interval_seconds is not None and interval_seconds not in {1, 10, 30, 60}:
            raise ValueError("Unsupported JSS monitor interval")
        if integrated:
            self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Tylko odczyt" if not integrated else "Jaźń Monitor — tylko odczyt")
        self.resize(870, 490)
        self.daemon_port = daemon_port
        self.ollama_port = ollama_port
        self._worker: ProbeThread | None = None
        self._closing = False
        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
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
        if integrated:
            # The JSS monitor is bound to its verified installation root.
            self.root_field.setReadOnly(True)
            browse.hide()
        row.addWidget(browse)
        self.refresh_button = QPushButton("Odśwież")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        self.tray_button = QPushButton("Do tray")
        self.tray_button.setToolTip("Minimalizuj do obszaru powiadomień")
        self.tray_button.clicked.connect(self.showMinimized)
        if integrated:
            # JSS owns its application lifecycle; only standalone uses tray.
            self.tray_button.hide()
        row.addWidget(self.tray_button)
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
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.table, "Usługi")

        self.process_table = QTableWidget(0, 7, self)
        self.process_table.setHorizontalHeaderLabels(
            ["Rola", "PID", "Rodzic PID", "CPU (s)", "RAM (MB)", "Czas (s)", "Dowód"])
        self._configure_data_table(self.process_table)
        self.tabs.addTab(self.process_table, "Procesy Jaźni")

        self.job_table = QTableWidget(0, 5, self)
        self.job_table.setHorizontalHeaderLabels(
            ["Żądanie", "Stan", "Czas (s)", "Kod błędu", "Powód odrzucenia"])
        self._configure_data_table(self.job_table)
        self.tabs.addTab(self.job_table, "Zadania")

        final_page = QWidget(self)
        final_layout = QVBoxLayout(final_page)
        self.final_label = QLabel(
            "Finalizacja ostatniej tury: NIEZWERYFIKOWANA. Gotowość /ready jej nie potwierdza.")
        self.final_label.setWordWrap(True)
        final_layout.addWidget(self.final_label)
        self.generation_label = QLabel("Ostatnia generacja Ollama: NIEZWERYFIKOWANA")
        self.generation_label.setWordWrap(True)
        final_layout.addWidget(self.generation_label)
        self.job_counts = QLabel("Statystyki: brak danych")
        self.job_counts.setWordWrap(True)
        final_layout.addWidget(self.job_counts)
        final_layout.addStretch()
        self.tabs.addTab(final_page, "Finalizacja")
        layout.addWidget(self.tabs)

        self.footer = QLabel(
            "Tylko obserwacja. Zamknięcie monitora nie zatrzyma daemona. "
            "/live ≠ /ready ≠ zaakceptowana odpowiedź.")
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)
        self.timer = QTimer(self)
        self.timer.setInterval((interval_seconds or 5) * 1000)
        self.timer.timeout.connect(self.refresh)
        if not integrated:
            self._configure_tray()
            if not smoke:
                self.timer.start()
                QTimer.singleShot(0, self.refresh)

    @staticmethod
    def _configure_data_table(table: QTableWidget) -> None:
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)

    @staticmethod
    def _show_rows(table: QTableWidget, values: list[list[str]]) -> None:
        table.setRowCount(len(values))
        for row_index, fields in enumerate(values):
            for column, value in enumerate(fields):
                table.setItem(row_index, column, QTableWidgetItem(value))

    def _configure_tray(self) -> None:
        icon = _monitor_icon()
        self.setWindowIcon(icon)
        if not _system_tray_available():
            self.tray_button.setEnabled(False)
            self.tray_button.setToolTip("Brak systemowego obszaru powiadomień")
            return
        tray = QSystemTrayIcon(icon, self)
        menu = QMenu(self)
        menu.addAction("Pokaż Jaźń Monitor").triggered.connect(self.restore_from_tray)
        menu.addSeparator()
        menu.addAction("Zakończ monitor").triggered.connect(self.close)
        tray.setContextMenu(menu)
        tray.setToolTip("Jaźń Monitor — daemon: NIEZWERYFIKOWANY")
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray_menu = menu
        self._tray_icon = tray
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setQuitOnLastWindowClosed(False)

    def _can_minimize_to_tray(self) -> bool:
        return (self._tray_icon is not None
                and self._tray_icon.isVisible()
                and _system_tray_available())

    def changeEvent(self, event: Any) -> None:
        super().changeEvent(event)
        if (event.type() == QEvent.Type.WindowStateChange
                and self.isMinimized() and not self._closing
                and self._can_minimize_to_tray()):
            QTimer.singleShot(0, self._hide_minimized_window)

    def _hide_minimized_window(self) -> None:
        if self.isMinimized() and not self._closing and self._can_minimize_to_tray():
            self.hide()

    def restore_from_tray(self) -> None:
        if not self._closing:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_from_tray()

    def choose_root(self) -> None:
        if self.integrated:
            return  # never retarget the JSS monitor to another installation
        path = QFileDialog.getExistingDirectory(self, "Wybierz SYSTEM ROOT",
                                                 self.root_field.text())
        if path:
            self.root_field.setText(path)
            self.refresh()

    def refresh(self) -> None:
        if self._closing or (self._worker is not None and self._worker.isRunning()):
            return
        raw = self.root_field.text().strip()
        selected = self._fixed_root if self.integrated else (Path(raw) if raw else None)
        self._worker = ProbeThread(selected,
                                   self.daemon_port, self.ollama_port)
        worker = self._worker
        worker.observed.connect(self.apply_snapshot)
        worker.finished.connect(lambda: self._worker_finished(worker))
        worker.start()

    def _worker_finished(self, worker: ProbeThread) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

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
        process_data = report.get("processes") or {}
        process_rows = []
        for item in process_data.get("items") or []:
            if not isinstance(item, dict):
                continue
            def display(value: Any) -> str:
                return "—" if value is None else str(value)
            process_rows.append([
                str(item.get("name") or "?"), display(item.get("pid")),
                display(item.get("parent_pid")), display(item.get("cpu_seconds")),
                display(item.get("ram_mb")), display(item.get("uptime_seconds")),
                str(item.get("evidence") or "niezweryfikowano"),
            ])
        self._show_rows(self.process_table, process_rows)
        self.tabs.setTabText(
            1, "Procesy Jaźni (" + str(len(process_rows)) + ")")

        jobs = report.get("jobs") or {}
        job_rows = []
        for item in jobs.get("items") or []:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("request_id") or "")
            job_rows.append([
                rid[:8] + "…" if len(rid) > 8 else rid,
                str(item.get("state") or "unknown"),
                str(item.get("duration_seconds") if item.get("duration_seconds") is not None else "—"),
                str(item.get("error_code") or "—"),
                str(item.get("reason_code") or "—"),
            ])
        self._show_rows(self.job_table, job_rows)
        self.tabs.setTabText(2, "Zadania (" + str(len(job_rows)) + ")")

        final = report.get("finalization") or {}
        final_state = str(final.get("state") or "unknown")
        self.final_label.setText(
            "OSTATNI WYNIK ZADANIA: " + final_state +
            "\nŻądanie: " + str(final.get("request_id") or "niezweryfikowano") +
            "\nKod błędu: " + str(final.get("error_code") or "—") +
            "\nPowód: " + str(final.get("reason_code") or "—") +
            "\nWynik zadania nie zastępuje dowodu accepted finalization.")
        generation = report.get("ollama_generation") or {}
        self.generation_label.setText(
            "Ostatnia generacja Ollama (SourceOriginLedger): " + str(generation.get("state") or "unknown") +
            "\nModel: " + str(generation.get("model") or "niezapisany") +
            "\nUTC: " + str(generation.get("created_at_utc") or "niezweryfikowano") +
            "\nHistoryczny kandydat nie potwierdza bieżącej gotowości ani finalizacji.")
        counts = jobs.get("counts") if isinstance(jobs.get("counts"), dict) else None
        self.job_counts.setText(
            ("Zadania: przyjęte do kolejki " + str(counts.get("submitted_total")) +
             " | ukończone " + str(counts.get("completed_total")) +
             " | błędy " + str(counts.get("failed_non_timeout_total")) +
             " | timeouty " + str(counts.get("execution_timeout_total")) +
             " | oczekujące " + str(counts.get("pending")))
            if counts else "Statystyki: brak zweryfikowanych liczników")
        self.footer.setText(
            "Odczyt UTC: " + str(report.get("observed_at_utc") or "UNKNOWN") +
            " • tylko obserwacja • zamknięcie nie zatrzymuje daemona")
        if self._tray_icon is not None:
            daemon_state = str((services.get("Daemon Jaźni") or {}).get("state") or "unknown")
            self._tray_icon.setToolTip(
                "Jaźń Monitor — daemon: " + LABELS.get(daemon_state, LABELS["unknown"]))
        self.snapshot_observed.emit(report)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        if self.integrated and not self._smoke and not self._closing:
            self.timer.start()
            self.refresh()

    def hideEvent(self, event: Any) -> None:
        if self.integrated:
            self.timer.stop()
        super().hideEvent(event)

    def shutdown(self) -> None:
        """Drain observer-only workers and release singleton when JSS closes."""
        self._closing = True
        self.timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(6000)
        if self._monitor_lock is not None:
            self._monitor_lock.unlock()
            self._monitor_lock = None

    def closeEvent(self, event: Any) -> None:
        if self.integrated:
            # Closing only hides this view; it must never quit its parent JSS.
            self.timer.stop()
            event.accept()
            return
        self.shutdown()
        if self._tray_icon is not None:
            self._tray_icon.hide()
            app = QApplication.instance()
            if app is not None:
                # X and "Zakończ monitor" exit only this observer process.
                QTimer.singleShot(0, app.quit)
        event.accept()
