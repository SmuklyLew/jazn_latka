from __future__ import annotations

"""v16 canonical-workspace adapter for LivingMemory.

The full read-only recall implementation is kept in ``_living_memory_gateway_impl``.
This adapter changes source-registry discovery so mutable host state is read from the
single canonical ``workspace_runtime`` and applies the v16.2.3 referential-focus
contract before the shared search implementation runs.
"""

from copy import copy, deepcopy
from dataclasses import replace
import json
import os
import time
from pathlib import Path
from typing import Any

from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.memory._living_memory_gateway_impl import (
    REGISTRY_FILENAME,
    SCHEMA_VERSION,
    LivingMemoryGateway as _LivingMemoryGateway,
    LivingMemoryHit,
)
from latka_jazn.memory.memory_root import resolve_memory_root
from latka_jazn.memory.memory_tier_reader import probe_memory_tier_database_readonly
from latka_jazn.memory.runtime_memory_install import resolve_memory_tier_database_path
from latka_jazn.memory.unified_memory_runtime import (
    probe_legacy_memory_layout,
    probe_unified_memory_database,
)
from latka_jazn.tools.memory_rebuild_app.unified_schema import CANONICAL_DATABASE_NAME
from latka_jazn.tools.memory_rebuild_common import DATABASE_FILENAMES


