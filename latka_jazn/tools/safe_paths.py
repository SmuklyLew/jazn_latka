from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
import os


class UnsafeRelativePathError(ValueError):
    """Raised when an untrusted package/archive path is not safely relative."""


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0) or 0)
        return bool(attributes & int(getattr(os, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))
    except OSError:
        return False


def validate_safe_relative_path(relative: str) -> str:
    """Return the canonical POSIX relative path or fail closed.

    Manifest and archive paths are a cross-platform protocol, so only ``/`` is
    accepted as a separator.  This prevents a path that is lexical data on one
    platform from becoming traversal or an absolute path on another.
    """

    if not isinstance(relative, str):
        raise UnsafeRelativePathError("path must be a string")
    if not relative or not relative.strip():
        raise UnsafeRelativePathError("empty path is forbidden")
    if relative != relative.strip():
        raise UnsafeRelativePathError("leading or trailing whitespace is forbidden")
    if "\x00" in relative:
        raise UnsafeRelativePathError("NUL byte is forbidden")
    if "\\" in relative:
        raise UnsafeRelativePathError("alternate path separators are forbidden")

    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root:
        raise UnsafeRelativePathError("absolute, drive, or UNC path is forbidden")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise UnsafeRelativePathError("empty, dot, or parent segments are forbidden")
    if any(":" in part for part in parts):
        raise UnsafeRelativePathError("drive or alternate data stream syntax is forbidden")
    return "/".join(parts)


def resolve_safe_path(
    root: Path | str,
    relative: str,
    *,
    must_exist: bool = False,
    must_be_file: bool = False,
) -> Path:
    """Resolve an untrusted relative path and prove containment under ``root``."""

    canonical = validate_safe_relative_path(relative)
    root_resolved = Path(root).expanduser().resolve()
    candidate = root_resolved.joinpath(*canonical.split("/"))
    resolved = candidate.resolve(strict=False)
    if not _within(resolved, root_resolved):
        raise UnsafeRelativePathError("resolved path escapes root")

    current = root_resolved
    for part in canonical.split("/"):
        current = current / part
        if (current.exists() or current.is_symlink()) and _is_reparse_point(current):
            target = current.resolve(strict=False)
            if not _within(target, root_resolved):
                raise UnsafeRelativePathError("symlink or reparse point escapes root")

    if must_exist and not resolved.exists():
        raise UnsafeRelativePathError("path does not exist")
    if must_be_file and not resolved.is_file():
        raise UnsafeRelativePathError("path is not a regular file")
    return resolved


def resolve_safe_source(root: Path | str, relative: str) -> Path:
    return resolve_safe_path(root, relative, must_exist=True, must_be_file=True)


def resolve_safe_destination(root: Path | str, relative: str) -> Path:
    return resolve_safe_path(root, relative)
