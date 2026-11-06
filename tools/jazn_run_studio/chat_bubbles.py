"""Presentation-only chat bubbles; never owns transport or finalization.

The transcript exposes the small legacy read-only text API used by GUI tests.
Actual replies can be inserted only by the host's accepted chat_final handler.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

WARSAW = ZoneInfo("Europe/Warsaw")


def visible_time(value: datetime | str | None) -> str:
    """Never invent a historical send time from an acceptance timestamp."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return "czas nieznany"
    if not isinstance(value, datetime) or value.tzinfo is None:
        return "czas nieznany"
    return value.astimezone(WARSAW).strftime("%d.%m.%Y, %H:%M")


class ChatTranscript(QScrollArea):
    """Selectable, accessible native Qt message bubbles and stable timestamps."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setObjectName("workbenchChatTranscript")
        self.setAccessibleName("Historia lokalnej rozmowy")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._records: list[str] = []
        self.bubbles: list[QFrame] = []
        self.container = QWidget(self)
        self.container.setObjectName("jssChatMessageCanvas")
        self.messages = QVBoxLayout(self.container)
        self.messages.setContentsMargins(12, 12, 12, 12)
        self.messages.setSpacing(12)
        self.placeholder = QLabel("Tutaj pojawią się wiadomości i zaakceptowane odpowiedzi Jaźni.")
        self.placeholder.setObjectName("jssChatPlaceholder")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.messages.addWidget(self.placeholder)
        self.messages.addStretch(1)
        self.setWidget(self.container)

    def isReadOnly(self) -> bool:
        return True

    def setPlaceholderText(self, text: str) -> None:
        self.placeholder.setText(text)

    def toPlainText(self) -> str:
        return "\n".join(self._records)

    def clear(self) -> None:
        for bubble in self.bubbles:
            self.messages.removeWidget(bubble)
            bubble.deleteLater()
        self.bubbles.clear()
        self._records.clear()
        self.placeholder.show()

    def appendPlainText(self, text: str) -> None:
        """Compatibility for synthetic/legacy append; not a finalization gate."""
        self.append_message("assistant", text, timestamp=None)

    def append_message(self, role: str, text: str, *,
                       timestamp: datetime | str | None = None,
                       timestamp_kind: str = "odebrano") -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("unknown chat message role")
        content = str(text)
        self._records.append(("Ty:\n" + content + "\n") if role == "user" else content + "\n")
        self.placeholder.hide()
        row = QFrame(self.container)
        row.setObjectName("jssUserBubbleRow" if role == "user" else "jssAssistantBubbleRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        bubble = QFrame(row)
        bubble.setObjectName("jssUserBubble" if role == "user" else "jssAssistantBubble")
        bubble.setMaximumWidth(740)
        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(14, 9, 14, 11)
        inner.setSpacing(5)
        who = "Ty" if role == "user" else "Łatka"
        header = QLabel(f"{who}  •  {visible_time(timestamp)}")
        header.setObjectName("jssBubbleHeader")
        header.setAccessibleName(
            who + ", " + timestamp_kind + ": " + visible_time(timestamp))
        inner.addWidget(header)
        content_widget = QLabel(content)
        content_widget.setObjectName("jssBubbleContent")
        content_widget.setWordWrap(True)
        content_widget.setTextFormat(Qt.TextFormat.PlainText)
        content_widget.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        content_widget.setAccessibleName("Wiadomość " + who)
        inner.addWidget(content_widget)
        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble, 0)
        else:
            row_layout.addWidget(bubble, 0)
            row_layout.addStretch(1)
        # Insert above the bottom stretch to preserve chronological ordering.
        self.messages.insertWidget(self.messages.count() - 1, row)
        self.bubbles.append(row)
        QTimer.singleShot(0, self._scroll_bottom)

    def _scroll_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
