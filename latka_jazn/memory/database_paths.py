from __future__ import annotations

"""Read-only discovery of SQLite directories in historical MEMORY layouts."""

from pathlib import Path, PureWindowsPath
from typing import Literal, Sequence


def resolve_sqlite_directory(
    value: str | Path,
    *,
    database_filenames: Sequence[str],
    missing_layout: Literal["directory", "system"] = "directory",
) -> Path:
    """Resolve an existing set, preserving the caller's missing-path contract.

    An explicit database or sqlite directory identifies its containing directory.
    Existing sets can live directly in the input, under sqlite, or under
    memory/sqlite. Missing arbitrary directories are ambiguous: inspectors keep
    them unchanged, while historical restore callers expect SYSTEM/memory/sqlite.
    A directory explicitly named memory or sqlite supplies that missing role.
    No files or directories are created, and database names are not schema proof.
    """

    raw = str(value)
    parts = raw.replace("\\", "/").split("/")
    if ".." in parts:
        raise ValueError(f"database path contains traversal: {value}")
    named_parts = [part.casefold() for part in parts if part not in {"", "."}]
    if any(left == right == "memory" for left, right in zip(named_parts, named_parts[1:])):
        raise ValueError(f"database path has duplicated memory prefix: {value}")
    windows = PureWindowsPath(raw)
    if windows.drive and not windows.is_absolute():
        raise ValueError(f"database path is drive-relative: {value}")
    if windows.is_absolute() and not Path(raw).is_absolute():
        raise ValueError(f"database path belongs to a different host platform: {value}")
    if missing_layout not in {"directory", "system"}:
        raise ValueError(f"unsupported missing database layout: {missing_layout}")
    root = Path(value).expanduser().resolve()
    if root.is_file():
        if root.suffix.casefold() not in {".sqlite", ".sqlite3", ".db"}:
            raise ValueError(f"database path is not a SQLite file: {value}")
        return root.parent
    if root.suffix.casefold() in {".sqlite", ".sqlite3", ".db"} and not root.exists():
        return root.parent
    if root.name.casefold() == "sqlite":
        return root
    candidates = [root, root / "sqlite"]
    if root.name.casefold() != "memory":
        candidates.append(root / "memory" / "sqlite")
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"database directory escapes selected root: {candidate}") from exc
        if any((resolved / name).is_file() for name in database_filenames):
            return resolved
    if root.name.casefold() == "memory":
        return root / "sqlite"
    return root / "memory" / "sqlite" if missing_layout == "system" else root


__all__ = ["resolve_sqlite_directory"]
