from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import metadata, util
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from latka_jazn.archive.service import (
    CHUNK_SIZE,
    ArchiveEntry,
    ArchiveError,
    ArchiveInspection,
    ArchiveSecurityLimits,
    _check_free_space,
    _normalize_member_name,
    _safe_target,
    _validate_entries,
)

RAR3_SIGNATURE = b"Rar!\x1a\x07\x00"
RAR5_SIGNATURE = b"Rar!\x1a\x07\x01\x00"
RAR_BACKEND_CANDIDATES = ("unrar", "unar", "7zz", "7z", "bsdtar")


@dataclass(frozen=True, slots=True)
class RarBackendStatus:
    module_available: bool
    module_version: str | None
    metadata_ready: bool
    compressed_extract_ready: bool
    external_backends: tuple[str, ...]
    preferred_backend: str | None
    creation_supported_by_rarfile: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["external_backends"] = list(self.external_backends)
        return payload


def _rarfile_module() -> Any:
    try:
        import rarfile  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ArchiveError("rarfile_not_installed") from exc
    return rarfile


def rar_backend_status() -> RarBackendStatus:
    try:
        module_available = util.find_spec("rarfile") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        module_available = False
    try:
        module_version = metadata.version("rarfile") if module_available else None
    except metadata.PackageNotFoundError:
        module_version = None
    backends = tuple(name for name in RAR_BACKEND_CANDIDATES if shutil.which(name))
    return RarBackendStatus(
        module_available=module_available,
        module_version=module_version,
        metadata_ready=module_available,
        compressed_extract_ready=bool(module_available and backends),
        external_backends=backends,
        preferred_backend=backends[0] if backends else None,
    )


def is_rar_file(path: Path | str) -> bool:
    try:
        with Path(path).open("rb") as handle:
            signature = handle.read(8)
    except OSError:
        return False
    return signature.startswith(RAR3_SIGNATURE) or signature.startswith(RAR5_SIGNATURE)


def inspect_rar(
    source: Path | str,
    *,
    password: str | None = None,
    limits: ArchiveSecurityLimits | None = None,
    verify_crc: bool = False,
) -> ArchiveInspection:
    rarfile = _rarfile_module()
    source_path = Path(source).expanduser().resolve()
    if not is_rar_file(source_path):
        raise ArchiveError(f"invalid_rar_signature:{source_path}")
    policy = limits or ArchiveSecurityLimits()
    try:
        with rarfile.RarFile(source_path, errors="strict") as archive:
            if password:
                archive.setpassword(password)
            encrypted = bool(archive.needs_password())
            if encrypted and not password:
                raise ArchiveError("archive_password_required")
            entries: list[ArchiveEntry] = []
            for info in archive.infolist():
                is_dir = bool(info.is_dir())
                is_symlink = bool(info.is_symlink())
                is_file = bool(info.is_file())
                entries.append(
                    ArchiveEntry(
                        name=_normalize_member_name(str(info.filename)),
                        size_bytes=int(info.file_size or 0),
                        compressed_size_bytes=int(info.compress_size or 0),
                        is_dir=is_dir,
                        is_symlink=is_symlink,
                        is_regular_file=is_file,
                        encrypted=bool(info.needs_password()),
                    )
                )
            frozen = tuple(entries)
            total = _validate_entries(frozen, policy)
            if verify_crc:
                archive.testrar(pwd=password)
            return ArchiveInspection(
                archive_format="rar",
                entries=frozen,
                total_uncompressed_bytes=total,
                encrypted=encrypted,
                crc_verified=bool(verify_crc),
            )
    except ArchiveError:
        raise
    except Exception as exc:
        raise ArchiveError(f"archive_rar_read_failed:{type(exc).__name__}:{exc}") from exc


def extract_rar(
    source: Path | str,
    destination: Path | str,
    *,
    password: str | None = None,
    limits: ArchiveSecurityLimits | None = None,
    replace_existing: bool = False,
) -> dict[str, Any]:
    rarfile = _rarfile_module()
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    policy = limits or ArchiveSecurityLimits()
    inspection = inspect_rar(
        source_path,
        password=password,
        limits=policy,
        verify_crc=False,
    )
    _check_free_space(destination_path.parent, inspection.total_uncompressed_bytes, policy)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_path.name}.rar-extract-",
            dir=str(destination_path.parent),
        )
    )
    backup: Path | None = None
    try:
        with rarfile.RarFile(source_path, errors="strict") as archive:
            if password:
                archive.setpassword(password)
            for info in archive.infolist():
                name = _normalize_member_name(str(info.filename))
                target = _safe_target(staging, name)
                if info.is_symlink():
                    raise ArchiveError(f"archive_symlink_rejected:{name}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not info.is_file():
                    raise ArchiveError(f"archive_special_file_rejected:{name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise ArchiveError(f"archive_target_collision:{name}")
                temp = target.with_name(target.name + ".tmp")
                with archive.open(info, pwd=password) as input_handle, temp.open("xb") as output_handle:
                    shutil.copyfileobj(input_handle, output_handle, length=CHUNK_SIZE)
                os.replace(temp, target)

        if destination_path.exists():
            if not replace_existing:
                raise ArchiveError(f"archive_destination_exists:{destination_path}")
            backup = destination_path.with_name(
                destination_path.name + f".backup-{os.getpid()}"
            )
            os.replace(destination_path, backup)
        os.replace(staging, destination_path)
        if backup is not None and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        return {
            "ok": True,
            "source": str(source_path),
            "destination": str(destination_path),
            "container_format": "rar",
            "entry_count": len(inspection.entries),
            "total_uncompressed_bytes": inspection.total_uncompressed_bytes,
            "encrypted": inspection.encrypted,
            "backend": rar_backend_status().to_dict(),
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if backup is not None and backup.exists() and not destination_path.exists():
            os.replace(backup, destination_path)
        raise
