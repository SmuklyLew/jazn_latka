from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct
import tempfile
import unicodedata
import uuid
import zipfile

from latka_jazn.packaging.package_set_contract import READABLE_SCHEMAS
from latka_jazn.archive.resource_policy import GENERIC_ARCHIVE
from latka_jazn.tools.safe_paths import validate_safe_relative_path, portable_path_key
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


CHUNK_SIZE = 8 * 1024 * 1024
SEVEN_Z_SIGNATURE = b"7z\xbc\xaf\x27\x1c"
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
SUPPORTED_PACKAGE_SCHEMAS = READABLE_SCHEMAS
ARCHIVE_FORMAT_ALIASES = {
    "zip": "zip",
    "zip64": "zip",
    "pyzip": "zip",
    "pyzipfile": "zip",
    "pyzip_file": "zip",
    "7z": "7z",
    "sevenzip": "7z",
    "seven_zip": "7z",
    "aes_zip": "aes_zip",
    "aes-zip": "aes_zip",
    "zip_aes": "aes_zip",
}
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_SPLIT_SUFFIX = re.compile(r"\.\d{3,4}$")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ArchiveError(ValueError):
    """Fail-closed archive I/O error."""


@dataclass(frozen=True, slots=True)
class ArchiveSecurityLimits:
    max_members: int = GENERIC_ARCHIVE.max_members
    max_total_uncompressed_bytes: int = GENERIC_ARCHIVE.max_total_uncompressed_bytes
    max_member_bytes: int = GENERIC_ARCHIVE.max_member_uncompressed_bytes
    max_compression_ratio: float = GENERIC_ARCHIVE.max_compression_ratio
    max_name_length: int = 1024
    require_free_space: bool = True
    reject_symlinks: bool = True
    reject_special_files: bool = True
    reject_casefold_collisions: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    name: str
    size_bytes: int
    compressed_size_bytes: int | None
    is_dir: bool = False
    is_symlink: bool = False
    is_regular_file: bool = True
    encrypted: bool = False


@dataclass(frozen=True, slots=True)
class ArchiveInspection:
    archive_format: str
    entries: tuple[ArchiveEntry, ...]
    total_uncompressed_bytes: int
    encrypted: bool
    crc_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_format": self.archive_format,
            "entry_count": len(self.entries),
            "file_count": sum(1 for item in self.entries if not item.is_dir),
            "total_uncompressed_bytes": self.total_uncompressed_bytes,
            "encrypted": self.encrypted,
            "crc_verified": self.crc_verified,
            "entries": [asdict(item) for item in self.entries],
        }


@dataclass(frozen=True, slots=True)
class ArchiveWriteEntry:
    arcname: str
    source: Path | None = None
    data: bytes | None = None

    def __post_init__(self) -> None:
        if (self.source is None) == (self.data is None):
            raise ValueError("ArchiveWriteEntry requires exactly one of source or data")


def normalize_archive_format(value: str | None) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    if raw in {"", "auto"}:
        return "auto"
    normalized = ARCHIVE_FORMAT_ALIASES.get(raw)
    if normalized is None:
        raise ArchiveError(f"unsupported_archive_format:{value}")
    return normalized


def _normalize_member_name(value: str) -> str:
    try:
        return validate_safe_relative_path(str(value or ""))
    except Exception as exc:
        raise ArchiveError(f"unsafe_archive_member:{value}:{exc}") from exc


def _member_key(name: str) -> str:
    try:
        return portable_path_key(name)
    except Exception as exc:
        raise ArchiveError(f"unsafe_archive_member:{name}:{exc}") from exc


def _zip_has_aes_extra(extra: bytes) -> bool:
    offset = 0
    while offset + 4 <= len(extra):
        field_id, size = struct.unpack_from("<HH", extra, offset)
        offset += 4
        if offset + size > len(extra):
            break
        if field_id == 0x9901:
            return True
        offset += size
    return False


