"""Simple line icons for the JSS activity rail, drawn natively with Qt."""
from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def activity_icon(kind: str, color: str) -> QIcon:
    canvas = QPixmap(44, 44)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(2.2, 2.2)
    p.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "dashboard":
        p.drawRoundedRect(QRectF(3, 3, 14, 14), 2, 2)
        p.drawLine(10, 3, 10, 17)
        p.drawLine(3, 10, 17, 10)
    elif kind == "chat":
        path = QPainterPath()
        path.moveTo(4, 4); path.lineTo(16, 4); path.lineTo(17, 5); path.lineTo(17, 14)
        path.lineTo(8, 14); path.lineTo(4, 17); path.lineTo(4, 14); path.lineTo(3, 13)
        path.lineTo(3, 5); path.closeSubpath()
        p.drawPath(path)
        p.drawLine(6, 9, 14, 9)
    elif kind == "services":
        for y in (3, 9, 15):
            p.drawRoundedRect(QRectF(3, y, 14, 3.5), 1, 1)
            p.drawEllipse(QRectF(5, y + 1, 1.2, 1.2))
    elif kind == "memory":
        p.drawEllipse(QRectF(3, 3, 14, 5))
        p.drawLine(3, 5.5, 3, 15); p.drawLine(17, 5.5, 17, 15)
        p.drawArc(QRectF(3, 12.5, 14, 5), 180 * 16, 180 * 16)
    elif kind == "tests":
        p.drawRoundedRect(QRectF(4, 2.5, 12, 15), 2, 2)
        p.drawLine(6, 10, 8.5, 12.3); p.drawLine(8.5, 12.3, 14, 6.5)
    elif kind == "studios":
        for x in (3, 11):
            for y in (3, 11):
                p.drawRect(QRectF(x, y, 6, 6))
    elif kind == "developer":
        p.drawLine(8, 5, 3, 10); p.drawLine(3, 10, 8, 15)
        p.drawLine(12, 5, 17, 10); p.drawLine(17, 10, 12, 15)
        p.drawLine(11.5, 3.5, 8.5, 16.5)
    elif kind == "settings":
        p.drawEllipse(QRectF(5, 5, 10, 10))
        p.drawEllipse(QRectF(8, 8, 4, 4))
        for x1, y1, x2, y2 in ((10, 1, 10, 4), (10, 16, 10, 19), (1, 10, 4, 10), (16, 10, 19, 10),
                               (4, 4, 6, 6), (14, 14, 16, 16), (4, 16, 6, 14), (14, 6, 16, 4)):
            p.drawLine(x1, y1, x2, y2)
    p.end()
    return QIcon(canvas)
