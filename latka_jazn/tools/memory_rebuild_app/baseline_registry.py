from __future__ import annotations

from pathlib import Path
from typing import Iterable
import os

from .models import BaselineSpec
from .sqlite_inspector import DATABASE_FILENAMES, inspect_database_set, resolve_database_root


def _contains_database_set(path: Path) -> bool:
    root = resolve_database_root(path)
    return sum(1 for filename in DATABASE_FILENAMES.values() if (root / filename).is_file()) >= 3


def discover_baseline_roots(
    roots: Iterable[str | Path],
    *,
    max_depth: int = 4,
) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for value in roots:
        root = Path(value).expanduser().resolve()
        if not root.is_dir():
            continue
        candidates = [root]
        for current, directories, _files in os.walk(root):
            current_path = Path(current)
            try:
                depth = len(current_path.relative_to(root).parts)
            except ValueError:
                continue
            if depth >= max_depth:
                directories[:] = []
            candidates.append(current_path)
        for candidate in candidates:
            if not _contains_database_set(candidate):
                continue
            database_root = resolve_database_root(candidate)
            key = os.path.normcase(str(database_root))
            if key in seen:
                continue
            seen.add(key)
            found.append(database_root)
    return sorted(found, key=lambda path: str(path).casefold())


def baseline_from_path(
    value: str | Path,
    *,
    label: str | None = None,
    full_integrity: bool = False,
    calculate_sha256: bool = True,
) -> BaselineSpec:
    root = resolve_database_root(value)
    baseline = BaselineSpec.create(root, label=label)
    baseline.summary = inspect_database_set(
        root,
        full_integrity=full_integrity,
        calculate_sha256=calculate_sha256,
    )
    baseline.status = "ready" if baseline.summary.get("ok") else "needs_attention"
    return baseline


def refresh_baseline(
    baseline: BaselineSpec,
    *,
    full_integrity: bool = False,
    calculate_sha256: bool = True,
) -> BaselineSpec:
    baseline.summary = inspect_database_set(
        baseline.path,
        full_integrity=full_integrity,
        calculate_sha256=calculate_sha256,
    )
    baseline.status = "ready" if baseline.summary.get("ok") else "needs_attention"
    return baseline


__all__ = [
    "baseline_from_path",
    "discover_baseline_roots",
    "refresh_baseline",
]
