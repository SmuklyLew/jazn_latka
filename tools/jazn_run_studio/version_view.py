"""Read-only native entry for Version Rebuild; no package mutation."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget

from .core import Controller


class VersionPanel(QWidget):
    """Independent view; write/backup parity remains in legacy Version Studio."""

    def __init__(self, core: Controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.core = core
        self.state = QLabel("Wersja wymaga odczytu ze zweryfikowanego kodu SYSTEM.")
        self.state.setWordWrap(True)
        self.inspect_button = QPushButton("Sprawdź wersję kanoniczną (odczyt)")
        self.inspect_button.clicked.connect(self.inspect)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setAccessibleName("Zweryfikowany odczyt wersji pakietu")
        layout = QVBoxLayout(self)
        layout.addWidget(self.state)
        layout.addWidget(self.inspect_button)
        layout.addWidget(self.output)
        layout.addStretch(1)

    def inspect(self) -> None:
        self.inspect_button.setEnabled(False)
        try:
            self.core.studio_helper("version-inspect")
        except (OSError, ValueError) as exc:
            self.state.setText("BŁĄD: " + type(exc).__name__)
            self.inspect_button.setEnabled(True)
            return
        self.state.setText("Trwa odczyt z rzeczywistego SYSTEM…")

    def receive(self, value: object) -> None:
        self.inspect_button.setEnabled(True)
        if not isinstance(value, dict) or value.get("schema") != "jazn_version_readonly_inspection/v1" or value.get("read_only") is not True:
            self.state.setText("BŁĄD: niezgodna odpowiedź weryfikacyjna.")
            return
        self.output.setPlainText(
            "PACKAGE_VERSION: " + str(value.get("package", "")) +
            "\nRELEASE_NAME: " + str(value.get("name", "")) +
            "\nVERSION_FULL: " + str(value.get("full", ""))
        )
        self.state.setText("Odczytano wersję. Nie zaktualizowano żadnych metadanych.")

    def receive_state(self, value: object) -> None:
        if isinstance(value, dict) and value.get("state") in {"failed", "stopped"}:
            self.inspect_button.setEnabled(True)
            self.state.setText("BŁĄD odczytu wersji: " + str(value.get("error", "unknown")))
