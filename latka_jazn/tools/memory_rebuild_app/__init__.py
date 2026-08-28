from __future__ import annotations

from .baseline_registry import baseline_from_path, discover_baseline_roots, refresh_baseline
from .adapters import AdapterRegistry, default_adapter_registry
from .config import APP_VERSION, TOOL_VERSION
from .controller import MemoryRebuildAppController, MemoryRebuildAppError
from .final_export import EXPORT_SCHEMA, export_final_memory
from .html_import import HtmlImportResult, import_chat_html
from .models import (
    BaselineSpec,
    PIPELINES,
    PROJECT_SCHEMA,
    RebuildProject,
    SOURCE_ROLES,
    SourceSpec,
    TRUTH_DOMAINS,
)
from .project_store import ProjectStore, default_project_root
from .source_inventory import SourceInspection, inspect_source, inspect_sources
from .settings import MemoryRebuildSettings, load_settings
from .source_union import (
    SOURCE_UNION_SCHEMA,
    TOOL_RELEASE_LABEL,
    TOOL_REVISION,
    build_source_union_manifest,
    run_source_union_analysis,
)
from .sqlite_inspector import compare_database_summaries, inspect_database_set
from .test_profiles import PROFILE_NAMES, baseline_counts, run_test_profile
from .unified_memory import (
    CANONICAL_DATABASE_NAME,
    LEGACY_DATABASE_NAMES,
    UNIFIED_SCHEMA_VERSION,
    UnifiedImportResult,
    UnifiedMemoryDatabase,
)
from .typed_api import (
    MemoryCitation,
    MemoryLayer,
    RecallHit,
    RecallQuery,
    RecallResponse,
    RecallStatus,
    TypedMemoryAPI,
)
from .v16311_hardening import (
    EXTENDED_L0_SCHEMA_VERSION,
    HARDENING_VERSION,
    compare_chat_sources,
    list_chat_conversations,
)
from .v16311_hardening import apply as _apply_v16311_hardening
from .v16312_ci_hotfix import HOTFIX_VERSION
from .v16312_ci_hotfix import apply as _apply_v16312_ci_hotfix
from .v16325_hardening import HARDENING_VERSION as SOURCE_UNION_HARDENING_VERSION
from .v16325_hardening import apply as _apply_v16325_hardening

# Install versioned migrations only after the base modular components are
# imported. Operations are idempotent and do not touch user data until a store
# is explicitly initialized/imported.
_apply_v16311_hardening()
_apply_v16312_ci_hotfix()
_apply_v16325_hardening()

__all__ = [
    "BaselineSpec",
    "AdapterRegistry",
    "APP_VERSION",
    "CANONICAL_DATABASE_NAME",
    "EXPORT_SCHEMA",
    "EXTENDED_L0_SCHEMA_VERSION",
    "HARDENING_VERSION",
    "HOTFIX_VERSION",
    "HtmlImportResult",
    "LEGACY_DATABASE_NAMES",
    "MemoryRebuildAppController",
    "MemoryRebuildAppError",
    "MemoryRebuildSettings",
    "MemoryCitation",
    "MemoryLayer",
    "PIPELINES",
    "PROFILE_NAMES",
    "PROJECT_SCHEMA",
    "ProjectStore",
    "RebuildProject",
    "RecallHit",
    "RecallQuery",
    "RecallResponse",
    "RecallStatus",
    "SOURCE_ROLES",
    "SOURCE_UNION_HARDENING_VERSION",
    "SOURCE_UNION_SCHEMA",
    "SourceInspection",
    "SourceSpec",
    "TOOL_RELEASE_LABEL",
    "TOOL_REVISION",
    "TRUTH_DOMAINS",
    "TOOL_VERSION",
    "TypedMemoryAPI",
    "UNIFIED_SCHEMA_VERSION",
    "UnifiedImportResult",
    "UnifiedMemoryDatabase",
    "baseline_counts",
    "baseline_from_path",
    "build_source_union_manifest",
    "compare_chat_sources",
    "compare_database_summaries",
    "default_project_root",
    "default_adapter_registry",
    "discover_baseline_roots",
    "export_final_memory",
    "import_chat_html",
    "inspect_database_set",
    "inspect_source",
    "inspect_sources",
    "list_chat_conversations",
    "load_settings",
    "refresh_baseline",
    "run_source_union_analysis",
    "run_test_profile",
]
