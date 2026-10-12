"""Mutable operator state, separated from SYSTEM and runtime-owned data.

Resolution never creates directories or migrates legacy files. Callers may read
old settings but all new writes must use the returned destination.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

from latka_jazn.core.runtime_root import default_runtime_workspace_path, workspace_runtime_path


class OperatorPathError(ValueError):
    """An operator destination overlaps protected data or escapes its state root."""


def _within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def validate_operator_path(path: str | Path, system_root: Path, *, directory: bool = False,
                           allow_memory_settings: bool = False) -> Path:
    """Validate an explicit path after resolving symlinks and Windows junctions."""
    raw = Path(path).expanduser()
    if not raw.is_absolute() or ".." in raw.parts:
        raise OperatorPathError("Ścieżka stanu operatora musi być absolutna i nie może zawierać '..'.")
    target = raw.resolve()
    system = Path(system_root).expanduser().resolve()
    workspaces = (default_runtime_workspace_path(system).resolve(), workspace_runtime_path(system).resolve())
    protected = [system, system.parent / "memory", *(workspace / "memory" for workspace in workspaces)]
    for workspace in workspaces:
        allowed = {workspace / "memory_rebuild_settings.json", workspace / "memory_rebuild_settings.json.tmp"}
        if not (allow_memory_settings and not directory and raw.absolute() in allowed and target == raw.absolute()):
            protected.append(workspace)
    memory = os.environ.get("JAZN_MEMORY_ROOT", "").strip()
    if memory:
        candidate = Path(memory).expanduser()
        protected.append(candidate if candidate.is_absolute() else workspace_runtime_path(system) / candidate)
    for root in protected:
        if _within(target, root.resolve()):
            raise OperatorPathError(f"Stan operatora nie może być zapisany w SYSTEM, MEMORY lub workspace runtime: {target}")
    if target.exists() and (not target.is_dir() if directory else not target.is_file()):
        raise OperatorPathError(f"Nieprawidłowy typ ścieżki stanu operatora: {target}")
    for parent in target.parents:
        if parent.exists() and not parent.is_dir():
            raise OperatorPathError(f"Rodzic ścieżki nie jest katalogiem: {parent}")
    return target


def operator_state_dir(app_id: str, system_root: Path, *, per_system: bool = False) -> Path:
    """Return ~/.jazn/tools/<app>, or a validated JAZN_OPERATOR_STATE_ROOT.

    Per-system state is keyed by the resolved, platform-normalized SYSTEM path.
    This avoids mixing reviews from separate checkouts while remaining stable
    across commits. No directory is created by discovery.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", app_id):
        raise OperatorPathError(f"Nieprawidłowy identyfikator aplikacji: {app_id}")
    raw = os.environ.get("JAZN_OPERATOR_STATE_ROOT", "").strip()
    base = validate_operator_path(raw or Path.home() / ".jazn" / "tools", system_root, directory=True)
    target = base / app_id
    if per_system:
        identity = os.path.normcase(str(Path(system_root).expanduser().resolve()))
        target = target / hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    resolved = validate_operator_path(target, system_root, directory=True)
    if not _within(resolved, base):
        raise OperatorPathError(f"Symlink lub junction wyprowadza stan poza katalog operatora: {target}")
    # Validate known writable descendants too: a safe app directory may still
    # contain a redirected log or pytest cache directory.
    for child in (resolved / "runtime", resolved / "pytest_cache"):
        checked = validate_operator_path(child, system_root, directory=True)
        if not _within(checked, resolved):
            raise OperatorPathError(f"Podkatalog stanu wyprowadza poza katalog aplikacji: {child}")
    log = validate_operator_path(resolved / "runtime" / f"{app_id}.jsonl", system_root)
    if not _within(log, resolved):
        raise OperatorPathError(f"Log wyprowadza poza katalog aplikacji: {log}")
    return resolved


def operator_file(app_id: str, system_root: Path, filename: str, *, per_system: bool = False) -> Path:
    """Resolve a simple filename, rejecting a redirected leaf as well as parents."""
    if not filename or Path(filename).name != filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise OperatorPathError("Nazwa pliku stanu musi być pojedynczym komponentem.")
    base = operator_state_dir(app_id, system_root, per_system=per_system)
    target = validate_operator_path(base / filename, system_root)
    if not _within(target, base):
        raise OperatorPathError(f"Plik stanu wyprowadza poza katalog operatora: {target}")
    # The current shell and review writers use these atomic-write sidecars.
    for temporary in (base / (filename + ".tmp"), (base / filename).with_suffix(".tmp")):
        checked = validate_operator_path(temporary, system_root)
        if not _within(checked, base):
            raise OperatorPathError(f"Plik tymczasowy wyprowadza poza katalog aplikacji: {temporary}")
    return target


def legacy_read_path(destination: Path, legacy: Path) -> Path:
    """A legacy file is a read-only fallback; never copy, delete or rewrite it."""
    return destination if destination.exists() or not legacy.is_file() else legacy
