"""Qt presentation of separate read-only MEMORY observations."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .core import Controller

_SAFE_REASON = re.compile(r"[a-z][a-z0-9_:-]{0,79}\\Z", re.ASCII)


def safe_reason(value: object, fallback: str = "observation_failed") -> str:
    """Expose only short diagnostic codes; raw exception text can contain private paths."""
    return value if isinstance(value, str) and _SAFE_REASON.fullmatch(value) else fallback


def evidence_rows(operation: str, result: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Names describe exactly what is checked; equality never certifies lineage."""
    rows: list[tuple[str, str, str]] = []
    if operation == "layout":
        roles = result.get("roles", {})
        source = roles.get("source", {})
        rows.append(("Źródła: obecność plików", "verified" if source.get("inventory_present") else "unverified",
                     f"obecne={source.get('present', 0)}, brak={source.get('missing', 0)}, niebezpieczne={source.get('unsafe', 0)}"))
        for role, label in (("target", "Target odbudowy"), ("staging", "Staging"),
                            ("host_selected_memory", "MEMORY wybrana przez hosta")):
            value = roles.get(role, {})
            database = value.get("database", value)
            state = "verified" if database.get("schema_compatible") is True else "unverified"
            if value.get("status") in {"unsafe_path", "ambiguous", "invalid", "bounded_scan_required"}:
                state = "blocked"
            rows.append((label + ": schemat", state, safe_reason(value.get("status"), "unverified")))
        rows.append(("Pamięć rzeczywiście zweryfikowana w runtime", "unverified", "wymaga osobnej obserwacji runtime"))
        for issue in result.get("readiness", {}).get("blockers", []):
            rows.append(("Blokada inspekcji", "blocked", safe_reason(issue, "inspection_blocked")))
    elif operation == "comparison":
        for name, comparison in result.get("comparisons", {}).items():
            equal = comparison.get("fingerprint_equal")
            state = "verified" if equal is True else "different" if equal is False else "unverified"
            if comparison.get("state") == "incompatible":
                state = "incompatible"
            rows.append((name + ": zgodność zawartości", state, safe_reason(comparison.get("issue", comparison.get("state")), "comparison_blocked")))
            lineage = comparison.get("lineage", {})
            rows.append((name + ": deklarowana lineage", str(lineage.get("verification_state", "unverified")),
                         safe_reason(lineage.get("state"), "unverified")))
            uuid_equal = lineage.get("database_uuid_equal")
            rows.append((name + ": zgodność deklarowanych UUID", "verified" if uuid_equal is True else
                         "different" if uuid_equal is False else "unverified", "zgodność UUID nie certyfikuje genealogii"))
            for field, matching in lineage.get("claim_matches", {}).items():
                rows.append((name + ": deklaracja " + field, "unverified" if matching else "different",
                             "deklaracje zgodne" if matching else "deklaracje różne"))
            for delta in comparison.get("table_diffs", []):
                rows.append((name + ": tabela " + str(delta["table"]), "different",
                    f"dodane={delta['added']}, usunięte={delta['removed']}, zmienione={delta['changed']}"))
        source = result.get("source_provenance", {})
        rows.append(("Bajty źródeł a deklaracje", str(source.get("verification_state", "unverified")), str(source.get("state", "unverified"))))
        rows.append(("Niezależnie zweryfikowana proweniencja", "unverified", "zgodne rekordy i UUID nie dowodzą genealogii"))
        rows.append(("Atomowy snapshot wszystkich baz", "unverified", "obserwacje baz są sekwencyjne"))
        if result.get("issue"):
            rows.append(("Blokada porównania", "blocked", safe_reason(result["issue"], "comparison_blocked")))
    else:
        labels = {"runtime_root": "Root runtime", "version_integrity": "Wersja i integralność",
            "process": "PID i komenda procesu", "endpoint": "Uwierzytelniony endpoint i instancja",
            "heartbeat": "Świeżość heartbeat", "memory_root": "MEMORY runtime a wybór hosta",
            "memory_schema": "Schemat aktywnej MEMORY", "database_identity": "Tożsamość bazy MEMORY",
            "provenance": "Niezależna proweniencja", "recall": "Rzeczywisty recall", "continuity": "Ciągłość pamięci"}
        for key, label in labels.items():
            state = str(result.get("checks", {}).get(key, {}).get("state", "unverified"))
            if key in {"recall", "continuity"}:
                state = "verified" if (result.get("memory_" + key + "_ready") is True
                    and result.get("independent_" + key + "_verified") is True) else "unverified"
            rows.append((label, state, safe_reason(result.get("checks", {}).get(key, {}).get("issue"), "")))
        for key, label in (("runtime_ready", "Gotowość bieżącego runtime"),
                           ("activation_preflight_passed", "Pozytywny preflight aktywacji"),
                           ("activation_authorized", "Autoryzacja aktywacji")):
            rows.append((label, "verified" if result.get(key) is True else "unverified", ""))
    return rows


