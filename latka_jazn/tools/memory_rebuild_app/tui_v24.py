from __future__ import annotations

"""Compatibility entrypoint for the single canonical Memory Rebuild Studio.

The public ``run_studio_v24`` name remains available for CLI/API compatibility,
but it no longer owns a menu and never starts the retired Memory Rebuild UI.
"""

from pathlib import Path
import os

from .project_store import ProjectStore
from .settings import load_tool_settings, resolve_settings_path
from .studio import run_studio
from .unified_memory import CANONICAL_DATABASE_NAME


def _default_database(project_root: str | Path | None, project: str | None) -> Path:
    if project:
        try:
            loaded = ProjectStore(project_root).load(project)
            configured = str(loaded.settings.get("unified_database_path") or "").strip()
            if configured:
                return Path(configured).expanduser().resolve()
            if loaded.target_root:
                return (Path(loaded.target_root).expanduser().resolve() / CANONICAL_DATABASE_NAME).resolve()
        except Exception:
            pass
    env = os.getenv("JAZN_MEMORY_DATABASE", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".jazn" / CANONICAL_DATABASE_NAME).resolve()


def run_studio_v24(
    *,
    project_root: str | Path | None = None,
    project: str | None = None,
    tool_root: str | Path | None = None,
    text_ui: bool = False,
    settings_path: str | Path | None = None,
) -> int:
    root = Path(tool_root or Path.cwd()).expanduser().resolve()
    database = _default_database(project_root, project)
    resolved_settings = resolve_settings_path(settings_path, tool_root=root)
    load_tool_settings(resolved_settings, tool_root=root, create=True)
    return run_studio(
        database=database,
        project_root=project_root,
        project=project,
        tool_root=root,
        settings_path=resolved_settings,
        text_ui=text_ui,
    )


__all__ = ["run_studio_v24"]
