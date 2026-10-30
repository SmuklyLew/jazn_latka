"""Local operator configuration owned by one verified SYSTEM/worktree root.

Path discovery is read-only; no implicit migration or daemon lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalSettingsLayout:
    system: Path
    versioned: Path
    local: Path
    operator: Path
    acceptance: Path


def _redirected(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def local_settings_enabled(system_root: Path) -> bool:
    root = Path(system_root).expanduser().resolve()
    return (root / ".settings").is_dir()


def verify_local_descendant(path: Path, layout: LocalSettingsLayout) -> Path:
    raw = Path(path).expanduser().absolute()
    if ".." in Path(path).parts or not raw.is_relative_to(layout.local):
        raise ValueError("Local settings path escapes its owned root")
    current = layout.local
    if _redirected(current):
        raise ValueError("Local settings root cannot be a link or junction")
    for part in raw.relative_to(layout.local).parts:
        current = current / part
        if _redirected(current):
            raise ValueError("Local settings descendant is redirected")
    # Compare canonical paths on both sides. On Windows an already-created
    # descendant may be resolved through a physical volume/mount spelling
    # while its parent was constructed lexically during concurrent creation.
    # The redirect checks above still reject links/junctions on every
    # descendant; comparing an unresolved parent is not a security boundary.
    resolved_root = layout.local.resolve()
    resolved = raw.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("Local settings path resolves outside its root")
    return resolved


def resolve_local_settings_layout(system_root: Path) -> LocalSettingsLayout:
    system = Path(system_root).expanduser().resolve()
    versioned = system / ".settings"
    local = system / ".settings_local"
    if not versioned.is_dir() or _redirected(versioned):
        raise ValueError("Missing or redirected versioned settings")
    if _redirected(local):
        raise ValueError("Local settings root cannot be redirected")
    layout = LocalSettingsLayout(
        system=system,
        versioned=versioned,
        local=local,
        operator=local / "operator",
        acceptance=local / "acceptance",
    )
    verify_local_descendant(layout.operator, layout)
    verify_local_descendant(layout.acceptance, layout)
    return layout
