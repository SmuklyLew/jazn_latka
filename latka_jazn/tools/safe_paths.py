from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable
import os
import unicodedata


class UnsafeRelativePathError(ValueError):
    """Raised when an untrusted package/archive path is not safely relative."""


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
    "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³",
}


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
    """Return canonical POSIX relative path or fail closed on the raw input.

    This is the single lexical boundary for manifests, package-set sidecars,
    archive members and memory transport paths.  It intentionally validates
    *before* any cleanup/sanitization so an unsafe spelling cannot become safe
    merely by stripping `./`, whitespace or alternate separators.
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
    for part in parts:
        if any(ord(ch) < 32 for ch in part):
            raise UnsafeRelativePathError("control character in path component is forbidden")
        if ":" in part:
            raise UnsafeRelativePathError("drive or alternate data stream syntax is forbidden")
        if part.endswith((" ", ".")):
            raise UnsafeRelativePathError("Windows-trimmed trailing space or period is forbidden")
        stem = part.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED:
            raise UnsafeRelativePathError(f"Windows reserved device name is forbidden: {part}")
    return "/".join(parts)


def portable_path_key(relative: str) -> str:
    canonical = validate_safe_relative_path(relative)
    return unicodedata.normalize("NFC", canonical).casefold()


def validate_safe_path_set(paths: Iterable[str]) -> tuple[str, ...]:
    """Validate a complete cross-platform path inventory and reject collisions."""
    exact: set[str] = set()
    folded: dict[str, str] = {}
    result: list[str] = []
    for raw in paths:
        canonical = validate_safe_relative_path(str(raw))
        if canonical in exact:
            raise UnsafeRelativePathError(f"duplicate path is forbidden: {canonical}")
        key = portable_path_key(canonical)
        previous = folded.get(key)
        if previous is not None and previous != canonical:
            raise UnsafeRelativePathError(
                f"portable case/Unicode path collision is forbidden: {previous!r} vs {canonical!r}"
            )
        exact.add(canonical)
        folded[key] = canonical
        result.append(canonical)
    return tuple(result)


def resolve_safe_path(
    root: Path | str,
    relative: str,
    *,
    must_exist: bool = False,
    must_be_file: bool = False,
) -> Path:
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