def _zip_entry(info: zipfile.ZipInfo) -> ArchiveEntry:
    name = _normalize_member_name(info.filename)
    unix_mode = (int(info.external_attr) >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode) if unix_mode else 0
    is_dir = info.is_dir()
    is_symlink = file_type == stat.S_IFLNK
    is_regular = bool(is_dir or file_type in {0, stat.S_IFREG, stat.S_IFDIR})
    return ArchiveEntry(
        name=name,
        size_bytes=int(info.file_size),
        compressed_size_bytes=int(info.compress_size),
        is_dir=is_dir,
        is_symlink=is_symlink,
        is_regular_file=is_regular and not is_symlink,
        encrypted=bool(info.flag_bits & 0x1),
    )


def _import_py7zr() -> Any:
    try:
        import py7zr  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ArchiveError("py7zr_not_installed") from exc
    return py7zr


def _import_pyzipper() -> Any:
    try:
        import pyzipper  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ArchiveError("pyzipper_not_installed") from exc
    return pyzipper


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _password_bytes(password: str | bytes | None) -> bytes | None:
    if password is None:
        return None
    return password if isinstance(password, bytes) else str(password).encode("utf-8")


def _password_text(password: str | bytes | None) -> str | None:
    if password is None:
        return None
    return password.decode("utf-8") if isinstance(password, bytes) else str(password)


