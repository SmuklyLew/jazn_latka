from __future__ import annotations

"""v16 canonical-workspace adapter for LivingMemory.

The full read-only recall implementation is kept in ``_living_memory_gateway_impl``.
This adapter changes only source-registry discovery so mutable host state is read
from the single canonical ``workspace_runtime`` rather than from a per-version
runtime directory.
"""

import json
import os
from pathlib import Path
from typing import Any

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.memory._living_memory_gateway_impl import (
    REGISTRY_FILENAME,
    SCHEMA_VERSION,
    LivingMemoryGateway as _LivingMemoryGateway,
    LivingMemoryHit,
)
from latka_jazn.tools.memory_rebuild_common import DATABASE_FILENAMES


class LivingMemoryGateway(_LivingMemoryGateway):
    """LivingMemory gateway whose mutable registry follows the host workspace."""

    def discover(self) -> list[dict[str, Any]]:
        candidates: list[tuple[Path, str]] = [(self.root, "active_runtime_root")]
        env_value = os.environ.get("JAZN_MEMORY_SOURCE_ROOTS", "")
        for raw in env_value.split(os.pathsep):
            if raw.strip():
                candidates.append((Path(raw).expanduser(), "environment_registry"))

        registry = workspace_runtime_path(self.root) / REGISTRY_FILENAME
        if registry.is_file():
            try:
                payload = json.loads(registry.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                payload = {}
            entries = payload.get("sources") if isinstance(payload, dict) else []
            if isinstance(entries, list):
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("enabled", True) is not True or entry.get("read_only", True) is not True:
                        continue
                    raw_path = str(entry.get("path") or "").strip()
                    if raw_path:
                        candidates.append((Path(raw_path).expanduser(), "workspace_registry"))

        discovered: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for candidate, origin in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            sqlite_dir = self._as_sqlite_dir(resolved)
            if sqlite_dir in seen:
                continue
            seen.add(sqlite_dir)
            databases = {key: sqlite_dir / filename for key, filename in DATABASE_FILENAMES.items()}
            available = {key: path.is_file() for key, path in databases.items()}
            discovered.append(
                {
                    "root": str(resolved),
                    "sqlite_dir": str(sqlite_dir),
                    "origin": origin,
                    "available": available,
                    "database_paths": {key: str(path) for key, path in databases.items()},
                    "recall_ready": any(available.get(key, False) for key in self.SEARCH_ORDER),
                    "import_catalog_used_for_recall": False,
                    "read_only": True,
                }
            )
        return discovered


__all__ = ["LivingMemoryGateway", "LivingMemoryHit", "REGISTRY_FILENAME", "SCHEMA_VERSION"]
