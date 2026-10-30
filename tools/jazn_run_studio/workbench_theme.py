"""Reusable Jaźń Studio workbench palette and Qt widget styling.

No application-wide stylesheet: individual studios can use this helper
without overriding another Qt tool's palette or changing runtime settings.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


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
    focus: str = "#A783DB"


def _base_colors(theme: str, accent: str, *, system_dark: bool = False) -> WorkbenchColors:
    """Choose readable, restrained colors without inspecting live services."""
    if theme not in {key for _, key in THEME_CHOICES}:
        raise ValueError("Nieznany motyw Studio")
    if len(accent) != 7 or accent[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in accent[1:]):
        raise ValueError("Kolor akcentu wymaga formatu #RRGGBB")
    if theme == "technical-workbench":
        return WorkbenchColors(
            "#141A23", "#1B2430", "#202A36", "#263342",
            "#314053", "#8194AA", "#F5F8FC", "#BFCDD9", "#5BA5F5", "#0B1A2B"
        )
    if theme == "operations-studio":
        return WorkbenchColors(
            "#111C21", "#172931", "#1C3038", "#25414B",
            "#30535F", "#8EA7B4", "#F2FAFC", "#BBD0D7", "#5CD4C2", "#071D22"
        )
    if theme == "fluent-studio":
        return WorkbenchColors(
            "#171E2B", "#1F2938", "#253347", "#2D3F55",
            "#38516B", "#8EA7B4", "#F6F9FC", "#C1CFDE", "#86B6FF", "#122034"
        )
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


@dataclass(frozen=True)
class WorkbenchMetrics:
    """Logical dimensions; Qt scales these with the window's device scale."""
    body_points: int = 10
    small_points: int = 9
    heading_points: int = 17
    control_height: int = 24
    gap: int = 6
    page_margin: int = 16
    row_height: int = 30
    radius: int = 4


METRICS = WorkbenchMetrics()


@dataclass(frozen=True)
class ThemeProfile:
    """Pure, serializable appearance definition; no runtime or service access."""
    key: str
    label: str
    description: str
    metrics: WorkbenchMetrics


DEFAULT_WORKBENCH_THEME = "technical-workbench"
WORKBENCH_PROFILES = (
    ThemeProfile("technical-workbench", "Technical Workbench",
                 "Ciemny, zwarty układ dla kodu, testów i diagnostyki.",
                 WorkbenchMetrics(body_points=9, small_points=8, heading_points=16,
                                  control_height=24, gap=5, page_margin=12, row_height=27, radius=3)),
    ThemeProfile("operations-studio", "Operations Studio",
                 "Czytelny panel usług, monitorowania i operacji.",
                 WorkbenchMetrics(body_points=10, small_points=9, heading_points=18,
                                  control_height=30, gap=8, page_margin=18, row_height=36, radius=6)),
    ThemeProfile("fluent-studio", "Fluent Studio",
                 "Spokojniejszy układ z przestrzenią i łagodnymi krawędziami.",
                 WorkbenchMetrics(body_points=10, small_points=9, heading_points=19,
                                  control_height=34, gap=10, page_margin=22, row_height=40, radius=9)),
)
LEGACY_THEMES = ("violet-night", "system", "light", "dark", "purple", "custom")
THEME_CHOICES = tuple((p.label, p.key) for p in WORKBENCH_PROFILES) + tuple(
    (key, key) for key in LEGACY_THEMES
)


def workbench_metrics(theme: str) -> WorkbenchMetrics:
    return next((profile.metrics for profile in WORKBENCH_PROFILES if profile.key == theme), METRICS)


def theme_label(theme: str) -> str:
    return next((label for label, key in THEME_CHOICES if key == theme), theme)



