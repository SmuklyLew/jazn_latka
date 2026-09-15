from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import os

from latka_jazn.memory.availability import build_memory_availability_status
from latka_jazn.memory.memory_root import legacy_memory_root, memory_path, resolve_memory_root
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.runtime_memory import RuntimeMemoryCoordinator
from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.memory_rebuild_app.unified_schema import CANONICAL_DATABASE_NAME
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("runtime_memory_install")
DEFAULT_TIER_DB = "sqlite/runtime_write_v2/runtime_memory.sqlite3"
LEGACY_DEFAULT_TIER_DB = f"memory/{DEFAULT_TIER_DB}"


@dataclass(slots=True, frozen=True)
class RuntimeMemoryInstallStatus:
    installed: bool
    database_path: str
    legacy_classifier_type: str
    layered_fanout_blocked: bool
    persistent_memory_enabled: bool = True
    memory_state: str = "persistent_memory_present"
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "RuntimeMemoryCoordinator keeps one stable interface with or without private MEMORY. "
        "When persistent memory is absent/disabled, persistence is fail-closed and no L1/L2/L3 database is created. "
        "When verified MEMORY is present, installation replaces legacy fan-out with transactional L1/L2; L2 never "
        "auto-promotes to L3."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LegacyLayeredMemoryReadOnlyAdapter:
    """Preserve legacy reads while blocking automatic consolidation writes."""

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped
        self.blocked_write_count = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def consolidate_from_plan(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        self.blocked_write_count += 1
        return {
            "status": "blocked_legacy_fanout",
            "schema_version": SCHEMA_VERSION,
            "automatic_l3": False,
            "truth_boundary": (
                "Legacy LayeredMemory fan-out is disabled. With persistent MEMORY attached, selected memory enters "
                "L1/L2 through RuntimeMemoryCoordinator. Without MEMORY, core dialogue continues and no private-memory "
                "promotion is attempted."
            ),
        }


def _strip_memory_prefix(path: Path) -> Path:
    parts = path.parts
    if parts and parts[0].casefold() == "memory":
        return Path(*parts[1:])
    return path


def _configured_tier_path(runtime_root: Path, configured: str | Path) -> Path:
    """Map historical version-local tier paths into the selected persistent memory root."""

    candidate = Path(configured).expanduser()
    selected_root = resolve_memory_root(runtime_root)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        for base in (selected_root, legacy_memory_root(runtime_root)):
            try:
                inner = resolved.relative_to(base)
            except ValueError:
                continue
            return (selected_root / inner).resolve()
        try:
            relative_runtime = resolved.relative_to(runtime_root)
        except ValueError as exc:
            raise ValueError("configured memory tier database must be inside runtime or memory root") from exc
        return memory_path(runtime_root, _strip_memory_prefix(relative_runtime))
    return memory_path(runtime_root, _strip_memory_prefix(candidate))


def _native_unified_tier_path(runtime_root: Path) -> Path | None:
    availability = build_memory_availability_status(runtime_root)
    if not availability.persistent_memory_enabled:
        return None
    canonical = memory_path(runtime_root, Path("sqlite") / CANONICAL_DATABASE_NAME)
    probe = probe_unified_memory_database(canonical)
    if probe.get("memory_search_ready") is True:
        return canonical
    return None


def resolve_memory_tier_database_path(
    root: str | Path,
    *,
    configured: str | Path | None = None,
) -> Path:
    """Resolve the canonical persistent L1/L2/L3 store without creating it.

    A verified native unified ``memory_jazn.sqlite3`` is preferred when persistent
    MEMORY is present. In SYSTEM-only mode this returns the future canonical
    MEMORY path only as an identity; callers must consult memory availability
    before opening it for writes.
    """

    runtime_root = Path(root).expanduser().resolve()
    explicit_env = os.environ.get("JAZN_MEMORY_TIER_DB")

    if configured is not None:
        configured_path = _configured_tier_path(runtime_root, configured)
        configured_text = str(configured).replace("\\", "/").strip().casefold()
        default_like = configured_text.endswith(LEGACY_DEFAULT_TIER_DB.casefold()) or configured_text.endswith(DEFAULT_TIER_DB.casefold())
        if explicit_env is None and default_like:
            unified = _native_unified_tier_path(runtime_root)
            if unified is not None:
                return unified
        return configured_path

    if explicit_env is not None and explicit_env.strip():
        raw = Path(explicit_env.strip())
        if raw.is_absolute():
            raise ValueError("JAZN_MEMORY_TIER_DB must be relative to JAZN_MEMORY_ROOT")
        return memory_path(runtime_root, _strip_memory_prefix(raw))

    unified = _native_unified_tier_path(runtime_root)
    if unified is not None:
        return unified
    return memory_path(runtime_root, DEFAULT_TIER_DB)


def initialize_transactional_memory_store(root: str | Path, *, configured: str | Path | None = None) -> dict[str, Any]:
    """Create/validate transactional memory only when persistent MEMORY is enabled."""

    runtime_root = Path(root).expanduser().resolve()
    availability = build_memory_availability_status(runtime_root)
    database_path = resolve_memory_tier_database_path(runtime_root, configured=configured)
    if not availability.persistent_memory_enabled:
        required_missing = bool(availability.persistent_memory_required and not availability.required_satisfied)
        return {
            "ok": not required_missing,
            "status": availability.status,
            "skipped": True,
            "database_path": str(database_path),
            "persistent_memory_enabled": False,
            "error": "persistent_memory_required_missing" if required_missing else None,
            "memory_availability": availability.to_dict(),
        }
    try:
        with MemoryTierStore(database_path) as store:
            validation = store.validate(full=False)
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "ok": False,
            "status": "transactional_memory_initialization_failed",
            "database_path": str(database_path),
            "persistent_memory_enabled": True,
            "error": f"{type(exc).__name__}: {exc}",
            "validation": {},
            "memory_availability": availability.to_dict(),
        }
    return {
        "ok": validation.get("ok") is True,
        "status": "ready" if validation.get("ok") is True else "validation_failed",
        "database_path": str(database_path),
        "persistent_memory_enabled": True,
        "validation": validation,
        "memory_availability": availability.to_dict(),
    }


