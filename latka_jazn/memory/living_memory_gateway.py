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
from latka_jazn.memory.unified_memory_runtime import (
    probe_legacy_memory_layout,
    probe_unified_memory_database,
)
from latka_jazn.tools.memory_rebuild_app.unified_schema import CANONICAL_DATABASE_NAME
from latka_jazn.tools.memory_rebuild_common import DATABASE_FILENAMES


class LivingMemoryGateway(_LivingMemoryGateway):
    """Select exactly one native unified database, with legacy read-only fallback."""

    @staticmethod
    def _candidate_sqlite_dir(path: Path) -> Path:
        if path.is_file():
            return path.parent
        return _LivingMemoryGateway._as_sqlite_dir(path)

    @classmethod
    def _candidate_native_database(cls, path: Path) -> Path:
        if path.is_file():
            return path
        return cls._candidate_sqlite_dir(path) / CANONICAL_DATABASE_NAME

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
            sqlite_dir = self._candidate_sqlite_dir(resolved)
            if sqlite_dir in seen:
                continue
            seen.add(sqlite_dir)
            databases = {key: sqlite_dir / filename for key, filename in DATABASE_FILENAMES.items()}
            available = {key: path.is_file() for key, path in databases.items()}
            native_database = self._candidate_native_database(resolved)
            native_probe = probe_unified_memory_database(
                native_database,
                busy_timeout_ms=self.busy_timeout_ms,
            )
            native_ready = bool(native_probe.get("memory_search_ready"))
            legacy_probe = (
                probe_legacy_memory_layout(
                    databases,
                    busy_timeout_ms=self.busy_timeout_ms,
                )
                if not native_ready
                else {
                    "status": "not_evaluated_native_selected",
                    "legacy_search_ready": False,
                    "memory_search_ready": False,
                }
            )
            if native_ready:
                database_paths = {key: str(native_database) for key in self.SEARCH_ORDER}
                source_kind = "native_unified"
                recall_ready = True
            else:
                database_paths = {key: str(path) for key, path in databases.items()}
                source_kind = "legacy_five_database_compatibility"
                recall_ready = bool(legacy_probe.get("legacy_search_ready"))
            discovered.append(
                {
                    "root": str(resolved),
                    "sqlite_dir": str(sqlite_dir),
                    "origin": origin,
                    "available": available,
                    "database_paths": database_paths,
                    "canonical_database": str(native_database) if native_ready else None,
                    "source_kind": source_kind,
                    "memory_search_ready": native_ready,
                    "legacy_search_ready": bool(legacy_probe.get("legacy_search_ready")),
                    "recall_ready": recall_ready,
                    "native_probe": native_probe,
                    "legacy_probe": legacy_probe,
                    "import_catalog_used_for_recall": False,
                    "read_only": True,
                }
            )

        selected_native = next(
            (item for item in discovered if item.get("memory_search_ready")),
            None,
        )
        if selected_native is not None:
            for item in discovered:
                selected = item is selected_native
                item["selected_canonical"] = selected
                if not selected:
                    item["recall_ready"] = False
                    item["ignored_reason"] = "another_native_unified_database_selected"
        else:
            for item in discovered:
                item["selected_canonical"] = False
        return discovered

    def readiness(self) -> dict[str, Any]:
        sources = self.discover()
        selected = next((item for item in sources if item.get("selected_canonical")), None)
        legacy = [item for item in sources if item.get("legacy_search_ready")]
        if selected is not None:
            status = "ready_native_unified"
        elif legacy:
            status = "ready_legacy_compatibility_only"
        else:
            status = "no_ready_memory_source"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "memory_search_ready": selected is not None,
            "legacy_search_ready": bool(legacy),
            "canonical_database": selected.get("canonical_database") if selected else None,
            "selected_source_count": 1 if selected else 0,
            "source_count": len(sources),
            "sources": sources,
            "truth_boundary": (
                "memory_search_ready wymaga jednej natywnej bazy unified z poprawną tożsamością "
                "schematu, integralnością, FTS i działającą próbą odczytu. Układ pięciu baz jest "
                "wyłącznie zgodnością read-only i nie jest drugim kanonicznym runtime."
            ),
        }


__all__ = ["LivingMemoryGateway", "LivingMemoryHit", "REGISTRY_FILENAME", "SCHEMA_VERSION"]
