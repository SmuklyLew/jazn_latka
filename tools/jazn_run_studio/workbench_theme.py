"""Reusable Jaźń Studio workbench palette and Qt widget styling.

No application-wide stylesheet: individual studios can use this helper
without overriding another Qt tool's palette or changing runtime settings.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkbenchColors:
    background: str
    sidebar: str
    editor: str
    surface: str
    hover: str
    border: str
    text: str
    muted: str
    accent: str
    selected_text: str
    success: str = "#82D6A2"
    warning: str = "#F0C17A"
    error: str = "#F1849B"
    cyan: str = "#70CADC"
    lavender: str = "#D4B6F2"


def workbench_colors(theme: str, accent: str, *, system_dark: bool = False) -> WorkbenchColors:
    """Choose readable, restrained colors without inspecting live services."""
    if theme not in {"violet-night", "system", "light", "dark", "purple", "custom"}:
        raise ValueError("Nieznany motyw Studio")
    if len(accent) != 7 or accent[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in accent[1:]):
        raise ValueError("Kolor akcentu wymaga formatu #RRGGBB")
    if theme == "violet-night":
        return WorkbenchColors(
            "#11101C", "#1B172A", "#1B172A", "#242034",
            "#302440", "#8D78A3", "#F0E9FA", "#BDB2CF", "#A783DB", "#11101C"
        )
    chosen_accent = accent if theme == "custom" else "#9876d4"
    dark = theme in {"purple", "dark", "custom"} or (theme == "system" and system_dark)
    if not dark:
        return WorkbenchColors(
            "#f5f4f8", "#eceaf3", "#ffffff", "#f9f8fc",
            "#e8e3ef", "#d2cadd", "#292537", "#665f75", chosen_accent, "#1a1029"
        )
    if theme == "purple":
        return WorkbenchColors(
            "#11101c", "#141221", "#191627", "#211c31",
            "#302845", "#4a3c63", "#eeeaf8", "#b3aacb", chosen_accent, "#150f23"
        )
    return WorkbenchColors(
        "#17161d", "#201e29", "#1d1b26", "#282531",
        "#34303e", "#454051", "#efebf5", "#aba5b7", chosen_accent, "#160f21"
    )


def workbench_stylesheet(theme: str, accent: str, *, system_dark: bool = False) -> str:
    """Shared visual contract for current and future native Qt studios."""
    c = workbench_colors(theme, accent, system_dark=system_dark)
    return f"""
        QWidget {{ background: {c.background}; color: {c.text}; font-size: 13px; }}
        QLabel {{ background: transparent; }}
        QWidget#workbenchSidebar {{ background: {c.sidebar}; border-right: 2px solid {c.border}; }}
        QWidget#workbenchTopbar {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c.editor}, stop:1 {c.sidebar}); border-bottom: 1px solid {c.border}; }}
        QLabel#workbenchBrand {{ color: {c.accent}; font-size: 17px; font-weight: 700; }}
        QLabel#workbenchCaption, QLabel#workbenchStatus, QLabel#workbenchFootnote {{
            color: {c.muted}; font-size: 12px;
        }}
        QLabel#workbenchSection {{ font-size: 17px; font-weight: 600; }}
        QLabel#heading {{ font-size: 25px; font-weight: 600; padding-bottom: 6px; }}
        QScrollArea {{ background: {c.editor}; border: 0; }}
        QScrollArea > QWidget > QWidget {{ background: {c.editor}; }}
        QListWidget#workbenchNavigation {{
            background: {c.sidebar}; border: 0; padding: 8px 4px;
        }}
        QListWidget#workbenchNavigation::item {{
            border-radius: 5px; margin: 2px 4px; padding: 11px 10px;
        }}
        QListWidget#workbenchNavigation::item:hover {{ background: {c.hover}; }}
        QListWidget#workbenchNavigation::item:selected {{
            background: {c.accent}; color: {c.selected_text};
        }}
        QPushButton {{
            background: {c.surface}; border: 1px solid {c.border};
            border-radius: 6px; min-height: 26px; padding: 5px 11px;
        }}
        QPushButton:hover {{ background: {c.hover}; border-color: {c.accent}; }}
        QPushButton:focus, QListWidget:focus, QTabBar::tab:focus {{
            border: 2px solid {c.accent}; outline: 0;
        }}
        QPushButton:disabled {{ color: {c.muted}; }}
        QPlainTextEdit, QLineEdit, QComboBox, QTextEdit, QTableView {{
            background: {c.surface}; border: 1px solid {c.border};
            border-radius: 3px; padding: 5px; selection-background-color: {c.accent};
            selection-color: {c.selected_text};
        }}
        QPlainTextEdit {{ font-family: Consolas, 'DejaVu Sans Mono', monospace; }}
        QSplitter::handle {{ background: {c.border}; border: 1px solid {c.hover}; }}
        QSplitter::handle:hover {{ background: {c.accent}; }}
        QTabWidget::pane {{ border: 1px solid {c.border}; background: {c.editor}; }}
        QTabBar::tab {{
            background: {c.sidebar}; border: 1px solid {c.border};
            border-bottom: 0; padding: 7px 14px; margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background: {c.editor}; border-top: 2px solid {c.accent};
            padding-top: 6px;
        }}
        QTabBar::tab:hover {{ background: {c.hover}; }}
        QTableWidget {{
            background: {c.editor}; alternate-background-color: {c.surface};
            gridline-color: {c.border};
        }}
        QHeaderView::section {{
            background: {c.sidebar}; border: 0;
            border-bottom: 1px solid {c.border}; padding: 6px;
        }}
        QStatusBar {{
            background: {c.sidebar}; border-top: 1px solid {c.border};
            color: {c.muted};
        }}
        QToolTip {{
            background: {c.surface}; color: {c.text}; border: 1px solid {c.accent};
        }}
    """
