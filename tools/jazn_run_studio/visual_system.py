"""Scoped Qt palette, density and table behavior for every Heart System page."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QBoxLayout, QFormLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QTableWidget,
    QTreeWidget, QWidget,
)

from .workbench_theme import METRICS, workbench_colors, workbench_stylesheet, workbench_metrics


class VisualSystem(QObject):
    """Observe new widgets too; never change another application's defaults."""
    def __init__(self, root: QWidget):
        super().__init__(root)
        self.root = root
        self.metrics = METRICS
        self.reflow_pending = False
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (event.type() in (QEvent.Type.Resize, QEvent.Type.Show)
                and isinstance(watched, QWidget) and (watched is self.root or self.root.isAncestorOf(watched))
                and not self.reflow_pending):
            self.reflow_pending = True
            QTimer.singleShot(0, self.reflow)
        if (event.type() == QEvent.Type.Polish and isinstance(watched, QWidget)
                and (watched is self.root or self.root.isAncestorOf(watched))):
            self.polish(watched)
        return False

    def reflow(self) -> None:
        self.reflow_pending = False
        for form in self.root.findChildren(QFormLayout):
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setSpacing(self.metrics.gap)
        for button in self.root.findChildren(QPushButton):
            original = button.property("heartOriginalText")
            if not isinstance(original, str) or button.text() != button.property("heartRenderedText"):
                original = button.text()
                button.setProperty("heartOriginalText", original)
            available = self.available_width(button) - 40
            lines: list[str] = []
            line = ""
            for word in original.split():
                candidate = (line + " " + word).strip()
                if line and button.fontMetrics().horizontalAdvance(candidate) > max(180, available):
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            text = "\n".join(lines)
            if text != button.text():
                button.setText(text)
                if not button.toolTip() or button.property("heartGeneratedTooltip"):
                    button.setToolTip(original)
                    button.setProperty("heartGeneratedTooltip", True)
                if not button.accessibleName():
                    button.setAccessibleName(original)
            button.setProperty("heartRenderedText", text)
        for layout in self.root.findChildren(QHBoxLayout):
            parent = layout.parentWidget()
            if parent is None:
                continue
            available = self.available_width(parent)
            widths = []
            for index in range(layout.count()):
                item = layout.itemAt(index)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None and not widget.isHidden():
                    widths.append(max(widget.minimumWidth(), widget.minimumSizeHint().width()))
                else:
                    nested = item.layout()
                    if nested is not None:
                        widths.append(nested.minimumSize().width())
            needed = sum(widths) + max(0, len(widths) - 1) * layout.spacing()
            direction = QBoxLayout.Direction.TopToBottom if needed > available else QBoxLayout.Direction.LeftToRight
            if layout.direction() != direction:
                layout.setDirection(direction)

    @staticmethod
    def available_width(widget: QWidget) -> int:
        parent = widget.parentWidget()
        available = parent.width() - 32 if parent is not None else widget.width() - 32
        ancestor = parent
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                available = min(available, ancestor.viewport().width() - 32)
                break
            ancestor = ancestor.parentWidget()
        return available

    def polish(self, widget: QWidget) -> None:
        if widget.property("heartVisualConfigured"):
            return
        widget.setProperty("heartVisualConfigured", True)
        if isinstance(widget, QLabel):
            widget.setWordWrap(True)
        if isinstance(widget, (QTableWidget, QTreeWidget)):
            widget.setAlternatingRowColors(True)
            widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            widget.setTextElideMode(Qt.TextElideMode.ElideRight)
            widget.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            header = widget.horizontalHeader() if isinstance(widget, QTableWidget) else widget.header()
            header.setMinimumSectionSize(36)
            header.setSectionsMovable(True)
            if isinstance(widget, QTableWidget):
                widget.verticalHeader().setMinimumSectionSize(self.metrics.row_height)
                widget.verticalHeader().setDefaultSectionSize(max(self.metrics.row_height, widget.verticalHeader().defaultSectionSize()))
                if widget is getattr(self.root, "services_table", None):
                    widget.verticalHeader().setDefaultSectionSize(48)
                widget.setMouseTracking(True)
                widget.cellEntered.connect(lambda row, column, table=widget: self.tooltip(table, row, column))
        layout = widget.layout()
        if isinstance(layout, QFormLayout):
            layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.setSpacing(self.metrics.gap)

    @staticmethod
    def tooltip(table: QTableWidget, row: int, column: int) -> None:
        item = table.item(row, column)
        if item is not None and not item.toolTip():
            item.setToolTip(item.text())

    def apply(self, theme: str, accent: str, *, system_dark: bool) -> None:
        colors = workbench_colors(theme, accent, system_dark=system_dark)
        self.metrics = workbench_metrics(theme)
        palette = QPalette(self.root.palette())
        roles = {QPalette.ColorRole.Window: colors.background,
                 QPalette.ColorRole.Base: colors.editor,
                 QPalette.ColorRole.AlternateBase: colors.surface,
                 QPalette.ColorRole.WindowText: colors.text,
                 QPalette.ColorRole.Text: colors.text,
                 QPalette.ColorRole.Button: colors.surface,
                 QPalette.ColorRole.ButtonText: colors.text,
                 QPalette.ColorRole.ToolTipBase: colors.surface,
                 QPalette.ColorRole.ToolTipText: colors.text,
                 QPalette.ColorRole.Highlight: colors.accent,
                 QPalette.ColorRole.HighlightedText: colors.selected_text,
                 QPalette.ColorRole.PlaceholderText: colors.muted,
                 QPalette.ColorRole.Link: colors.accent}
        for role, color in roles.items():
            palette.setColor(role, QColor(color))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors.muted))
        self.root.setPalette(palette)
        font = QFont(self.root.font())
        font.setPointSize(self.metrics.body_points)
        self.root.setFont(font)
        self.root.setStyleSheet(workbench_stylesheet(theme, accent, system_dark=system_dark))
        for widget in self.root.findChildren(QWidget):
            self.polish(widget)
        self.reflow()
