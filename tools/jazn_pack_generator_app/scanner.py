from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
from typing import Callable

from .constants import EXCLUDED_DIR_NAMES, EXCLUDED_FILE_NAMES, EXCLUDED_FILE_SUFFIXES
from .errors import PackSafetyError, PackValidationError
from .models import ContentMode, PackPlan, PackRequest, SourceEntry


_MEMORY_TRANSIENT_DIRS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})
_MEMORY_TRANSIENT_SUFFIXES = EXCLUDED_FILE_SUFFIXES


def parse_package_version(source_root: Path) -> str:
    version_file = source_root / "latka_jazn" / "version.py"
    if not version_file.is_file():
        raise PackValidationError(f"Brak kanonicznego pliku wersji Jaźni: {version_file}")
    text = version_file.read_text(encoding="utf-8")
    version_match = re.search(r"^PACKAGE_VERSION\s*=\s*(['\"])(.*?)\1", text, re.MULTILINE)
    release_match = re.search(r"^PACKAGE_RELEASE_NAME\s*=\s*(['\"])(.*?)\1", text, re.MULTILINE)
    if not version_match:
        raise PackValidationError(f"Nie znaleziono PACKAGE_VERSION w {version_file}")
    version = version_match.group(2).strip()
    release = release_match.group(2).strip() if release_match else ""
    return f"{version}-{release}" if release else version