class MemoryPanel(QWidget):
    def __init__(self, core: Controller, guard: Any):
        super().__init__()
        self.core, self.guard = core, guard
        self.pending: dict[str, float] = {}
        layout = QVBoxLayout(self)
        notice = QLabel("Inspekcja jest odczytowa. Zgodność danych, identity, proweniencja, runtime, recall i aktywacja mają osobne dowody. Każda zakładka jest osobną obserwacją.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        form = QFormLayout()
        self.project = QLineEdit()
        self.project.setAccessibleName("Plik projektu pamięci")
        picker = QHBoxLayout()
        picker.addWidget(self.project)
        choose = QPushButton("Wybierz projekt")
        choose.clicked.connect(self.choose_project)
        picker.addWidget(choose)
        form.addRow("Projekt", picker)
        layout.addLayout(form)
        pin_toggle = QPushButton("Referencje (opcjonalne)")
        self.pin_toggle = pin_toggle
        pin_toggle.setCheckable(True)
        layout.addWidget(pin_toggle)
        pin_box = QWidget()
        pin_form = QFormLayout(pin_box)
        pin_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        pin_note = QLabel("Wyłącznie zamrożone artefakty i SHA-256 przypięte niezależnie przez operatora. Zgodność nie upoważnia do aktywacji.")
        pin_note.setWordWrap(True)
        pin_form.addRow(pin_note)
        self.pin_fields: dict[str, QLineEdit] = {}
        for key, label in (("reference", "Artefakt referencyjny"),
                           ("reference_sha256", "SHA-256 referencji"),
                           ("parent", "Artefakt rodzica"), ("parent_sha256", "SHA-256 rodzica")):
            entry = QLineEdit()
            entry.setAccessibleName(label)
            pin_form.addRow(label, entry)
            self.pin_fields[key] = entry
        layout.addWidget(pin_box)
        pin_box.hide()
        pin_toggle.toggled.connect(pin_box.setVisible)
        row = QVBoxLayout()
        for operation, label in (("layout", "Inspekcja ról i schematu"),
                                 ("comparison", "Porównaj dane i deklaracje"),
                                 ("readiness", "Sprawdź dowody runtime")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, op=operation: self.guard(lambda: self.start(op)))
            row.addWidget(button)
        layout.addLayout(row)
        self.tabs = QTabWidget()
        self.tables: dict[str, QTableWidget] = {}
        self.timestamps: dict[str, QLabel] = {}
        for operation, label in (("layout", "Role baz"),
                                 ("comparison", "Porównanie"), ("readiness", "Runtime")):
            page = QWidget()
            inner = QVBoxLayout(page)
            timestamp = QLabel("Jeszcze nie wykonano obserwacji")
            timestamp.setWordWrap(True)
            inner.addWidget(timestamp)
            table = QTableWidget(0, 3)
            table.setHorizontalHeaderLabels(["Właściwość", "Stan", "Dowód / blokada"])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setAccessibleName(label)
            table.setMinimumHeight(260)
            inner.addWidget(table)
            self.tables[operation], self.timestamps[operation] = table, timestamp
            self.tabs.addTab(page, label)
        layout.addWidget(self.tabs)
        self.project.textChanged.connect(self.invalidate)
        for entry in self.pin_fields.values():
            entry.textChanged.connect(self.invalidate)

    def invalidate(self, _text: str = "") -> None:
        self.pending.clear()
        for operation, table in self.tables.items():
            table.setRowCount(0)
            self.timestamps[operation].setText("Wybór zmieniony; wykonaj nową obserwację")

    def choose_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Projekt pamięci", "", "Projekt (*.memory-rebuild.json);;JSON (*.json)")
        if path:
            self.project.setText(path)

    def start(self, operation: str) -> None:
        if operation == "comparison" and QMessageBox.question(self, "Odczyt prywatnych danych",
                "Porównanie odczyta bazy i bajty źródeł oraz utworzy tymczasowe snapshoty poza MEMORY. Wynik zawiera wyłącznie agregaty. Wykonać?") != QMessageBox.StandardButton.Yes:
            return
        pins = {key: value.text().strip() for key, value in self.pin_fields.items()} if operation == "readiness" else {}
        job = self.core.inspect_memory(operation, project=self.project.text().strip() if operation != "readiness" else "", **pins)
        self.pending[operation] = job.started
        self.tables[operation].setRowCount(0)
        self.timestamps[operation].setText("Obserwacja w toku; brak nowego wyniku")

    def receive(self, key: str, value: dict[str, Any]) -> None:
        operation = key.removeprefix("memory:p1:")
        if operation not in self.tables or self.pending.get(operation) != value.get("started"):
            return  # Discard a delayed result after selection changed.
        report = value["report"]
        self.pending.pop(operation, None)
        rows = (evidence_rows(operation, report.get("result", {})) if report.get("ok") is True else
                [(operation, "blocked", safe_reason(report.get("issue")))])
        table = self.tables[operation]
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, text in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(text))
        table.resizeColumnsToContents()
        self.timestamps[operation].setText("Osobna obserwacja ukończona: " + datetime.now().astimezone().isoformat(timespec="seconds"))

    def receive_state(self, key: str, value: dict[str, Any]) -> None:
        operation = key.removeprefix("memory:p1:")
        if (operation not in self.tables or self.pending.get(operation) != value.get("started")
                or value.get("state") not in {"failed", "stopped"}):
            return
        self.pending.pop(operation, None)
        table = self.tables[operation]
        table.setRowCount(1)
        for column, text in enumerate(("Obserwacja", "blocked", safe_reason(value.get("error"), str(value["state"])))):
            table.setItem(0, column, QTableWidgetItem(text))
        self.timestamps[operation].setText("Obserwacja nieukończona; brak pozytywnego dowodu")
