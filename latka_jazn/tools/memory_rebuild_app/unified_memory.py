from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .candidate_editor import CandidateEditorMixin
from .candidate_relations import CandidateRelationsMixin
from .unified_core import UnifiedCoreMixin
from .unified_migration import UnifiedMigrationMixin
from .unified_schema import (
    CANONICAL_DATABASE_NAME,
    LEGACY_DATABASE_NAMES,
    UNIFIED_SCHEMA_VERSION,
    UnifiedImportResult,
)
from .adapters import default_adapter_registry
from .settings import MemoryRebuildSettings

if TYPE_CHECKING:
    from .adapters.registry import AdapterRegistry


class UnifiedMemoryDatabase(
    UnifiedCoreMixin,
    UnifiedMigrationMixin,
    CandidateEditorMixin,
    CandidateRelationsMixin,
):
    """Jedna fizyczna baza SQLite: L0, dziennik, kandydaci, doświadczenia oraz L1/L2/L3."""

    def __init__(
        self,
        path: str | Path,
        *,
        settings: MemoryRebuildSettings | None = None,
        adapter_registry: "AdapterRegistry | None" = None,
    ) -> None:
        raw = Path(path).expanduser().resolve()
        if raw.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
            raw = raw / CANONICAL_DATABASE_NAME
        self.path = raw
        self.settings = settings or MemoryRebuildSettings()
        self.adapter_registry = adapter_registry or default_adapter_registry()


__all__ = [
    "CANONICAL_DATABASE_NAME",
    "LEGACY_DATABASE_NAMES",
    "UNIFIED_SCHEMA_VERSION",
    "UnifiedImportResult",
    "UnifiedMemoryDatabase",
]
