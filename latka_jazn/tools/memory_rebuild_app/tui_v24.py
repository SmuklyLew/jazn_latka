from __future__ import annotations

"""Compatibility entrypoint for the canonical Memory Rebuild interactive shell.

The public ``run_studio_v24`` name remains available for CLI/API compatibility.
Text and TUI now share the same application shell contract as the window mode:
home, operations, settings and diagnostics over the canonical Memory Rebuild CLI.
"""

from pathlib import Path
import os

from latka_jazn.tools.application_shell import build_diagnostics, run_text_studio, run_tui_studio

from .project_store import ProjectStore
from .settings import load_tool_settings, resolve_settings_path
from .ui_window import build_studio_spec
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
    resolved_settings = resolve_settings_path(settings_path, tool_root=root)
    load_tool_settings(resolved_settings, tool_root=root, create=True)
    spec = build_studio_spec(tool_root=root)
    diagnostics = build_diagnostics(spec)
    diagnostics.record(
        "INFO",
        "Uruchomiono Memory Rebuild interaktywnie",
        mode="text" if text_ui else "tui",
        project_root=str(project_root) if project_root else None,
        project=project,
        database=str(_default_database(project_root, project)),
    )
    return run_text_studio(spec, diagnostics) if text_ui else run_tui_studio(spec, diagnostics)


__all__ = ["run_studio_v24"]