class LivingMemoryGateway(_LivingMemoryGateway):
    """Select exactly one native unified database, with legacy read-only fallback."""

    def __init__(
        self,
        root: str | Path,
        *,
        busy_timeout_ms: int = 10_000,
        discovery_cache_seconds: float = 60.0,
        graph_retrieval_mode: str | None = None,
    ) -> None:
        resolved_graph_mode = str(
            graph_retrieval_mode
            if graph_retrieval_mode is not None
            else os.environ.get("JAZN_GRAPH_RETRIEVAL_MODE", "shadow")
        ).strip().lower()
        super().__init__(
            root,
            busy_timeout_ms=busy_timeout_ms,
            graph_retrieval_mode=resolved_graph_mode,
        )
        self.discovery_cache_seconds = max(0.0, float(discovery_cache_seconds))
        self._discovery_cached_at = 0.0
        self._discovery_cache: list[dict[str, Any]] | None = None

    @staticmethod
    def _candidate_sqlite_dir(path: Path) -> Path:
        if path.is_file():
            return path.parent
        if path.name.casefold() == "sqlite":
            return path
        if path.name.casefold() == "memory":
            return path / "sqlite"
        return _LivingMemoryGateway._as_sqlite_dir(path)

    @classmethod
    def _candidate_native_database(cls, path: Path) -> Path:
        if path.is_file():
            return path
        return cls._candidate_sqlite_dir(path) / CANONICAL_DATABASE_NAME

    def _referential_plan(self, plan: Any) -> Any:
        mode = str(getattr(plan, "search_mode", None) or "")
        context_query = str(getattr(plan, "context_query", None) or "").strip()
        if mode != "referential_followup" or not context_query:
            return plan
        context_plan = MemorySearchPlanner(self.root).plan(context_query)
        focus = list(context_plan.focus_terms or [])
        if not focus:
            return plan
        try:
            return replace(plan, focus_terms=focus)
        except TypeError:
            clone = copy(plan)
            try:
                setattr(clone, "focus_terms", focus)
            except (AttributeError, TypeError):
                return plan
            return clone

    def search(
        self,
        plan: Any,
        *,
        limit: int = 6,
        should_continue: Any | None = None,
    ) -> dict[str, Any]:
        effective_plan = self._referential_plan(plan)
        result = super().search(
            effective_plan,
            limit=limit,
            should_continue=should_continue,
        )
        if effective_plan is not plan:
            result["referential_focus"] = {
                "status": "previous_query_focus_selected",
                "control_instruction_used_as_fts_term": False,
                "focus_term_count": len(getattr(effective_plan, "focus_terms", None) or []),
                "private_content_recorded_in_telemetry": False,
            }
        return result

    def discover(self) -> list[dict[str, Any]]:
        active_memory_root = resolve_memory_root(self.root)
        candidates: list[tuple[Path, str, bool, str | None]] = [
            (active_memory_root, "active_memory_root", True, "active_memory_root_boundary")
        ]
        env_value = os.environ.get("JAZN_MEMORY_SOURCE_ROOTS", "")
        for raw in env_value.split(os.pathsep):
            if raw.strip():
                candidates.append(
                    (
                        Path(raw).expanduser(),
                        "environment_registry",
                        True,
                        "operator_environment_override",
                    )
                )

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
                        declared_trust_basis = str(entry.get("trust_basis") or "").strip()
                        source_trusted = bool(
                            entry.get("trusted") is True and declared_trust_basis
                        )
                        candidates.append(
                            (
                                Path(raw_path).expanduser(),
                                "workspace_registry",
                                source_trusted,
                                declared_trust_basis if source_trusted else None,
                            )
                        )

        discovered: list[dict[str, Any]] = []
        normalized: list[tuple[Path, Path, str, bool, str | None]] = []
        normalized_index: dict[Path, int] = {}
        for candidate, origin, source_trusted, trust_basis in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            sqlite_dir = self._candidate_sqlite_dir(resolved)
            existing_index = normalized_index.get(sqlite_dir)
            if existing_index is not None:
                existing = normalized[existing_index]
                if source_trusted and not existing[3]:
                    normalized[existing_index] = (
                        resolved,
                        sqlite_dir,
                        origin,
                        source_trusted,
                        trust_basis,
                    )
                continue
            normalized_index[sqlite_dir] = len(normalized)
            normalized.append(
                (resolved, sqlite_dir, origin, source_trusted, trust_basis)
            )

        for resolved, sqlite_dir, origin, source_trusted, trust_basis in normalized:
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
                structural_recall_ready = True
            else:
                database_paths = {key: str(path) for key, path in databases.items()}
                source_kind = "legacy_five_database_compatibility"
                structural_recall_ready = bool(legacy_probe.get("legacy_search_ready"))
            recall_ready = bool(source_trusted and structural_recall_ready)
            discovered.append(
                {
                    "root": str(resolved),
                    "sqlite_dir": str(sqlite_dir),
                    "origin": origin,
                    "available": available,
                    "database_paths": database_paths,
                    "canonical_database": str(native_database) if native_ready else None,
                    "source_kind": source_kind,
                    "source_trusted": source_trusted,
                    "trust_basis": trust_basis,
                    "trust_issue": (
                        None
                        if source_trusted
                        else "workspace_registry_explicit_trust_required"
                    ),
                    "native_structurally_ready": native_ready,
                    "legacy_structurally_ready": bool(
                        legacy_probe.get("legacy_search_ready")
                    ),
                    "memory_search_ready": bool(source_trusted and native_ready),
                    "legacy_search_ready": bool(
                        source_trusted and legacy_probe.get("legacy_search_ready")
                    ),
                    "recall_ready": recall_ready,
                    "native_probe": native_probe,
                    "legacy_probe": legacy_probe,
                    "import_catalog_used_for_recall": False,
                    "read_only": True,
                    "ignored_reason": None if source_trusted else "source_not_trusted",
                }
            )

        tier_database = resolve_memory_tier_database_path(self.root)
        tier_probe = probe_memory_tier_database_readonly(
            tier_database,
            busy_timeout_ms=self.busy_timeout_ms,
        )
        tier_ready = bool(tier_probe.get("memory_search_ready"))
        same_native = next(
            (
                item
                for item in discovered
                if item.get("source_kind") == "native_unified"
                and item.get("canonical_database") == str(tier_database)
            ),
            None,
        )
        if same_native is not None:
            same_native["transactional_tier_structurally_ready"] = tier_ready
            same_native["transactional_tier_probe"] = tier_probe
            same_native["transactional_tier_same_database"] = True
            same_native["selected_transactional_tier"] = tier_ready
            same_native["recall_ready"] = bool(same_native.get("recall_ready") or tier_ready)
        elif tier_database.is_file():
            discovered.append(
                {
                    "root": str(active_memory_root),
                    "sqlite_dir": str(tier_database.parent),
                    "origin": "active_memory_transactional_tier",
                    "available": {"memory_jazn": True},
                    "database_paths": {"memory_jazn": str(tier_database)},
                    "canonical_database": str(tier_database),
                    "source_kind": "transactional_tier_memory",
                    "source_trusted": True,
                    "trust_basis": "active_memory_root_boundary",
                    "trust_issue": None,
                    "native_structurally_ready": False,
                    "legacy_structurally_ready": False,
                    "transactional_tier_structurally_ready": tier_ready,
                    "memory_search_ready": tier_ready,
                    "legacy_search_ready": False,
                    "recall_ready": tier_ready,
                    "native_probe": {},
                    "legacy_probe": {},
                    "transactional_tier_probe": tier_probe,
                    "transactional_tier_same_database": False,
                    "import_catalog_used_for_recall": False,
                    "read_only": True,
                    "selected_canonical": False,
                    "selected_transactional_tier": tier_ready,
                    "ignored_reason": None if tier_ready else "transactional_tier_not_read_ready",
                }
            )

        selected_native = next(
            (
                item
                for item in discovered
                if item.get("source_kind") == "native_unified"
                and item.get("memory_search_ready")
            ),
            None,
        )
        if selected_native is not None:
            for item in discovered:
                if item.get("source_kind") == "transactional_tier_memory":
                    item["selected_canonical"] = False
                    continue
                selected = item is selected_native
                item["selected_canonical"] = selected
                if not selected:
                    item["recall_ready"] = False
                    if item.get("source_trusted") is True:
                        item["ignored_reason"] = "another_native_unified_database_selected"
        else:
            for item in discovered:
                item.setdefault("selected_canonical", False)
        self._discovery_cache = deepcopy(discovered)
        self._discovery_cached_at = time.monotonic()
        return discovered

    def invalidate_discovery_cache(self) -> None:
        self._discovery_cache = None
        self._discovery_cached_at = 0.0

    def readiness(self) -> dict[str, Any]:
        sources = self.discover()
        selected = next((item for item in sources if item.get("selected_canonical")), None)
        tier = next((item for item in sources if item.get("selected_transactional_tier")), None)
        legacy = [item for item in sources if item.get("legacy_search_ready")]
        same_database = bool(selected is not None and tier is selected)
        if same_database:
            status = "ready_native_unified_transactional_single_database"
        elif selected is not None and tier is not None:
            status = "ready_native_plus_transactional_tier"
        elif selected is not None:
            status = "ready_native_unified"
        elif tier is not None:
            status = "ready_transactional_tier_only"
        elif legacy:
            status = "ready_legacy_compatibility_only"
        else:
            status = "no_ready_memory_source"
        memory_ready = selected is not None or tier is not None
        selected_source_count = 0
        if selected is not None:
            selected_source_count += 1
        if tier is not None and tier is not selected:
            selected_source_count += 1
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "memory_search_ready": memory_ready,
            "transactional_tier_search_ready": tier is not None,
            "transactional_tier_same_database": same_database,
            "legacy_search_ready": bool(legacy),
            "canonical_database": (
                selected.get("canonical_database")
                if selected
                else (tier.get("canonical_database") if tier else None)
            ),
            "selected_source_count": selected_source_count,
            "source_count": len(sources),
            "sources": sources,
            "truth_boundary": (
                "memory_search_ready wymaga jawnie zaufanego źródła i poprawnej próby read-only. "
                "Zweryfikowana natywna baza unified może być jednocześnie transactional L1/L2/L3, "
                "co usuwa drugi niewidoczny świat pamięci. Układ pięciu baz pozostaje wyłącznie "
                "zgodnością read-only, a sidecary i wake-state są warstwami pochodnymi."
            ),
        }


__all__ = ["LivingMemoryGateway", "LivingMemoryHit", "REGISTRY_FILENAME", "SCHEMA_VERSION"]
