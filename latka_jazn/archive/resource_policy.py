from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArchiveResourcePolicy:
    name: str
    max_members: int
    max_total_uncompressed_bytes: int
    max_member_uncompressed_bytes: int
    max_compression_ratio: float


SYSTEM_PACKAGE = ArchiveResourcePolicy("system_package", 20_000, 8 * 1024**3, 2 * 1024**3, 1_000.0)
MEMORY_PACKAGE_V3 = ArchiveResourcePolicy("memory_package_v3", 20_000, 8 * 1024**3, 2 * 1024**3, 1_000.0)
DEPENDENCY_ARTIFACT = ArchiveResourcePolicy("dependency_artifact", 20_000, 8 * 1024**3, 2 * 1024**3, 1_000.0)
LEGACY_MEMORY_REPACK_INPUT = ArchiveResourcePolicy("legacy_memory_repack_input", 200_000, 64 * 1024**3, 16 * 1024**3, 500.0)
GENERIC_ARCHIVE = ArchiveResourcePolicy("generic_archive", 200_000, 64 * 1024**3, 16 * 1024**3, 500.0)

POLICIES = {item.name: item for item in (
    SYSTEM_PACKAGE, MEMORY_PACKAGE_V3, DEPENDENCY_ARTIFACT,
    LEGACY_MEMORY_REPACK_INPUT, GENERIC_ARCHIVE,
)}
