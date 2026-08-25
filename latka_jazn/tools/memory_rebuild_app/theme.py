from __future__ import annotations

"""Presentation-only theme values; no storage or policy decisions belong here."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemoryRebuildTheme:
    name: str = "latka-default"
    title: str = "Jaźń Memory Rebuild v16+"
    accent: str = "#6C63FF"
    success: str = "#2E8B57"
    warning: str = "#D97706"
    danger: str = "#B91C1C"
    muted: str = "#6B7280"
    l0_label: str = "Archiwum źródłowe L0"
    active_label: str = "Pamięć aktywna"
    unknown_label: str = "Nie wiem — brak wystarczających dowodów"


DEFAULT_THEME = MemoryRebuildTheme()

__all__ = ["DEFAULT_THEME", "MemoryRebuildTheme"]
