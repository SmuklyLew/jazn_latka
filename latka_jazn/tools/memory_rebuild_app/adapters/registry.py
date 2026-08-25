from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..intermediate import ImportAdapter
from ..source_detection import SourceProbe
from .chatgpt_json import ChatGptJsonAdapter
from .html import ChatHtmlAdapter
from .journal import JournalAdapter
from .legacy_sqlite import LegacySqliteAdapter
from .music_analysis import MusicAnalysisAdapter


class AdapterRegistry:
    def __init__(self, adapters: Iterable[ImportAdapter]) -> None:
        self.adapters = tuple(adapters)
        ids = [adapter.adapter_id for adapter in self.adapters]
        if len(ids) != len(set(ids)):
            raise ValueError("Adapter IDs must be unique")

    def select(self, path: Path, probe: SourceProbe) -> ImportAdapter:
        matches = [adapter for adapter in self.adapters if adapter.supports(path, probe)]
        if not matches:
            raise ValueError(
                f"Brak bezpiecznego adaptera dla {path.name}: kind={probe.kind}, suffix={path.suffix.casefold()}"
            )
        return matches[0]

    def ids(self) -> tuple[str, ...]:
        return tuple(adapter.adapter_id for adapter in self.adapters)


def default_adapter_registry() -> AdapterRegistry:
    return AdapterRegistry((
        ChatHtmlAdapter(),
        ChatGptJsonAdapter(),
        JournalAdapter(),
        MusicAnalysisAdapter(),
        LegacySqliteAdapter(),
    ))


__all__ = ["AdapterRegistry", "default_adapter_registry"]
