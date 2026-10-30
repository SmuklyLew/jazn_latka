"""Explicit interactive PTY panel; basic ANSI display, full VT fidelity remains P2."""
from __future__ import annotations
import re
import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget
from .terminal_session import PtySession

_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|.)")

class TerminalScreen(QPlainTextEdit):
    def __init__(self, session: InteractiveTerminal):
        super().__init__()
        self.session = session
        self.setReadOnly(True)
        self.setMaximumBlockCount(2500)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mono = QFont("Consolas" if sys.platform == "win32" else "Monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(mono)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.session.resize_terminal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.session.pty.process is None:
            return super().keyPressEvent(event)
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if ctrl and key == Qt.Key.Key_C and self.textCursor().hasSelection():
            return super().keyPressEvent(event)
        if ctrl and key == Qt.Key.Key_V:
            self.session.send(QApplication.clipboard().text()[:8192])
            return
        specials: dict[int, str] = {int(Qt.Key.Key_Enter): "\r", int(Qt.Key.Key_Return): "\r",
                    int(Qt.Key.Key_Backspace): "\x7f", int(Qt.Key.Key_Up): "\x1b[A",
                    int(Qt.Key.Key_Down): "\x1b[B", int(Qt.Key.Key_Left): "\x1b[D",
                    int(Qt.Key.Key_Right): "\x1b[C", int(Qt.Key.Key_Tab): "\t"}
        if ctrl and key in (Qt.Key.Key_C, Qt.Key.Key_D):
            self.session.send("\x03" if key == Qt.Key.Key_C else "\x04")
        elif key in specials:
            self.session.send(specials[key])
        elif event.text():
            self.session.send(event.text())

class InteractiveTerminal(QWidget):
    def __init__(self, host):
        super().__init__()
        self.pty = PtySession(host.core.root)
        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        self.launch = QPushButton("Nowa lokalna sesja PTY")
        self.launch.clicked.connect(self.start)
        self.stop_button = QPushButton("Zamknij własną sesję")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        self.status = QLabel("Nie uruchomiono. Nie zarządza daemonem Jaźni.")
        for widget in (self.launch, self.stop_button, self.status):
            actions.addWidget(widget)
        layout.addLayout(actions)
        self.terminal_output = TerminalScreen(self)
        self.terminal_output.setAccessibleName("Interaktywne wyjście lokalnego PTY")
        layout.addWidget(self.terminal_output)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.drain)
        self.clock.start(80)
        self._dimensions: tuple[int, int] | None = None

    def preferred_dimensions(self) -> tuple[int, int]:
        return (
            max(10, min(200, self.terminal_output.height() // 17)),
            max(20, min(400, self.terminal_output.width() // 9)),
        )

    def resize_terminal(self) -> None:
        if self.pty.process is None or self.pty.done:
            return
        dimensions = self.preferred_dimensions()
        if dimensions == self._dimensions:
            return
        try:
            self.pty.resize(*dimensions)
        except (OSError, RuntimeError, ValueError) as exc:
            self.status.setText("Zmiana rozmiaru PTY: " + type(exc).__name__)
        else:
            self._dimensions = dimensions

    def start(self) -> None:
        try:
            self._dimensions = self.preferred_dimensions()
            self.pty.start(rows=self._dimensions[0], cols=self._dimensions[1])
        except (OSError, RuntimeError, ValueError) as exc:
            self.status.setText("Nie uruchomiono: " + str(exc))
            return
        self.launch.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("PTY aktywne — pełny renderer VT/ANSI wymaga dalszych testów")
        self.terminal_output.setFocus()

    def send(self, text: str) -> None:
        try:
            self.pty.write(text)
        except (OSError, RuntimeError, ValueError) as exc:
            self.status.setText("Wejście PTY: " + type(exc).__name__)

    def drain(self) -> None:
        chunks = self.pty.read_available()
        if chunks:
            text = _ANSI.sub("", "".join(chunks)).replace("\r", "\n")
            cursor = self.terminal_output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
            self.terminal_output.setTextCursor(cursor)
            self.terminal_output.ensureCursorVisible()
        if self.pty.error:
            self.status.setText(self.pty.error)

    def stop(self) -> None:
        self.pty.close()
        # A new session is created only on the next explicit operator click.
        self.pty = PtySession(self.pty.root)
        self._dimensions = None
        self.launch.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status.setText("Zamknięto własny terminal; daemon pozostaje nietknięty")

    def closeEvent(self, event) -> None:
        self.stop()
        super().closeEvent(event)
