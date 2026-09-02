from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath, PureWindowsPath
import re
import stat
import unicodedata
from typing import Any, Iterable

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ArchiveResourcePolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArchiveResourcePolicy:
    max_members: int = 200_000
    max_total_uncompressed_bytes: int = 64 * 1024 * 1024 * 1024
    max_member_bytes: int = 16 * 1024 * 1024 * 1024
    max_compression_ratio: float = 500.0
    max_name_length: int = 1024
    require_free_space: bool = True
    reject_symlinks: bool = True
    reject_special_files: bool = True
    reject_casefold_collisions: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_member_path(value: str, *, normalize_backslash: bool = True) -> str:
    raw = str(value or "")
    if normalize_backslash:
        raw = raw.replace("\\", "/")
    elif "\\" in raw:
        raise ArchiveResourcePolicyError(f"unsafe_archive_member:alternate_separator:{value}")
    if not raw or "\x00" in raw:
        raise ArchiveResourcePolicyError("unsafe_archive_member:empty_or_nul")
    if raw.startswith("/") or raw.startswith("//") or _DRIVE_PREFIX.match(raw):
        raise ArchiveResourcePolicyError(f"unsafe_archive_member:absolute:{value}")
    windows = PureWindowsPath(raw)
    if windows.is_absolute() or windows.drive or windows.root:
        raise ArchiveResourcePolicyError(f"unsafe_archive_member:absolute:{value}")
    raw = raw.rstrip("/")
    parts = PurePosixPath(raw).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArchiveResourcePolicyError(f"unsafe_archive_member:traversal:{value}")
    clean: list[str] = []
    for part in parts:
        if part.endswith(" ") or part.endswith("."):
            raise ArchiveResourcePolicyError(f"unsafe_archive_member:windows_normalization:{value}")
        if ":" in part:
            raise ArchiveResourcePolicyError(f"unsafe_archive_member:alternate_data_stream:{value}")
        stem = part.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED:
            raise ArchiveResourcePolicyError(f"unsafe_archive_member:windows_reserved:{value}")
        clean.append(part)
    return PurePosixPath(*clean).as_posix()


def member_collision_key(name: str) -> str:
    return unicodedata.normalize("NFC", str(name)).casefold()


def zip_member_kind(info: Any) -> tuple[bool, bool, bool]:
    mode = (int(getattr(info, "external_attr", 0)) >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode) if mode else 0
    is_dir = bool(getattr(info, "is_dir", lambda: False)())
    is_symlink = file_type == stat.S_IFLNK
    is_regular = bool(is_dir or file_type in {0, stat.S_IFREG, stat.S_IFDIR}) and not is_symlink
    return is_dir, is_symlink, is_regular


def validate_member_inventory(entries: Iterable[Any], *, policy: ArchiveResourcePolicy | None = None) -> dict[str, Any]:
    active = policy or ArchiveResourcePolicy()
    rows = list(entries)
    if len(rows) > active.max_members:
        raise ArchiveResourcePolicyError(f"archive_member_limit_exceeded:{len(rows)}>{active.max_members}")
    exact: set[str] = set()
    folded: set[str] = set()
    total = 0
    highest_ratio = 0.0
    for entry in rows:
        raw_name = str(getattr(entry, "filename", getattr(entry, "name", "")))
        name = normalize_member_path(raw_name)
        if len(name) > active.max_name_length:
            raise ArchiveResourcePolicyError(f"archive_member_name_too_long:{name[:120]}")
        if name in exact:
            raise ArchiveResourcePolicyError(f"duplicate_archive_member:{name}")
        exact.add(name)
        folded_key = member_collision_key(name)
        if active.reject_casefold_collisions and folded_key in folded:
            raise ArchiveResourcePolicyError(f"casefold_archive_member_collision:{name}")
        folded.add(folded_key)
        is_dir = bool(getattr(entry, "is_dir", False))
        if callable(getattr(entry, "is_dir", None)):
            is_dir, is_symlink, is_regular = zip_member_kind(entry)
        else:
            is_symlink = bool(getattr(entry, "is_symlink", False))
            is_regular = bool(getattr(entry, "is_regular_file", True))
        if active.reject_symlinks and is_symlink:
            raise ArchiveResourcePolicyError(f"archive_symlink_rejected:{name}")
        if active.reject_special_files and not is_dir and not is_regular:
            raise ArchiveResourcePolicyError(f"archive_special_file_rejected:{name}")
        if is_dir:
            continue
        size = int(getattr(entry, "file_size", getattr(entry, "size_bytes", 0)))
        compressed_raw = getattr(entry, "compress_size", getattr(entry, "compressed_size_bytes", None))
        compressed = int(compressed_raw) if compressed_raw is not None else None
        if size < 0 or size > active.max_member_bytes:
            raise ArchiveResourcePolicyError(f"archive_member_size_limit_exceeded:{name}:{size}>{active.max_member_bytes}")
        total += size
        if total > active.max_total_uncompressed_bytes:
            raise ArchiveResourcePolicyError(f"archive_total_size_limit_exceeded:{total}>{active.max_total_uncompressed_bytes}")
        if compressed is not None and size > 0:
            ratio = float("inf") if compressed == 0 else size / compressed
            highest_ratio = max(highest_ratio, ratio)
            if ratio > active.max_compression_ratio:
                raise ArchiveResourcePolicyError(f"archive_compression_ratio_limit_exceeded:{name}:{ratio:.2f}>{active.max_compression_ratio:.2f}")
    return {
        "member_count": len(rows),
        "total_uncompressed_bytes": total,
        "highest_compression_ratio": highest_ratio,
        "policy": active.to_dict(),
    }
