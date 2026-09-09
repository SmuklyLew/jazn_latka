from __future__ import annotations

"""Safe optional backend convergence for 7z and RAR read/extraction."""

from importlib import metadata
from pathlib import Path
import re
from typing import Any

from latka_jazn.archive.service import (
    ArchiveEntry,
    ArchiveError,
    ArchiveInspection,
    ArchiveSecurityLimits,
    _normalize_member_name,
    _password_text,
    _validate_entries,
    normalize_archive_format as _base_normalize_archive_format,
)

RAR3_SIGNATURE = b"Rar!\x1a\x07\x00"
RAR5_SIGNATURE = b"Rar!\x1a\x07\x01\x00"


def _version_tuple(value: str | None) -> tuple[int, int, int]:
    parts = [int(item) for item in re.findall(r"\d+", str(value or ""))[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])  # type: ignore[return-value]


def import_safe_py7zr() -> Any:
    try:
        import py7zr  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ArchiveError("py7zr_not_installed") from exc
    try:
        version = metadata.version("py7zr")
    except metadata.PackageNotFoundError as exc:
        raise ArchiveError("py7zr_distribution_metadata_missing") from exc
    if _version_tuple(version) < (1, 1, 3):
        raise ArchiveError(f"py7zr_version_unsafe:{version}:requires>=1.1.3")
    return py7zr


def normalize_archive_format(value: str | None) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    if raw in {"rar", "rar3", "rar5"}:
        return "rar"
    return _base_normalize_archive_format(value)


class ArchiveBackendConvergenceMixin:
    limits: ArchiveSecurityLimits

    def inspect(
        self,
        source: Path,
        *,
        archive_format: str | None = None,
        password: str | bytes | None = None,
        verify_crc: bool = True,
    ) -> ArchiveInspection:
        source = Path(source).expanduser().resolve()
        declared = str(archive_format or "").strip().lower().replace(" ", "_")
        declared_rar = declared in {"rar", "rar3", "rar5"}
        auto = declared in {"", "auto"}
        signature_rar = False
        if auto:
            try:
                with source.open("rb") as handle:
                    signature = handle.read(8)
            except OSError as exc:
                raise ArchiveError(f"archive_unreadable:{source}:{exc}") from exc
            signature_rar = signature.startswith(RAR3_SIGNATURE) or signature.startswith(RAR5_SIGNATURE)
        if declared_rar or signature_rar:
            from latka_jazn.archive.rar_backend import inspect_rar

            return inspect_rar(
                source,
                password=_password_text(password),
                limits=self.limits,
                verify_crc=verify_crc,
            )
        return super().inspect(  # type: ignore[misc]
            source,
            archive_format=archive_format,
            password=password,
            verify_crc=verify_crc,
        )

    def _inspect_7z(
        self,
        source: Path,
        *,
        password: str | bytes | None,
        verify_crc: bool,
    ) -> ArchiveInspection:
        py7zr = import_safe_py7zr()
        text_password = _password_text(password)
        try:
            with py7zr.SevenZipFile(
                source,
                mode="r",
                password=text_password,
                max_extract_size=int(self.limits.max_total_uncompressed_bytes),
            ) as archive:
                encrypted = bool(archive.needs_password())
                if encrypted and not text_password:
                    raise ArchiveError("archive_password_required")
                entries: list[ArchiveEntry] = []
                for row in archive.list():
                    is_dir = bool(getattr(row, "is_directory", False))
                    is_symlink = bool(getattr(row, "is_symlink", False))
                    is_file = bool(getattr(row, "is_file", not is_dir and not is_symlink))
                    entries.append(
                        ArchiveEntry(
                            name=_normalize_member_name(str(getattr(row, "filename"))),
                            size_bytes=int(getattr(row, "uncompressed", 0) or 0),
                            compressed_size_bytes=(
                                int(getattr(row, "compressed"))
                                if getattr(row, "compressed", None) is not None
                                else None
                            ),
                            is_dir=is_dir,
                            is_symlink=is_symlink,
                            is_regular_file=is_file,
                            encrypted=encrypted,
                        )
                    )
                frozen = tuple(entries)
                total = _validate_entries(frozen, self.limits)
                if verify_crc:
                    bad = archive.testzip()
                    if bad:
                        raise ArchiveError(f"archive_crc_failed:{bad}")
                return ArchiveInspection(
                    archive_format="7z",
                    entries=frozen,
                    total_uncompressed_bytes=total,
                    encrypted=encrypted,
                    crc_verified=bool(verify_crc),
                )
        except ArchiveError:
            raise
        except Exception as exc:
            raise ArchiveError(f"archive_7z_read_failed:{type(exc).__name__}:{exc}") from exc

    def _extract_archive_to(
        self,
        source: Path,
        staging: Path,
        archive_format: str,
        *,
        password: str | bytes | None,
    ) -> None:
        if archive_format == "rar":
            from latka_jazn.archive.rar_backend import extract_rar_to_directory

            extract_rar_to_directory(
                source,
                staging,
                password=_password_text(password),
                limits=self.limits,
                verify_crc=False,
            )
            return
        if archive_format == "7z":
            py7zr = import_safe_py7zr()
            try:
                with py7zr.SevenZipFile(
                    source,
                    mode="r",
                    password=_password_text(password),
                    max_extract_size=int(self.limits.max_total_uncompressed_bytes),
                ) as archive:
                    archive.extractall(path=staging)
            except Exception as exc:
                raise ArchiveError(f"archive_7z_extract_failed:{type(exc).__name__}:{exc}") from exc
            return
        return super()._extract_archive_to(  # type: ignore[misc]
            source,
            staging,
            archive_format,
            password=password,
        )
