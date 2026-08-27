from __future__ import annotations

"""Presentation-only theme tokens for Memory Rebuild Studio.

No storage, recall, promotion, or truth-policy decisions belong in this module.
The P0 studio keeps theme tokens separate from concrete palettes (``themes.py``)
and terminal layout construction (``layout.py``).
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemoryRebuildTheme:
    name: str = "latka-default"
    title: str = "Jaźń Memory Rebuild v16+"
    background: str = "#11131D"
    panel: str = "#191C29"
    panel_alt: str = "#24293D"
    border: str = "#7C83A7"
    accent: str = "#6C63FF"
    accent_soft: str = "#9B94FF"
    text: str = "#F0EEF7"
    text_muted: str = "#9498AE"
    selection: str = "#303650"
    success: str = "#2E8B57"
    warning: str = "#D97706"
    danger: str = "#B91C1C"
    info: str = "#5EA2FF"
    l0_label: str = "Archiwum źródłowe L0"
    active_label: str = "Pamięć aktywna"
    unknown_label: str = "Nie wiem — brak wystarczających dowodów"


DEFAULT_THEME = MemoryRebuildTheme()

__all__ = ["DEFAULT_THEME", "MemoryRebuildTheme"]
