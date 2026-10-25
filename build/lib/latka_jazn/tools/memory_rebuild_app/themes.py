from __future__ import annotations

"""Concrete visual palettes for Memory Rebuild Studio.

The default P0 palette is inspired by the supplied terminal application example:
dark navy surfaces, warm peach accents, lavender selection, and restrained status
colours. This module only translates theme tokens into UI styles.
"""

from .theme import DEFAULT_THEME, MemoryRebuildTheme


TERMINAL_STUDIO_THEME = MemoryRebuildTheme(
    name="latka-terminal",
    title="Jaźń Memory Rebuild Studio",
    background="#0E101A",
    panel="#171A27",
    panel_alt="#23283B",
    border="#F29A63",
    accent="#B58AF1",
    accent_soft="#D0B0FA",
    text="#E8E4F2",
    text_muted="#9295AA",
    selection="#33384F",
    success="#75D190",
    warning="#F2A45D",
    danger="#EF6A78",
    info="#65A7FF",
)

THEMES: dict[str, MemoryRebuildTheme] = {
    TERMINAL_STUDIO_THEME.name: TERMINAL_STUDIO_THEME,
    DEFAULT_THEME.name: DEFAULT_THEME,
}
DEFAULT_STUDIO_THEME_NAME = TERMINAL_STUDIO_THEME.name


def get_theme(name: str | None = None) -> MemoryRebuildTheme:
    return THEMES.get(str(name or DEFAULT_STUDIO_THEME_NAME), TERMINAL_STUDIO_THEME)


def cycle_theme_name(current: str) -> str:
    names = tuple(THEMES)
    try:
        index = names.index(current)
    except ValueError:
        return names[0]
    return names[(index + 1) % len(names)]


def prompt_toolkit_style(theme: MemoryRebuildTheme):
    """Build prompt_toolkit ``Style`` lazily so imports remain optional."""

    from prompt_toolkit.styles import Style

    return Style.from_dict(
        {
            "": f"bg:{theme.background} {theme.text}",
            "header": f"bg:{theme.background} {theme.text}",
            "header-title": f"bg:{theme.background} {theme.border} bold",
            "header-version": f"bg:{theme.background} {theme.text_muted}",
            "tabs": f"bg:{theme.background} {theme.text_muted}",
            "tab": f"bg:{theme.background} {theme.text_muted}",
            "tab-active": f"bg:{theme.accent} {theme.background} bold",
            "frame": f"bg:{theme.panel} {theme.border}",
            "sidebar": f"bg:{theme.panel} {theme.text}",
            "content": f"bg:{theme.panel} {theme.text}",
            "section": f"bg:{theme.panel} {theme.border} bold",
            "selected": f"bg:{theme.selection} {theme.accent_soft} bold",
            "muted": f"bg:{theme.panel} {theme.text_muted}",
            "accent": f"bg:{theme.panel} {theme.accent_soft}",
            "success": f"bg:{theme.panel} {theme.success}",
            "warning": f"bg:{theme.panel} {theme.warning}",
            "danger": f"bg:{theme.panel} {theme.danger}",
            "info": f"bg:{theme.panel} {theme.info}",
            "status": f"bg:{theme.panel_alt} {theme.text_muted}",
            "status-ok": f"bg:{theme.panel_alt} {theme.success}",
            "status-error": f"bg:{theme.panel_alt} {theme.danger}",
            "footer": f"bg:{theme.panel_alt} {theme.text_muted}",
            "footer-key": f"bg:{theme.panel_alt} {theme.border} bold",
        }
    )


__all__ = [
    "DEFAULT_STUDIO_THEME_NAME",
    "TERMINAL_STUDIO_THEME",
    "THEMES",
    "cycle_theme_name",
    "get_theme",
    "prompt_toolkit_style",
]