def _tier_database_path(engine: Any) -> Path:
    config = engine.config
    return resolve_memory_tier_database_path(
        config.root,
        configured=getattr(config, "memory_tier_db_path", None),
    )


def install_runtime_memory(engine: Any) -> RuntimeMemoryInstallStatus:
    availability = build_memory_availability_status(
        engine.config.root,
        mode=getattr(engine.config, "memory_mode", None),
    )
    current = getattr(engine, "runtime_memory", None)
    if isinstance(current, RuntimeMemoryCoordinator):
        layered = getattr(engine, "layered_memory", None)
        return RuntimeMemoryInstallStatus(
            installed=False,
            database_path=str(current.database_path),
            legacy_classifier_type=type(current.classifier).__name__,
            layered_fanout_blocked=isinstance(layered, LegacyLayeredMemoryReadOnlyAdapter),
            persistent_memory_enabled=current.persistence_enabled,
            memory_state=availability.status,
        )
    if current is None:
        raise RuntimeError("engine has no runtime memory classifier")

    database_path = _tier_database_path(engine)
    engine.runtime_memory_legacy_classifier = current
    engine.runtime_memory = RuntimeMemoryCoordinator(
        database_path,
        classifier=current,
        persistence_enabled=availability.persistent_memory_enabled,
        disabled_reason=availability.status,
    )
    layered = getattr(engine, "layered_memory", None)
    if layered is not None and not isinstance(layered, LegacyLayeredMemoryReadOnlyAdapter):
        engine.layered_memory = LegacyLayeredMemoryReadOnlyAdapter(layered)
    return RuntimeMemoryInstallStatus(
        installed=True,
        database_path=str(database_path),
        legacy_classifier_type=type(current).__name__,
        layered_fanout_blocked=isinstance(getattr(engine, "layered_memory", None), LegacyLayeredMemoryReadOnlyAdapter),
        persistent_memory_enabled=availability.persistent_memory_enabled,
        memory_state=availability.status,
    )
