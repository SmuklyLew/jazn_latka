from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import zipfile

from latka_jazn.archive.resource_policy import (
    ArchiveResourcePolicy, ArchiveResourcePolicyError, validate_member_inventory,
)


class ZipResourceLimitError(ValueError):
    pass


DEFAULT_MAX_MEMBERS = 20_000
DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES = 8 * 1024**3
DEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES = 2 * 1024**3
DEFAULT_MAX_COMPRESSION_RATIO = 1_000.0


@dataclass(frozen=True, slots=True)
class ZipResourceLimits:
    max_members: int = DEFAULT_MAX_MEMBERS
    max_total_uncompressed_bytes: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES
    max_member_uncompressed_bytes: int = DEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO

    @classmethod
    def from_env(cls) -> "ZipResourceLimits":
        return cls(
            max_members=int(os.environ.get("JAZN_ZIP_MAX_MEMBERS", DEFAULT_MAX_MEMBERS)),
            max_total_uncompressed_bytes=int(
                os.environ.get("JAZN_ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES", DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES)
            ),
            max_member_uncompressed_bytes=int(
                os.environ.get("JAZN_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES", DEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES)
            ),
            max_compression_ratio=float(
                os.environ.get("JAZN_ZIP_MAX_COMPRESSION_RATIO", DEFAULT_MAX_COMPRESSION_RATIO)
            ),
        )

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def validate_zip_resources(
    archive: zipfile.ZipFile,
    *,
    limits: ZipResourceLimits | None = None,
) -> dict[str, int | float]:
    active = limits or ZipResourceLimits.from_env()
    infos = archive.infolist()
    try:
        validate_member_inventory(
            infos,
            policy=ArchiveResourcePolicy(
                max_members=active.max_members,
                max_total_uncompressed_bytes=active.max_total_uncompressed_bytes,
                max_member_bytes=active.max_member_uncompressed_bytes,
                max_compression_ratio=active.max_compression_ratio,
            ),
        )
    except ArchiveResourcePolicyError as exc:
        # Preserve the established ZIP-specific error contract for callers
        # while the shared policy engine uses archive-generic diagnostics.
        message = str(exc)
        legacy_prefixes = {
            "archive_member_limit_exceeded:": "zip_member_limit_exceeded:",
            "archive_member_size_limit_exceeded:": "zip_member_size_limit_exceeded:",
            "archive_total_size_limit_exceeded:": "zip_total_size_limit_exceeded:",
            "archive_compression_ratio_limit_exceeded:": "zip_compression_ratio_limit_exceeded:",
        }
        for current, legacy in legacy_prefixes.items():
            if message.startswith(current):
                message = legacy + message[len(current):]
                break
        raise ZipResourceLimitError(message) from exc
    if len(infos) > active.max_members:
        raise ZipResourceLimitError(
            f"zip_member_limit_exceeded:{len(infos)}>{active.max_members}"
        )

    total = 0
    highest_ratio = 0.0
    for info in infos:
        if info.is_dir():
            continue
        size = int(info.file_size)
        compressed = int(info.compress_size)
        if size < 0 or compressed < 0:
            raise ZipResourceLimitError(f"zip_negative_member_size:{info.filename}")
        if size > active.max_member_uncompressed_bytes:
            raise ZipResourceLimitError(
                f"zip_member_size_limit_exceeded:{info.filename}:{size}>{active.max_member_uncompressed_bytes}"
            )
        total += size
        if total > active.max_total_uncompressed_bytes:
            raise ZipResourceLimitError(
                f"zip_total_size_limit_exceeded:{total}>{active.max_total_uncompressed_bytes}"
            )
        if size:
            ratio = float("inf") if compressed == 0 else size / compressed
            highest_ratio = max(highest_ratio, ratio)
            if ratio > active.max_compression_ratio:
                raise ZipResourceLimitError(
                    f"zip_compression_ratio_limit_exceeded:{info.filename}:{ratio:.2f}>{active.max_compression_ratio:.2f}"
                )
    return {
        "member_count": len(infos),
        "total_uncompressed_bytes": total,
        "highest_compression_ratio": highest_ratio,
        **active.to_dict(),
    }
