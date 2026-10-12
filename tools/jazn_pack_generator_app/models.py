from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ContentMode(StrEnum):
    SYSTEM = "system"
    MEMORY = "memory"
    SYSTEM_AND_MEMORY = "system+memory"


class TransportMode(StrEnum):
    SINGLE = "single"
    SPLIT = "split"


class UiMode(StrEnum):
    TEXT = "text"
    TUI = "tui"
    STUDIO = "studio"


@dataclass(frozen=True, slots=True)
class SourceEntry:
    source: Path
    archive_path: str
    size_bytes: int
    is_dir: bool = False


@dataclass(frozen=True, slots=True)
class PackRequest:
    source_root: Path
    output_root: Path
    content: ContentMode = ContentMode.SYSTEM
    memory_root: Path | None = None
    transport: TransportMode = TransportMode.SINGLE
    part_size_mib: int = 450
    compression_level: int = 6
    force_split: bool = False
    overwrite: bool = False


@dataclass(frozen=True, slots=True)
class PackPlan:
    request: PackRequest
    package_version: str
    package_basename: str
    entries: tuple[SourceEntry, ...]
    excluded: tuple[dict[str, str], ...]
    source_total_size_bytes: int

    @property
    def file_count(self) -> int:
        return sum(1 for item in self.entries if not item.is_dir)

    @property
    def directory_count(self) -> int:
        return sum(1 for item in self.entries if item.is_dir)

    def summary(self) -> dict[str, Any]:
        return {
            "content": self.request.content.value,
            "transport": self.request.transport.value,
            "source_root": str(self.request.source_root),
            "memory_root": str(self.request.memory_root) if self.request.memory_root else None,
            "output_root": str(self.request.output_root),
            "part_size_mib": self.request.part_size_mib,
            "compression_level": self.request.compression_level,
            "package_version": self.package_version,
            "package_basename": self.package_basename,
            "file_count": self.file_count,
            "directory_count": self.directory_count,
            "source_total_size_bytes": self.source_total_size_bytes,
            "excluded_count": len(self.excluded),
        }


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    stage: str
    message: str
    current: int = 0
    total: int = 0
    path: str | None = None

    @property
    def fraction(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(1.0, max(0.0, self.current / self.total))


@dataclass(frozen=True, slots=True)
class PackResult:
    ok: bool
    output_root: Path
    logical_archive: Path | None
    manifest_path: Path
    sha256_path: Path
    logical_sha256: str
    logical_size_bytes: int
    parts: tuple[Path, ...] = field(default_factory=tuple)
    parts_sha256_path: Path | None = None
    join_script_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "output_root": str(self.output_root),
            "logical_archive": str(self.logical_archive) if self.logical_archive else None,
            "manifest_path": str(self.manifest_path),
            "sha256_path": str(self.sha256_path),
            "logical_sha256": self.logical_sha256,
            "logical_size_bytes": self.logical_size_bytes,
            "parts": [str(item) for item in self.parts],
            "parts_sha256_path": str(self.parts_sha256_path) if self.parts_sha256_path else None,
            "join_script_path": str(self.join_script_path) if self.join_script_path else None,
        }


def jsonable_request(request: PackRequest) -> dict[str, Any]:
    raw = asdict(request)
    raw["source_root"] = str(request.source_root)
    raw["output_root"] = str(request.output_root)
    raw["memory_root"] = str(request.memory_root) if request.memory_root else None
    raw["content"] = request.content.value
    raw["transport"] = request.transport.value
    return raw
