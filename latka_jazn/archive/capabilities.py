from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import metadata, util
from typing import Any

from latka_jazn.archive.rar_backend import rar_backend_status
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version


SCHEMA_VERSION = schema_version("archive_capability_matrix")


@dataclass(frozen=True, slots=True)
class ArchiveOperation:
    name: str
    available: bool
    backend: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArchiveFormatCapability:
    format: str
    family: str
    purpose: str
    aliases: tuple[str, ...]
    backend: str
    backend_kind: str
    backend_available: bool
    backend_version: str | None
    runtime_supported: bool
    operations: tuple[ArchiveOperation, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["aliases"] = list(self.aliases)
        payload["operations"] = [item.to_dict() for item in self.operations]
        payload["limitations"] = list(self.limitations)
        return payload


@dataclass(frozen=True, slots=True)
class ArchiveCapabilityReport:
    schema_version: str
    runtime_version: str
    archive_definition: str
    formats: tuple[ArchiveFormatCapability, ...]
    transport_capabilities: dict[str, Any]
    known_but_not_exposed: dict[str, Any]
    safety_policy: dict[str, Any]
    dependency_contract: dict[str, Any]
    truth_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runtime_version": self.runtime_version,
            "archive_definition": self.archive_definition,
            "formats": [item.to_dict() for item in self.formats],
            "transport_capabilities": dict(self.transport_capabilities),
            "known_but_not_exposed": dict(self.known_but_not_exposed),
            "safety_policy": dict(self.safety_policy),
            "dependency_contract": dict(self.dependency_contract),
            "truth_boundary": self.truth_boundary,
        }


def _module_available(name: str) -> bool:
    try:
        return util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _distribution_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _operation(name: str, available: bool, backend: str, reason: str | None = None) -> ArchiveOperation:
    return ArchiveOperation(
        name=name,
        available=bool(available),
        backend=backend,
        reason=None if available else reason,
    )


def _zip_capability() -> ArchiveFormatCapability:
    backend = "python.stdlib.zipfile"
    operations = tuple(
        _operation(name, True, backend)
        for name in ("detect", "inspect", "list", "integrity_test", "extract", "create", "decrypt_legacy_zip")
    ) + (
        _operation(
            "create_encrypted_zip",
            False,
            backend,
            "stdlib_zipfile_does_not_create_encrypted_zip; use aes_zip/pyzipper",
        ),
    )
    return ArchiveFormatCapability(
        format="zip",
        family="ZIP/ZIP64",
        purpose="Multi-file archive container with metadata and optional compression; ZIP64 extends size/count limits.",
        aliases=("zip", "zip64", "pyzip", "pyzipfile", "pyzip_file"),
        backend=backend,
        backend_kind="stdlib",
        backend_available=True,
        backend_version=None,
        runtime_supported=True,
        operations=operations,
        limitations=(
            "native multipart ZIP is not handled directly by zipfile",
            "AES-encrypted ZIP requires the aes_zip backend",
            "archive contents must pass Jaźń safety preflight before extraction",
        ),
    )


def _aes_zip_capability() -> ArchiveFormatCapability:
    module_ok = _module_available("pyzipper")
    version = _distribution_version("pyzipper") if module_ok else None
    backend = "pyzipper.AESZipFile"
    reason = "pyzipper_not_available_in_current_interpreter"
    operations = (
        _operation("detect", True, "python.stdlib.zipfile", None),
        *(
            _operation(name, module_ok, backend, reason)
            for name in ("inspect", "list", "integrity_test", "extract", "create", "encrypt", "decrypt")
        ),
    )
    return ArchiveFormatCapability(
        format="aes_zip",
        family="WinZip AES ZIP",
        purpose="ZIP container using WinZip-compatible AES encryption for protected archive contents.",
        aliases=("aes_zip", "aes-zip", "zip_aes"),
        backend=backend,
        backend_kind="required_external_dependency",
        backend_available=module_ok,
        backend_version=version,
        runtime_supported=module_ok,
        operations=operations,
        limitations=(
            "password is required for encrypted content",
            "password values must not be persisted in logs, sidecars, or command history by archive tooling",
            "enhanced runtime support depends on the optional archive plugin dependency pyzipper",
        ),
    )


def _seven_zip_capability() -> ArchiveFormatCapability:
    module_ok = _module_available("py7zr")
    version = _distribution_version("py7zr") if module_ok else None
    backend = "py7zr.SevenZipFile"
    reason = "py7zr_not_available_in_current_interpreter"
    operations = (
        _operation("detect", True, "7z_signature_probe", None),
        *(
            _operation(name, module_ok, backend, reason)
            for name in ("inspect", "list", "integrity_test", "extract", "create", "encrypt", "decrypt")
        ),
    )
    return ArchiveFormatCapability(
        format="7z",
        family="7-Zip",
        purpose="Multi-file archive container with strong compression and optional password-based encryption.",
        aliases=("7z", "sevenzip", "seven_zip"),
        backend=backend,
        backend_kind="required_external_dependency",
        backend_available=module_ok,
        backend_version=version,
        runtime_supported=module_ok,
        operations=operations,
        limitations=(
            "enhanced runtime support depends on the optional archive plugin dependency py7zr",
            "Jaźń validates normalized member paths/types/sizes before committing extracted content",
            "generic split/join transport is separate from native 7z multi-volume semantics",
        ),
    )


