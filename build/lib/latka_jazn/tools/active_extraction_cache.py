from __future__ import annotations

"""v16 activation adapter for the single canonical runtime workspace.

The v15 implementation remains byte-for-byte available in
``_active_extraction_cache_impl``.  Public API is re-exported here, while marker
writes first migrate any historical per-version ``workspace_runtime`` into the
host-level singleton.  This keeps bootstrap, daemon startup and memory attach on
one activation contract without duplicating their callers.
"""

from pathlib import Path
from typing import Any

from latka_jazn.core.runtime_root import migrate_legacy_runtime_workspace
from latka_jazn.tools import _active_extraction_cache_impl as _impl
from latka_jazn.tools._active_extraction_cache_impl import *  # noqa: F401,F403


def write_active_runtime_marker(
    root: Path,
    *,
    source_zip: Path | None = None,
    marker_output: Path | None = None,
    action: str = "reuse_existing_unpacked_folder",
) -> dict[str, Any]:
    """Migrate legacy mutable state, then publish the singleton active marker."""

    migration = migrate_legacy_runtime_workspace(Path(root))
    marker = _impl.write_active_runtime_marker(
        root,
        source_zip=source_zip,
        marker_output=marker_output,
        action=action,
    )
    marker["runtime_workspace_migration"] = migration
    marker["single_canonical_runtime_workspace"] = True
    return marker