def _safe_target(root: Path, member_name: str) -> Path:
    root = root.resolve()
    target = (root / Path(*PurePosixPath(member_name).parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ArchiveError(f"unsafe_archive_member:escape:{member_name}") from exc
    return target


def _validate_entries(entries: Sequence[ArchiveEntry], limits: ArchiveSecurityLimits) -> int:
    if len(entries) > int(limits.max_members):
        raise ArchiveError(f"archive_member_limit_exceeded:{len(entries)}>{limits.max_members}")
    exact: set[str] = set()
    folded: set[str] = set()
    total = 0
    for entry in entries:
        if len(entry.name) > limits.max_name_length:
            raise ArchiveError(f"archive_member_name_too_long:{entry.name[:120]}")
        normalized = _normalize_member_name(entry.name)
        if normalized in exact:
            raise ArchiveError(f"duplicate_archive_member:{normalized}")
        exact.add(normalized)
        folded_key = _member_key(normalized)
        if limits.reject_casefold_collisions and folded_key in folded:
            raise ArchiveError(f"casefold_archive_member_collision:{normalized}")
        folded.add(folded_key)
        if limits.reject_symlinks and entry.is_symlink:
            raise ArchiveError(f"archive_symlink_rejected:{normalized}")
        if limits.reject_special_files and not entry.is_dir and not entry.is_regular_file:
            raise ArchiveError(f"archive_special_file_rejected:{normalized}")
        if entry.is_dir:
            continue
        if entry.size_bytes < 0 or entry.size_bytes > limits.max_member_bytes:
            raise ArchiveError(
                f"archive_member_size_limit_exceeded:{normalized}:{entry.size_bytes}>{limits.max_member_bytes}"
            )
        total += entry.size_bytes
        if total > limits.max_total_uncompressed_bytes:
            raise ArchiveError(
                f"archive_total_size_limit_exceeded:{total}>{limits.max_total_uncompressed_bytes}"
            )
        compressed = entry.compressed_size_bytes
        if compressed is not None and compressed > 0 and entry.size_bytes > 0:
            ratio = entry.size_bytes / compressed
            if ratio > limits.max_compression_ratio:
                raise ArchiveError(
                    f"archive_compression_ratio_limit_exceeded:{normalized}:{ratio:.2f}>{limits.max_compression_ratio:.2f}"
                )
    return total


def _check_free_space(destination_parent: Path, needed: int, limits: ArchiveSecurityLimits) -> None:
    if not limits.require_free_space:
        return
    destination_parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(destination_parent).free
    margin = max(64 * 1024 * 1024, int(needed * 0.05))
    if free < needed + margin:
        raise ArchiveError(f"insufficient_disk_space:{free}<{needed + margin}")


def _detect_zip_format(path: Path) -> str:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            for info in archive.infolist():
                if bool(info.flag_bits & 0x1) and _zip_has_aes_extra(info.extra):
                    return "aes_zip"
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"invalid_zip:{path}") from exc
    return "zip"


def detect_archive_format(path: Path, declared: str | None = None) -> str:
    normalized = normalize_archive_format(declared)
    if normalized != "auto":
        return normalized
    path = Path(path)
    try:
        with path.open("rb") as handle:
            signature = handle.read(8)
    except OSError as exc:
        raise ArchiveError(f"archive_unreadable:{path}:{exc}") from exc
    if signature.startswith(SEVEN_Z_SIGNATURE):
        return "7z"
    if any(signature.startswith(item) for item in ZIP_SIGNATURES):
        return _detect_zip_format(path)
    raise ArchiveError(f"archive_format_unknown:{path}")


class ArchiveExtractionService:
    """Shared fail-closed archive service for runtime and package tools.

    Supported containers:
    - ZIP / ZIP64 using the Python standard library;
    - 7z using py7zr;
    - WinZip AES ZIP using pyzipper;
    - pyzip/PyZipFile as aliases of ordinary ZIP.

    Binary split sets are joined only after sidecar SHA-256 verification. Extraction
    always happens in a sibling staging directory and is committed atomically.
    """

    def __init__(self, limits: ArchiveSecurityLimits | None = None) -> None:
        self.limits = limits or ArchiveSecurityLimits()

    @staticmethod
    def password_from_env(variable: str | None) -> str | None:
        name = str(variable or "").strip()
        return os.environ.get(name) if name else None

    def inspect(
        self,
        source: Path,
        *,
        archive_format: str | None = None,
        password: str | bytes | None = None,
        verify_crc: bool = True,
    ) -> ArchiveInspection:
        source = Path(source).expanduser().resolve()
        fmt = detect_archive_format(source, archive_format)
        if fmt in {"zip", "aes_zip"}:
            return self._inspect_zip(source, fmt, password=password, verify_crc=verify_crc)
        return self._inspect_7z(source, password=password, verify_crc=verify_crc)

    def _inspect_zip(
        self,
        source: Path,
        fmt: str,
        *,
        password: str | bytes | None,
        verify_crc: bool,
    ) -> ArchiveInspection:
        opener: Any = zipfile.ZipFile if fmt == "zip" else _import_pyzipper().AESZipFile
        try:
            with opener(source, "r") as archive:
                pwd = _password_bytes(password)
                if pwd:
                    archive.setpassword(pwd)
                entries = tuple(_zip_entry(info) for info in archive.infolist())
                total = _validate_entries(entries, self.limits)
                encrypted = any(item.encrypted for item in entries)
                if encrypted and not pwd:
                    raise ArchiveError("archive_password_required")
                if verify_crc:
                    bad = archive.testzip()
                    if bad:
                        raise ArchiveError(f"archive_crc_failed:{bad}")
                return ArchiveInspection(
                    archive_format=fmt,
                    entries=entries,
                    total_uncompressed_bytes=total,
                    encrypted=encrypted,
                    crc_verified=bool(verify_crc),
                )
        except ArchiveError:
            raise
        except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
            raise ArchiveError(f"archive_zip_read_failed:{type(exc).__name__}:{exc}") from exc

    def _inspect_7z(
        self,
        source: Path,
        *,
        password: str | bytes | None,
        verify_crc: bool,
    ) -> ArchiveInspection:
        py7zr = _import_py7zr()
        text_password = _password_text(password)
        try:
            with py7zr.SevenZipFile(source, mode="r", password=text_password) as archive:
                encrypted = bool(archive.needs_password())
                if encrypted and not text_password:
                    raise ArchiveError("archive_password_required")
                rows = archive.list()
                entries: list[ArchiveEntry] = []
                for row in rows:
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

    def create_archive(
        self,
        entries: Sequence[ArchiveWriteEntry],
        output: Path,
        *,
        archive_format: str,
        compression_level: int = 6,
        password: str | bytes | None = None,
        aes_bits: int = 256,
    ) -> ArchiveInspection:
        fmt = normalize_archive_format(archive_format)
        if fmt == "auto":
            raise ArchiveError("archive_format_required_for_creation")
        if not 0 <= int(compression_level) <= 9:
            raise ArchiveError("compression_level_out_of_range")
        if int(aes_bits) not in {128, 192, 256}:
            raise ArchiveError("aes_bits_must_be_128_192_or_256")
        output = Path(output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ArchiveError(f"archive_output_exists:{output}")
        normalized: list[ArchiveWriteEntry] = []
        seen: set[str] = set()
        folded: set[str] = set()
        for entry in entries:
            arcname = _normalize_member_name(entry.arcname)
            if arcname in seen or _member_key(arcname) in folded:
                raise ArchiveError(f"duplicate_archive_write_member:{arcname}")
            seen.add(arcname)
            folded.add(_member_key(arcname))
            if entry.source is not None:
                source = Path(entry.source).resolve()
                if source.is_symlink() or not source.is_file():
                    raise ArchiveError(f"archive_source_not_regular_file:{source}")
                normalized.append(ArchiveWriteEntry(arcname=arcname, source=source))
            else:
                normalized.append(ArchiveWriteEntry(arcname=arcname, data=bytes(entry.data or b"")))
        try:
            if fmt == "zip":
                self._create_zip(normalized, output, compression_level)
            elif fmt == "aes_zip":
                if password is None:
                    raise ArchiveError("archive_password_required_for_aes_zip_creation")
                self._create_aes_zip(normalized, output, compression_level, password, aes_bits)
            else:
                self._create_7z(normalized, output, compression_level, password)
            return self.inspect(output, archive_format=fmt, password=password, verify_crc=True)
        except Exception:
            output.unlink(missing_ok=True)
            raise

    @staticmethod
    def _create_zip(entries: Sequence[ArchiveWriteEntry], output: Path, level: int) -> None:
        with zipfile.ZipFile(
            output,
            mode="x",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=level,
            allowZip64=True,
            strict_timestamps=False,
        ) as archive:
            for entry in entries:
                if entry.source is not None:
                    archive.write(entry.source, entry.arcname)
                else:
                    archive.writestr(entry.arcname, entry.data or b"", compress_type=zipfile.ZIP_DEFLATED, compresslevel=level)

    @staticmethod
    def _create_aes_zip(
        entries: Sequence[ArchiveWriteEntry],
        output: Path,
        level: int,
        password: str | bytes,
        aes_bits: int,
    ) -> None:
        pyzipper = _import_pyzipper()
        pwd = _password_bytes(password)
        assert pwd is not None
        with pyzipper.AESZipFile(
            output,
            mode="x",
            compression=pyzipper.ZIP_DEFLATED,
            compresslevel=level,
        ) as archive:
            archive.setpassword(pwd)
            archive.setencryption(pyzipper.WZ_AES, nbits=int(aes_bits))
            for entry in entries:
                if entry.source is not None:
                    archive.write(entry.source, entry.arcname)
                else:
                    archive.writestr(entry.arcname, entry.data or b"")

    @staticmethod
    def _create_7z(
        entries: Sequence[ArchiveWriteEntry],
        output: Path,
        level: int,
        password: str | bytes | None,
    ) -> None:
        py7zr = _import_py7zr()
        filters = [{"id": py7zr.FILTER_LZMA2, "preset": int(level)}]
        text_password = _password_text(password)
        with tempfile.TemporaryDirectory(prefix="jazn-7z-virtual-") as temp_raw:
            temp = Path(temp_raw)
            with py7zr.SevenZipFile(
                output,
                mode="w",
                filters=filters,
                password=text_password,
                header_encryption=bool(text_password),
            ) as archive:
                for index, entry in enumerate(entries):
                    source = entry.source
                    if source is None:
                        source = temp / f"virtual-{index:08d}.bin"
                        source.write_bytes(entry.data or b"")
                    archive.write(source, arcname=entry.arcname)

    def extract_source(
        self,
        source: Path,
        destination: Path,
        *,
        archive_format: str | None = None,
        password: str | bytes | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        source = Path(source).expanduser()
        destination = Path(destination).expanduser().resolve()
        sidecar: Path | None = None
        if source.name.endswith(".package.json") and source.is_file():
            sidecar = source.resolve()
        elif source.is_file() and (source.parent / f"{source.name}.package.json").is_file():
            sidecar = (source.parent / f"{source.name}.package.json").resolve()
        elif not source.exists() and Path(str(source) + ".package.json").is_file():
            sidecar = Path(str(source) + ".package.json").resolve()
        elif source.is_file() and _SPLIT_SUFFIX.search(source.name):
            base = _SPLIT_SUFFIX.sub("", str(source))
            candidate = Path(base + ".package.json")
            if candidate.is_file():
                sidecar = candidate.resolve()
            else:
                raise ArchiveError("split_archive_requires_verified_package_sidecar")
        if sidecar is not None:
            return self.extract_package_sidecar(
                sidecar,
                destination,
                password=password,
                replace_existing=replace_existing,
            )
        source = source.resolve()
        inspection = self.inspect(source, archive_format=archive_format, password=password, verify_crc=True)
        _check_free_space(destination.parent, inspection.total_uncompressed_bytes, self.limits)
        staging = self._new_staging(destination)
        try:
            self._extract_archive_to(source, staging, inspection.archive_format, password=password)
            self._verify_extracted_tree(staging, inspection.entries, expected=None)
            self._commit_staging(staging, destination, replace_existing=replace_existing)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return {
            "ok": True,
            "source": str(source),
            "destination": str(destination),
            "container_format": inspection.archive_format,
            "entry_count": len(inspection.entries),
            "total_uncompressed_bytes": inspection.total_uncompressed_bytes,
            "encrypted": inspection.encrypted,
            "security_limits": self.limits.to_dict(),
        }

    def verify_package_sidecar(
        self,
        sidecar: Path,
        *,
        password: str | bytes | None = None,
    ) -> dict[str, Any]:
        sidecar = Path(sidecar).expanduser().resolve()
        with tempfile.TemporaryDirectory(prefix="jazn-package-verify-", dir=str(sidecar.parent)) as temp_raw:
            destination = Path(temp_raw) / "verified"
            report = self.extract_package_sidecar(
                sidecar,
                destination,
                password=password,
                replace_existing=False,
            )
        report.pop("destination", None)
        report["verification_only"] = True
        return report

    def extract_package_sidecar(
        self,
        sidecar: Path,
        destination: Path,
        *,
        password: str | bytes | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        sidecar = Path(sidecar).expanduser().resolve()
        destination = Path(destination).expanduser().resolve()
        payload = self._load_sidecar(sidecar)
        outputs = self._verified_outputs(sidecar.parent, payload)
        expected = self._expected_entries(payload)
        volume_format = str(payload.get("archive_format") or "independent").strip().lower()
        if volume_format not in {"independent", "binary"}:
            raise ArchiveError(f"unsupported_volume_format:{volume_format}")
        declared_container = normalize_archive_format(str(payload.get("container_format") or "auto"))
        staging = self._new_staging(destination)
        joined: Path | None = None
        try:
            if volume_format == "binary":
                logical_name = str(payload.get("package_name") or "joined.archive")
                joined = staging.parent / f".{Path(logical_name).name}.joined-{uuid.uuid4().hex}"
                logical_expected = str(
                    payload.get("logical_archive_sha256")
                    or payload.get("logical_zip_sha256")
                    or ""
                ).strip().lower() or None
                self.join_parts(
                    [sidecar.parent / item["filename"] for item in outputs],
                    joined,
                    expected_sha256=[str(item["sha256"]) for item in outputs],
                    logical_sha256=logical_expected,
                )
                inspection = self.inspect(
                    joined,
                    archive_format=declared_container,
                    password=password,
                    verify_crc=True,
                )
                self._preflight_expected(inspection.entries, expected)
                _check_free_space(destination.parent, inspection.total_uncompressed_bytes, self.limits)
                self._extract_archive_to(joined, staging, inspection.archive_format, password=password)
                all_entries = inspection.entries
                container_format = inspection.archive_format
                encrypted = inspection.encrypted
                total = inspection.total_uncompressed_bytes
            else:
                inspections: list[tuple[Path, ArchiveInspection]] = []
                aggregate: list[ArchiveEntry] = []
                for item in outputs:
                    part_path = sidecar.parent / item["filename"]
                    inspection = self.inspect(
                        part_path,
                        archive_format=declared_container,
                        password=password,
                        verify_crc=True,
                    )
                    inspections.append((part_path, inspection))
                    aggregate.extend(inspection.entries)
                all_entries = tuple(aggregate)
                total = _validate_entries(all_entries, self.limits)
                self._preflight_expected(all_entries, expected)
                _check_free_space(destination.parent, total, self.limits)
                for part_path, inspection in inspections:
                    self._extract_archive_to(part_path, staging, inspection.archive_format, password=password)
                container_format = inspections[0][1].archive_format if inspections else declared_container
                encrypted = any(item.encrypted for _, item in inspections)
            self._verify_extracted_tree(staging, all_entries, expected=expected)
            self._commit_staging(staging, destination, replace_existing=replace_existing)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        finally:
            if joined is not None:
                joined.unlink(missing_ok=True)
        return {
            "ok": True,
            "sidecar": str(sidecar),
            "destination": str(destination),
            "package_name": payload.get("package_name"),
            "profile": payload.get("profile"),
            "container_format": container_format,
            "archive_format": volume_format,
            "outputs": len(outputs),
            "entries": len(expected),
            "total_uncompressed_bytes": total,
            "encrypted": encrypted,
            "security_limits": self.limits.to_dict(),
        }

    @staticmethod
    def _load_sidecar(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ArchiveError(f"package_sidecar_invalid:{path}:{exc}") from exc
        if not isinstance(payload, dict):
            raise ArchiveError("package_sidecar_not_object")
        schema = str(payload.get("schema_version") or "")
        if schema not in SUPPORTED_PACKAGE_SCHEMAS:
            raise ArchiveError(f"package_sidecar_schema_unsupported:{schema}")
        return payload

    @staticmethod
    def _verified_outputs(parent: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = payload.get("outputs")
        if not isinstance(rows, list) or not rows:
            raise ArchiveError("package_sidecar_outputs_missing")
        outputs: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                raise ArchiveError("package_sidecar_output_invalid")
            item = {
                "part_no": int(raw["part_no"]),
                "filename": str(raw["filename"]),
                "size_bytes": int(raw["size_bytes"]),
                "sha256": str(raw["sha256"]).lower(),
            }
            path = (parent / item["filename"]).resolve()
            try:
                path.relative_to(parent.resolve())
            except ValueError as exc:
                raise ArchiveError(f"package_output_escapes_directory:{item['filename']}") from exc
            if not path.is_file():
                raise ArchiveError(f"package_output_missing:{item['filename']}")
            if path.stat().st_size != item["size_bytes"]:
                raise ArchiveError(f"package_output_size_mismatch:{item['filename']}")
            if _sha256_file(path) != item["sha256"]:
                raise ArchiveError(f"package_output_sha256_mismatch:{item['filename']}")
            outputs.append(item)
        outputs.sort(key=lambda item: item["part_no"])
        numbers = [item["part_no"] for item in outputs]
        if numbers != list(range(1, len(outputs) + 1)):
            raise ArchiveError(f"package_output_part_sequence_invalid:{numbers}")
        expected_set_hash = str(payload.get("package_set_sha256") or "").strip().lower()
        if expected_set_hash:
            digest = hashlib.sha256()
            for item in outputs:
                digest.update(
                    f"{item['part_no']}\0{item['filename']}\0{item['size_bytes']}\0{item['sha256']}\n".encode("utf-8")
                )
            if digest.hexdigest() != expected_set_hash:
                raise ArchiveError("package_set_sha256_mismatch")
        return outputs

    @staticmethod
    def _expected_entries(payload: dict[str, Any]) -> dict[str, tuple[int, str]]:
        rows = payload.get("entries")
        if not isinstance(rows, list) or not rows:
            raise ArchiveError("package_sidecar_entries_missing")
        expected: dict[str, tuple[int, str]] = {}
        folded: set[str] = set()
        for raw in rows:
            if not isinstance(raw, dict):
                raise ArchiveError("package_sidecar_entry_invalid")
            name = _normalize_member_name(str(raw["path"]))
            key = _member_key(name)
            if name in expected or key in folded:
                raise ArchiveError(f"package_sidecar_duplicate_entry:{name}")
            folded.add(key)
            expected[name] = (int(raw["size_bytes"]), str(raw["sha256"]).lower())
        return expected

    @staticmethod
    def _preflight_expected(
        entries: Sequence[ArchiveEntry],
        expected: dict[str, tuple[int, str]],
    ) -> None:
        actual = {item.name for item in entries if not item.is_dir}
        wanted = set(expected)
        if actual != wanted:
            raise ArchiveError(
                "package_archive_members_mismatch:"
                f"missing={sorted(wanted-actual)[:10]}:extra={sorted(actual-wanted)[:10]}"
            )
        for entry in entries:
            if entry.is_dir:
                continue
            size, _ = expected[entry.name]
            if int(entry.size_bytes) != int(size):
                raise ArchiveError(f"package_archive_member_size_mismatch:{entry.name}")

    @staticmethod
    def _new_staging(destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / f".{destination.name}.extract-{uuid.uuid4().hex}"
        staging.mkdir(mode=0o700)
        return staging

    def _extract_archive_to(
        self,
        source: Path,
        staging: Path,
        archive_format: str,
        *,
        password: str | bytes | None,
    ) -> None:
        if archive_format in {"zip", "aes_zip"}:
            opener: Any = zipfile.ZipFile if archive_format == "zip" else _import_pyzipper().AESZipFile
            pwd = _password_bytes(password)
            try:
                with opener(source, "r") as archive:
                    if pwd:
                        archive.setpassword(pwd)
                    for info in archive.infolist():
                        entry = _zip_entry(info)
                        target = _safe_target(staging, entry.name)
                        if entry.is_dir:
                            target.mkdir(parents=True, exist_ok=True)
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if target.exists():
                            raise ArchiveError(f"archive_target_collision:{entry.name}")
                        temp = target.with_name(target.name + f".extract-{uuid.uuid4().hex}.tmp")
                        with archive.open(info, "r") as input_handle, temp.open("xb") as output_handle:
                            shutil.copyfileobj(input_handle, output_handle, length=CHUNK_SIZE)
                        os.replace(temp, target)
            except ArchiveError:
                raise
            except Exception as exc:
                raise ArchiveError(f"archive_zip_extract_failed:{type(exc).__name__}:{exc}") from exc
            return
        py7zr = _import_py7zr()
        try:
            with py7zr.SevenZipFile(source, mode="r", password=_password_text(password)) as archive:
                archive.extractall(path=staging)
        except Exception as exc:
            raise ArchiveError(f"archive_7z_extract_failed:{type(exc).__name__}:{exc}") from exc

    @staticmethod
    def _verify_extracted_tree(
        root: Path,
        entries: Sequence[ArchiveEntry],
        *,
        expected: dict[str, tuple[int, str]] | None,
    ) -> None:
        actual: dict[str, Path] = {}
        folded: set[str] = set()
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            base = Path(directory)
            safe_dirs: list[str] = []
            for dirname in dirnames:
                path = base / dirname
                if path.is_symlink():
                    raise ArchiveError(f"extracted_symlink_rejected:{path}")
                safe_dirs.append(dirname)
            dirnames[:] = safe_dirs
            for filename in filenames:
                path = base / filename
                if path.is_symlink() or not path.is_file():
                    raise ArchiveError(f"extracted_non_regular_file_rejected:{path}")
                relative = path.relative_to(root).as_posix()
                relative = _normalize_member_name(relative)
                key = _member_key(relative)
                if relative in actual or key in folded:
                    raise ArchiveError(f"extracted_path_collision:{relative}")
                actual[relative] = path
                folded.add(key)
        archive_files = {item.name for item in entries if not item.is_dir}
        if set(actual) != archive_files:
            raise ArchiveError(
                "extracted_tree_mismatch:"
                f"missing={sorted(archive_files-set(actual))[:10]}:extra={sorted(set(actual)-archive_files)[:10]}"
            )
        for entry in entries:
            if entry.is_dir:
                continue
            path = actual[entry.name]
            if path.stat().st_size != entry.size_bytes:
                raise ArchiveError(f"extracted_size_mismatch:{entry.name}")
            if expected is not None:
                size, digest = expected[entry.name]
                if path.stat().st_size != size or _sha256_file(path) != digest:
                    raise ArchiveError(f"extracted_sha256_mismatch:{entry.name}")

    @staticmethod
    def _commit_staging(staging: Path, destination: Path, *, replace_existing: bool) -> None:
        destination = destination.resolve()
        if destination.exists() and not replace_existing:
            raise ArchiveError(f"archive_destination_exists:{destination}")
        backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
        moved_old = False
        try:
            if destination.exists():
                os.replace(destination, backup)
                moved_old = True
            os.replace(staging, destination)
        except Exception:
            if moved_old and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    @staticmethod
    def split_file(
        source: Path,
        out_dir: Path,
        base_name: str,
        part_size_bytes: int,
    ) -> tuple[list[dict[str, Any]], str]:
        source = Path(source).resolve()
        out_dir = Path(out_dir).resolve()
        if part_size_bytes <= 0:
            raise ArchiveError("part_size_must_be_positive")
        out_dir.mkdir(parents=True, exist_ok=True)
        logical = hashlib.sha256()
        outputs: list[dict[str, Any]] = []
        with source.open("rb") as input_handle:
            part_no = 0
            while True:
                first = input_handle.read(min(CHUNK_SIZE, part_size_bytes))
                if not first:
                    break
                part_no += 1
                target = out_dir / f"{base_name}.{part_no:03d}"
                digest = hashlib.sha256()
                written = 0
                with target.open("xb") as output_handle:
                    chunk = first
                    while chunk:
                        output_handle.write(chunk)
                        digest.update(chunk)
                        logical.update(chunk)
                        written += len(chunk)
                        remaining = part_size_bytes - written
                        if remaining <= 0:
                            break
                        chunk = input_handle.read(min(CHUNK_SIZE, remaining))
                outputs.append(
                    {
                        "part_no": part_no,
                        "filename": target.name,
                        "size_bytes": written,
                        "sha256": digest.hexdigest(),
                    }
                )
        if not outputs:
            target = out_dir / f"{base_name}.001"
            target.write_bytes(b"")
            outputs.append(
                {
                    "part_no": 1,
                    "filename": target.name,
                    "size_bytes": 0,
                    "sha256": hashlib.sha256(b"").hexdigest(),
                }
            )
        return outputs, logical.hexdigest()

    @staticmethod
    def join_parts(
        parts: Sequence[Path],
        output: Path,
        *,
        expected_sha256: Sequence[str] | None = None,
        logical_sha256: str | None = None,
    ) -> str:
        if not parts:
            raise ArchiveError("split_parts_missing")
        if expected_sha256 is not None and len(expected_sha256) != len(parts):
            raise ArchiveError("split_part_hash_count_mismatch")
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ArchiveError(f"join_output_exists:{output}")
        logical = hashlib.sha256()
        try:
            with output.open("xb") as target:
                for index, raw in enumerate(parts):
                    part = Path(raw).resolve()
                    if not part.is_file():
                        raise ArchiveError(f"split_part_missing:{part}")
                    digest = hashlib.sha256()
                    with part.open("rb") as source:
                        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                            digest.update(chunk)
                            logical.update(chunk)
                            target.write(chunk)
                    if expected_sha256 is not None:
                        expected = str(expected_sha256[index]).lower()
                        if digest.hexdigest() != expected:
                            raise ArchiveError(f"split_part_sha256_mismatch:{part.name}")
            actual = logical.hexdigest()
            if logical_sha256 and actual != str(logical_sha256).lower():
                raise ArchiveError("logical_archive_sha256_mismatch")
            return actual
        except Exception:
            output.unlink(missing_ok=True)
            raise

    def entries_from_directory(self, source: Path) -> list[ArchiveWriteEntry]:
        source = Path(source).expanduser().resolve()
        if not source.is_dir():
            raise ArchiveError(f"archive_pack_source_not_directory:{source}")
        entries: list[ArchiveWriteEntry] = []
        for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().casefold()):
            if path.is_symlink():
                raise ArchiveError(f"archive_pack_symlink_rejected:{path}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ArchiveError(f"archive_pack_special_file_rejected:{path}")
            entries.append(ArchiveWriteEntry(path.relative_to(source).as_posix(), source=path))
        return entries
