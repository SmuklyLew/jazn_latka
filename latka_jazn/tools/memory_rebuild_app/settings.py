from __future__ import annotations

"""Validated settings for import, retrieval, and optional embeddings."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping
import json
import os


@dataclass(frozen=True, slots=True)
class MemoryRebuildSettings:
    require_fts5: bool = True
    embeddings_enabled: bool = False
    embedding_model: str | None = None
    retrieval_limit: int = 20
    min_lexical_score: float = 0.0
    require_provenance: bool = True
    automatic_l2: bool = False
    automatic_l3: bool = False
    automatic_activation: bool = False

    def __post_init__(self) -> None:
        if not self.require_fts5:
            raise ValueError("FTS5 jest obowiązkowym baseline i nie może zostać wyłączone.")
        if self.retrieval_limit < 1 or self.retrieval_limit > 500:
            raise ValueError("retrieval_limit musi mieścić się w zakresie 1..500")
        if not 0.0 <= self.min_lexical_score <= 1.0:
            raise ValueError("min_lexical_score musi mieścić się w zakresie 0..1")
        if self.embeddings_enabled and not (self.embedding_model or "").strip():
            raise ValueError("Włączone embeddingi wymagają jawnie wskazanego modelu.")
        if self.automatic_l2 or self.automatic_l3 or self.automatic_activation:
            raise ValueError("Memory Rebuild nie zezwala na automatyczne L2, L3 ani aktywację.")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MemoryRebuildSettings":
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"Nieznane ustawienia Memory Rebuild: {', '.join(unknown)}")
        return cls(**{key: value[key] for key in allowed if key in value})

    def with_overrides(self, **changes: Any) -> "MemoryRebuildSettings":
        return replace(self, **changes)


def load_settings(path: str | Path | None = None) -> MemoryRebuildSettings:
    configured = path or os.environ.get("JAZN_MEMORY_REBUILD_SETTINGS")
    if not configured:
        return MemoryRebuildSettings()
    source = Path(configured).expanduser().resolve()
    value = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Plik ustawień Memory Rebuild musi zawierać obiekt JSON.")
    return MemoryRebuildSettings.from_mapping(value)


__all__ = ["MemoryRebuildSettings", "load_settings"]