def resolve_memory_root(source_root: Path, explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env_value = str(os.environ.get("JAZN_MEMORY_ROOT") or "").strip()
    if env_value:
        candidates.append(Path(env_value))
    # Bounded compatibility path. The runtime itself owns more advanced
    # host-level resolution; the archiver does not guess outside these roots.
    candidates.append(source_root / "memory")
    for candidate in candidates:
        path = candidate.expanduser().resolve()
        if path.is_dir():
            return path
    rendered = ", ".join(str(item) for item in candidates)
    raise PackValidationError(
        "Nie znaleziono pamięci Jaźni. Wskaż --memory-root albo ustaw JAZN_MEMORY_ROOT. "
        f"Sprawdzone: {rendered}"
    )


def _is_system_excluded(relative: PurePosixPath, name: str, is_dir: bool) -> str | None:
    relative_text = relative.as_posix()
    if is_dir:
        if name in EXCLUDED_DIR_NAMES:
            return f"system-dir:{name}"
        if len(relative.parts) == 1 and name.casefold() == "memory":
            return "system-memory-boundary"
        if relative_text.casefold() == "latka_jazn/local_resources":
            return "system-managed-local-resources"
        return None
    if name in EXCLUDED_FILE_NAMES:
        return f"system-file:{name}"
    lower = name.casefold()
    if relative_text.casefold() == "latka_jazn/core/canon/local_private_canon_extension.py":
        return "system-private-canon-extension"
    if lower.endswith((".sqlite3", ".sqlite", ".db")):
        return "system-private-database"
    if lower.endswith(EXCLUDED_FILE_SUFFIXES):
        return "system-transient-suffix"
    if lower.endswith(".log"):
        return "system-log"
    if lower.endswith(".zip") or re.search(r"\.zip\.\d{3}$", lower):
        return "generated-package"
    return None


def _is_memory_excluded(_relative: PurePosixPath, name: str, is_dir: bool) -> str | None:
    if is_dir and name in _MEMORY_TRANSIENT_DIRS:
        return f"memory-cache:{name}"
    if not is_dir:
        lower = name.casefold()
        if name in EXCLUDED_FILE_NAMES:
            return f"memory-file:{name}"
        if lower.endswith(_MEMORY_TRANSIENT_SUFFIXES):
            return "memory-transient-suffix"
    return None


def _scan_tree(
    root: Path,
    *,
    archive_prefix: str,
    exclude: Callable[[PurePosixPath, str, bool], str | None],
) -> tuple[list[SourceEntry], list[dict[str, str]]]:
    entries: list[SourceEntry] = []
    excluded: list[dict[str, str]] = []
    root = root.resolve()

    def visit(directory: Path, relative_dir: PurePosixPath) -> None:
        try:
            items = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise PackValidationError(f"Nie można odczytać katalogu {directory}: {exc}") from exc

        for item in items:
            rel = relative_dir / item.name
            arc_rel = PurePosixPath(archive_prefix) / rel if archive_prefix else rel
            try:
                item_path = Path(item.path)
                is_junction = bool(
                    getattr(os.path, "isjunction", lambda _value: False)(item.path)
                )
                if item.is_symlink() or is_junction:
                    raise PackSafetyError(
                        f"Symlink/junction nie jest pakowany automatycznie: {item.path}"
                    )
                is_dir = item.is_dir(follow_symlinks=False)
                reason = exclude(rel, item.name, is_dir)
                if reason:
                    excluded.append({"path": str(rel), "reason": reason})
                    continue
                if is_dir:
                    entries.append(SourceEntry(Path(item.path), arc_rel.as_posix() + "/", 0, True))
                    visit(Path(item.path), rel)
                elif item.is_file(follow_symlinks=False):
                    stat_result = item.stat(follow_symlinks=False)
                    entries.append(
                        SourceEntry(
                            source=Path(item.path),
                            archive_path=arc_rel.as_posix(),
                            size_bytes=int(stat_result.st_size),
                            is_dir=False,
                        )
                    )
                else:
                    raise PackSafetyError(f"Nieobsługiwany typ wpisu systemu plików: {item.path}")
            except OSError as exc:
                raise PackValidationError(f"Nie można sprawdzić {item.path}: {exc}") from exc

    visit(root, PurePosixPath())
    return entries, excluded


def build_pack_plan(request: PackRequest) -> PackPlan:
    source_root = request.source_root.expanduser().resolve()
    output_root = request.output_root.expanduser().resolve()
    if not source_root.is_dir():
        raise PackValidationError(f"Folder Jaźni nie istnieje: {source_root}")
    if request.part_size_mib <= 0:
        raise PackValidationError("Rozmiar części musi być większy od zera.")
    if not 0 <= request.compression_level <= 9:
        raise PackValidationError("Poziom kompresji ZIP musi mieścić się w zakresie 0..9.")

    entries: list[SourceEntry] = []
    excluded: list[dict[str, str]] = []
    memory_root: Path | None = None

    if request.content in {ContentMode.SYSTEM, ContentMode.SYSTEM_AND_MEMORY}:
        system_entries, system_excluded = _scan_tree(
            source_root, archive_prefix="", exclude=_is_system_excluded
        )
        entries.extend(system_entries)
        excluded.extend(system_excluded)

    if request.content in {ContentMode.MEMORY, ContentMode.SYSTEM_AND_MEMORY}:
        memory_root = resolve_memory_root(source_root, request.memory_root)
        memory_entries, memory_excluded = _scan_tree(
            memory_root, archive_prefix="memory", exclude=_is_memory_excluded
        )
        entries.extend(memory_entries)
        excluded.extend(
            {"path": f"memory/{item['path']}", "reason": item["reason"]} for item in memory_excluded
        )

    # Case-insensitive collisions are rejected because archives are commonly moved
    # between Windows and Linux.
    seen: dict[str, str] = {}
    for entry in entries:
        normalized = entry.archive_path.rstrip("/")
        key = normalized.casefold()
        previous = seen.get(key)
        if previous is not None and previous != normalized:
            raise PackSafetyError(
                f"Kolizja nazw archiwum bez rozróżnienia wielkości liter: {previous!r} vs {normalized!r}"
            )
        seen[key] = normalized

    package_version = parse_package_version(source_root)
    content_slug = request.content.value.replace("+", "+")
    package_basename = f"jazn_latka_v{package_version}.{content_slug}.zip"
    normalized_request = PackRequest(
        source_root=source_root,
        output_root=output_root,
        content=request.content,
        memory_root=memory_root,
        transport=request.transport,
        part_size_mib=request.part_size_mib,
        compression_level=request.compression_level,
        force_split=request.force_split,
        overwrite=request.overwrite,
    )
    return PackPlan(
        request=normalized_request,
        package_version=package_version,
        package_basename=package_basename,
        entries=tuple(entries),
        excluded=tuple(excluded),
        source_total_size_bytes=sum(item.size_bytes for item in entries if not item.is_dir),
    )
