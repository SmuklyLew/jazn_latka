from __future__ import annotations

from typing import TYPE_CHECKING
import sqlite3

from latka_jazn.memory.memory_tier_support import WriteSummary
from latka_jazn.memory.memory_tiers import MemoryRecord


if TYPE_CHECKING:
    from contextlib import _GeneratorContextManager

    class MemoryTierStoreMixinHost:
        """Static contract supplied by the composed MemoryTierStore."""

        con: sqlite3.Connection

        def _require_transaction(self) -> None: ...

        def transaction(self) -> _GeneratorContextManager[None, None, None]: ...

        def write_record(self, record: MemoryRecord) -> WriteSummary: ...
else:
    class MemoryTierStoreMixinHost:
        """Runtime-neutral base for MemoryTierStore mixins."""

        pass
