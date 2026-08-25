from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, TYPE_CHECKING
import sqlite3


if TYPE_CHECKING:
    from .adapters.registry import AdapterRegistry
    from .settings import MemoryRebuildSettings


    class UnifiedMixinHost:
        """Static contract supplied by the composed UnifiedMemoryDatabase."""

        path: Path
        settings: MemoryRebuildSettings
        adapter_registry: AdapterRegistry

        def __init__(
            self,
            path: str | Path,
            *,
            settings: MemoryRebuildSettings | None = None,
            adapter_registry: AdapterRegistry | None = None,
        ) -> None: ...

        def initialize(self) -> dict[str, Any]: ...

        def ensure_initialized(self) -> dict[str, Any]: ...

        def connect(self, *, read_only: bool = False) -> sqlite3.Connection: ...

        def backup(self, output: str | Path) -> Path: ...

        def checkpoint(self) -> None: ...

        def validate(self, *, full: bool = False) -> dict[str, Any]: ...

        def get_candidate(self, candidate_id: str) -> dict[str, Any]: ...

        def migrate_databases(
            self,
            databases: Iterable[str | Path],
            *,
            dry_run: bool = False,
        ) -> dict[str, Any]: ...
else:
    class UnifiedMixinHost:
        """Runtime-neutral base for mixins composed by UnifiedMemoryDatabase."""

        pass