def _rar_capability() -> ArchiveFormatCapability:
    status = rar_backend_status()
    backend = "rarfile.RarFile"
    module_reason = "rarfile_not_available_in_current_interpreter"
    extract_reason = (
        module_reason
        if not status.module_available
        else "rarfile_requires_external_unrar_unar_7zip_or_bsdtar_for_compressed_payloads"
    )
    operations = (
        _operation("detect", True, "rar_signature_probe"),
        _operation("inspect", status.metadata_ready, backend, module_reason),
        _operation("list", status.metadata_ready, backend, module_reason),
        _operation("integrity_test", status.compressed_extract_ready, backend, extract_reason),
        _operation("extract", status.compressed_extract_ready, backend, extract_reason),
        _operation(
            "create",
            False,
            backend,
            "rarfile_is_read_only; Jaźń Pack Generator may use a separately detected external rar executable",
        ),
    )
    return ArchiveFormatCapability(
        format="rar",
        family="RAR3/RAR5",
        purpose="RAR3/RAR5 read, inspection and extraction through the canonical rarfile backend.",
        aliases=("rar", "rar3", "rar5"),
        backend=backend,
        backend_kind="optional_plugin_dependency_plus_external_decompressor",
        backend_available=status.module_available,
        backend_version=status.module_version,
        runtime_supported=status.metadata_ready,
        operations=operations,
        limitations=(
            "rarfile does not create RAR archives",
            "compressed RAR extraction requires a supported external backend such as unrar, unar, 7zip or bsdtar",
            "metadata parsing and uncompressed entries are handled in Python",
            "Jaźń rejects symlinks/special files and commits extraction through staging",
        ),
    )


def archive_capability_report() -> ArchiveCapabilityReport:
    formats = (_zip_capability(), _aes_zip_capability(), _seven_zip_capability(), _rar_capability())
    rar_status = rar_backend_status()
    return ArchiveCapabilityReport(
        schema_version=SCHEMA_VERSION,
        runtime_version=PACKAGE_VERSION_FULL,
        archive_definition=(
            "An archive is a container that groups one or more files plus metadata; it may also compress or encrypt "
            "their contents. A filename extension alone is not proof of the container type, so Jaźń uses signatures "
            "and structural parsing before archive operations."
        ),
        formats=formats,
        transport_capabilities={
            "binary_split_join": True,
            "sha256_verification_before_join_for_package_sidecars": True,
            "native_multipart_zip_via_stdlib": False,
            "note": "Binary split/join is a transport/layout capability, not a distinct archive container format.",
        },
        known_but_not_exposed={
            "tar": {
                "known": True,
                "python_stdlib_backend": "tarfile",
                "runtime_archive_service_supported": False,
                "reason": "not_exposed_by_jazn_archive_service; TAR extraction has separate link/metadata security semantics",
            },
            "gzip_bzip2_xz": {
                "known": True,
                "python_stdlib_backends": ["gzip", "bz2", "lzma"],
                "runtime_archive_service_supported": False,
                "reason": "compression_streams_are_not_current_jazn_multi_file_archive_containers",
            },
        },
        safety_policy={
            "inspect_before_extract": True,
            "reject_absolute_paths": True,
            "reject_parent_traversal": True,
            "reject_windows_reserved_names_and_ads": True,
            "reject_symlinks_by_default": True,
            "reject_special_files_by_default": True,
            "reject_casefold_collisions_by_default": True,
            "member_count_limit": True,
            "member_size_limit": True,
            "total_uncompressed_size_limit": True,
            "compression_ratio_limit": True,
            "free_space_preflight": True,
            "staging_before_commit": True,
            "atomic_destination_commit": True,
            "password_persistence": False,
        },
        dependency_contract={
            "profile": "archive",
            "profile_kind": "runtime_optional",
            "activation_required": False,
            "requirements": ["py7zr>=1.1.3,<2", "pyzipper>=0.4.0,<1", "rarfile>=4.5,<5"],
            "core_runtime_requirements": [],
            "rar_external_backends_detected": list(rar_status.external_backends),
            "rar_external_backend_required_for_compressed_extract": True,
            "stdlib_backends_are_not_pip_dependencies": ["zipfile", "tarfile", "gzip", "bz2", "lzma"],
        },
        truth_boundary=(
            "This report distinguishes knowledge of an archive format from executable support. "
            "Baseline ZIP support is stdlib-only. Enhanced AES ZIP, 7z and RAR support belongs to the optional archive "
            "capability. RAR metadata requires rarfile and compressed extraction additionally requires a supported external "
            "decompressor. Missing optional archive backends never proves core runtime failure."
        ),
    )


def archive_format_capability(name: str) -> dict[str, Any] | None:
    normalized = str(name or "").strip().lower().replace(" ", "_")
    for item in archive_capability_report().formats:
        if normalized == item.format or normalized in item.aliases:
            return item.to_dict()
    return None