def contrast_ratio(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def workbench_colors(theme: str, accent: str, *, system_dark: bool = False) -> WorkbenchColors:
    c = _base_colors(theme, accent, system_dark=system_dark)
    selected = max(("#111111", "#ffffff"), key=lambda color: contrast_ratio(c.accent, color))
    # Semantic colors must remain readable in both light and dark profiles.
    if contrast_ratio(c.background, "#111111") > contrast_ratio(c.background, "#ffffff"):
        c = replace(c, success="#176B3A", warning="#805000", error="#B4233D", cyan="#086877")
    focus = c.accent if contrast_ratio(c.accent, c.background) >= 3 else c.cyan
    return replace(c, selected_text=selected, focus=focus)


def workbench_stylesheet(theme: str, accent: str, *, system_dark: bool = False) -> str:
    """Shared visual contract for current and future native Qt studios."""
    c = workbench_colors(theme, accent, system_dark=system_dark)
    metrics = workbench_metrics(theme)
    return f"""
        QWidget {{ background: {c.background}; color: {c.text}; font-size: {metrics.body_points}pt; }}
        QLabel {{ background: transparent; }}
        QWidget#workbenchSidebar {{ background: {c.sidebar}; border-right: 2px solid {c.border}; }}
        QWidget#workbenchTopbar {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c.editor}, stop:1 {c.sidebar}); border-bottom: 1px solid {c.border}; }}
        QLabel#workbenchBrand {{ color: {c.accent}; font-size: 17px; font-weight: 700; }}
        QLabel#workbenchCaption, QLabel#workbenchStatus, QLabel#workbenchFootnote {{
            color: {c.muted}; font-size: 12px;
        }}
        QLabel#workbenchSection {{ font-size: 17px; font-weight: 600; }}
        QLabel#heading {{ font-size: {metrics.heading_points}pt; font-weight: 600; padding-bottom: 4px; }}
        QScrollArea {{ background: {c.editor}; border: 0; }}
        QScrollArea > QWidget > QWidget {{ background: {c.editor}; }}
        QListWidget#workbenchNavigation {{
            background: {c.sidebar}; border: 0; padding: 8px 4px;
        }}
        QListWidget#workbenchNavigation::item {{
            border-radius: {metrics.radius}px; margin: 1px 2px; padding: {metrics.gap}px 8px;
        }}
        QListWidget#workbenchNavigation::item:hover {{ background: {c.hover}; }}
        QListWidget#workbenchNavigation::item:selected {{
            background: {c.accent}; color: {c.selected_text};
        }}
        QPushButton {{
            background: {c.surface}; border: 1px solid {c.border};
            border-radius: {metrics.radius}px; min-height: {metrics.control_height}px; padding: 3px 8px;
        }}
        QPushButton:hover {{ background: {c.hover}; border-color: {c.accent}; }}
        QPushButton:focus, QListWidget:focus, QTabBar::tab:focus,
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
        QAbstractSpinBox:focus, QTableView:focus, QTreeView:focus {{
            border: 2px solid {c.focus}; outline: 0;
        }}
        QPushButton:disabled {{ color: {c.muted}; }}
        QPlainTextEdit, QLineEdit, QComboBox, QTextEdit, QTableView {{
            background: {c.surface}; border: 1px solid {c.border};
            border-radius: 3px; padding: 3px; selection-background-color: {c.accent};
            selection-color: {c.selected_text};
        }}
        QPlainTextEdit {{ font-family: Consolas, 'DejaVu Sans Mono', monospace; }}
        QSplitter::handle {{ background: {c.border}; border: 1px solid {c.hover}; }}
        QSplitter::handle:hover {{ background: {c.accent}; }}
        QTabWidget::pane {{ border: 1px solid {c.border}; background: {c.editor}; }}
        QTabBar::tab {{
            background: {c.sidebar}; border: 1px solid {c.border};
            border-bottom: 0; padding: {metrics.gap + 2}px 14px; margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background: {c.editor}; border-top: 2px solid {c.accent};
            padding-top: {metrics.gap + 1}px;
        }}
        QTabBar::tab:hover {{ background: {c.hover}; }}
        QTableWidget {{
            background: {c.editor}; alternate-background-color: {c.surface};
            gridline-color: {c.border};
        }}
        QTableWidget QLabel {{ background: {c.editor}; color: {c.text}; padding: 3px; }}
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
        QMenuBar, QMenu, QToolBar {{ background: {c.sidebar}; color: {c.text}; }}
        QMenuBar::item, QMenu::item {{ padding: 5px 10px; background: transparent; }}
        QMenuBar::item:selected, QMenu::item:selected {{ background: {c.accent}; color: {c.selected_text}; }}
        QMenu::item:disabled {{ color: {c.muted}; }}
        QMenu::separator {{ height: 1px; background: {c.border}; margin: 4px 8px; }}
        QDialog, QWizard, QWizardPage, QMessageBox {{ background: {c.background}; color: {c.text}; }}
        QGroupBox {{ border: 1px solid {c.border}; border-radius: 4px; margin-top: 12px; padding: 8px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
        QTreeView, QListView {{ background: {c.editor}; alternate-background-color: {c.surface}; color: {c.text}; }}
        QTreeView::item:selected, QTableView::item:selected {{ background: {c.accent}; color: {c.selected_text}; }}
        QCheckBox, QRadioButton {{ spacing: 6px; background: transparent; }}
        QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {c.muted}; background: {c.surface}; }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {c.accent}; border: 2px solid {c.text}; }}
        QProgressBar {{ border: 1px solid {c.border}; background: {c.surface}; text-align: center; min-height: 14px; }}
        QProgressBar::chunk {{ background: {c.accent}; }}
        QDockWidget::title {{ background: {c.sidebar}; padding: 6px; }}
        QScrollBar:vertical {{ width: 12px; background: {c.background}; }}
        QScrollBar:horizontal {{ height: 12px; background: {c.background}; }}
        QScrollBar::handle {{ background: {c.border}; min-height: 24px; min-width: 24px; border-radius: 3px; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QToolButton {{ background: {c.sidebar}; border: 0; padding: 8px; }}
        QToolButton:hover {{ background: {c.hover}; }}
        QToolButton:checked {{ border-left: 3px solid {c.accent}; background: {c.editor}; }}
        QWidget[semanticState="error"] {{ color: {c.error}; }}
        QWidget[semanticState="warning"], QWidget[semanticState="unknown"] {{ color: {c.warning}; }}
        QWidget[semanticState="success"] {{ color: {c.success}; }}
    """
