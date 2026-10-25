from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable
import os

SUPPORTED_SOURCE_SUFFIXES = {
    ".zip",
    ".json",
    ".jsonl",
    ".ndjson",
    ".html",
    ".htm",
    ".txt",
    ".md",
    ".pdf",
    ".docx",
    ".odt",
    ".rtf",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".svg",
}

_SKIPPED_DIRECTORY_NAMES = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}


def human_size(value: int | float | None) -> str:
    size = float(value or 0)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{int(value or 0)} B"


def discover_source_files(
    root: str | Path,
    *,
    recursive: bool = True,
    max_depth: int = 16,
) -> list[Path]:
    """Discover supported source files. Dot-prefixed folders are intentionally included."""

    source_root = Path(root).expanduser().resolve()
    if not source_root.is_dir():
        raise NotADirectoryError(source_root)

    found: list[Path] = []
    if not recursive:
        iterator: Iterable[Path] = source_root.iterdir()
        for path in iterator:
            if path.is_file() and path.suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES:
                found.append(path.resolve())
        return sorted(found, key=lambda item: item.name.casefold())

    for current, directories, filenames in os.walk(source_root):
        current_path = Path(current)
        try:
            depth = len(current_path.relative_to(source_root).parts)
        except ValueError:
            continue
        directories[:] = [name for name in directories if name not in _SKIPPED_DIRECTORY_NAMES]
        if depth >= max(0, int(max_depth)):
            directories[:] = []
        for filename in filenames:
            path = current_path / filename
            if path.suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES:
                found.append(path.resolve())

    return sorted(found, key=lambda item: str(item.relative_to(source_root)).casefold())


def format_discovered_files(
    root: str | Path,
    files: Iterable[str | Path],
    *,
    max_items: int = 120,
) -> str:
    source_root = Path(root).expanduser().resolve()
    paths = [Path(item).expanduser().resolve() for item in files]
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        try:
            relative = path.relative_to(source_root)
            folder = str(relative.parent) if str(relative.parent) != "." else "(główny folder)"
        except ValueError:
            folder = str(path.parent)
        grouped[folder].append(path)

    lines = [
        f"Folder: {source_root}",
        f"Znalezione pliki: {len(paths)}",
        "",
    ]
    shown = 0
    for folder in sorted(grouped, key=str.casefold):
        lines.append(f"[{folder}]")
        for path in sorted(grouped[folder], key=lambda item: item.name.casefold()):
            if shown >= max_items:
                break
            size = human_size(path.stat().st_size if path.is_file() else 0)
            lines.append(f"  • {path.name}  ({size})")
            shown += 1
        if shown >= max_items:
            break
        lines.append("")
    if len(paths) > shown:
        lines.append(f"… oraz jeszcze {len(paths) - shown} plików.")
    return "\n".join(lines).rstrip()


__all__ = [
    "SUPPORTED_SOURCE_SUFFIXES",
    "discover_source_files",
    "format_discovered_files",
    "human_size",
]
