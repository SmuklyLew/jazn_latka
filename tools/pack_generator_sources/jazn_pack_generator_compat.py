from __future__ import annotations

import argparse
import contextlib
import contextvars
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any, Iterator, Sequence
import uuid

from latka_jazn.archive.hardened_service import ArchiveExtractionService
from latka_jazn.archive.service import ArchiveSecurityLimits, ArchiveWriteEntry
from latka_jazn.packaging.memory_raw_segmentation import (
    RawJsonlSegmenter,
    RawMemorySegmentationPolicy,
)

PROFILE_CHOICES = ("system", "dual", "memory")
PACK_PROFILE_CHOICES = ("system", "dual", "memory", "combined")
PACKAGE_INTEGRITY_MANIFEST = "PACKAGE_INTEGRITY_MANIFEST.json"
SOURCE_PROVENANCE = "SOURCE_PROVENANCE.json"
MEMORY_PACKAGE_MANIFEST = "memory/MEMORY_PACKAGE_MANIFEST.json"
MEMORY_MANIFEST_SCHEMA = "jazn_memory_package_manifest/v3"
MEMORY_FORMAT_VERSION = 3
MEMORY_RAW_SEGMENT_TARGET_BYTES = int(
    os.environ.get("JAZN_MEMORY_PACKAGE_RAW_SEGMENT_BYTES", str(256 * 1024 * 1024))
)
MEMORY_RAW_SEGMENT_MAX_BYTES = int(
    os.environ.get("JAZN_MEMORY_PACKAGE_RAW_MEMBER_MAX_BYTES", str(480 * 1024 * 1024))
)
MEMORY_SQLITE_MEMBER_MAX_BYTES = int(
    os.environ.get("JAZN_MEMORY_PACKAGE_SQLITE_MEMBER_MAX_BYTES", str(480 * 1024 * 1024))
)
MEMORY_RUNTIME_COMPATIBILITY_CONTRACT = "jazn_memory_runtime/v1"
SQLITE_HEADER = b"SQLite format 3\x00"

_CORE: Any = None
_ARCHIVE_SETTINGS: contextvars.ContextVar["GeneratorArchiveSettings | None"] = contextvars.ContextVar(
    "jazn_pack_generator_archive_settings", default=None
)


def _pack_error(message: str) -> Exception:
    return _CORE.PackError(message)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class VersionInfo:
    version_file: Path
    package_version: str
    release_name: str
    full_version: str
    filename_version: str


@dataclass(frozen=True, slots=True)
class PlanEntry:
    relative: str
    source: Path | None
    size_bytes: int
    sha256: str
    classification: str = "file"
    mtime_ns: int = 0
    virtual_bytes: bytes | None = None

    @property
    def is_virtual(self) -> bool:
        return self.virtual_bytes is not None


@dataclass(slots=True)
class PackPlan:
    root: Path
    profile: str
    version: VersionInfo
    entries: list[PlanEntry]
    excluded: list[tuple[str, str]] = field(default_factory=list)
    scan_method: str = "filesystem"
    manifest_builder: str = "internal"
    generated_at_utc: str = field(default_factory=_utc_now)
    _temp_paths: list[Path] = field(default_factory=list, repr=False)

    @property
    def file_count(self) -> int:
        return len(self.entries)

    @property
    def total_bytes(self) -> int:
        return sum(int(item.size_bytes) for item in self.entries)

    @property
    def paths(self) -> list[str]:
        return [item.relative for item in self.entries]

    def cleanup(self) -> None:
        for path in self._temp_paths:
            shutil.rmtree(path, ignore_errors=True)
        self._temp_paths.clear()


@dataclass(slots=True)
class PackOptions:
    source: Path
    out_dir: Path
    profile: str = "dual"
    archive_format: str = "auto"
    archive_basename: str = "jazn_latka"
    part_size_mb: int = 400
    compression_level: int = 6
    force: bool = False
    base_excludes: list[str] = field(default_factory=list)
    custom_excludes: list[str] = field(default_factory=list)
    manual_excludes_enabled: bool = False
    sidecars: bool = True
    update_source_manifest: bool = True
    compatibility_checks: bool = True


@dataclass(frozen=True, slots=True)
class PackageResult:
    package_name: str
    package_path: Path
    sidecar_path: Path
    committed_paths: list[Path]


@dataclass(frozen=True, slots=True)
class GeneratorArchiveSettings:
    container_format: str = "zip"
    password_env: str | None = None
    aes_bits: int = 256
    max_members: int = 200_000
    max_total_uncompressed_bytes: int = 64 * 1024 * 1024 * 1024
    max_member_bytes: int = 16 * 1024 * 1024 * 1024
    max_compression_ratio: float = 500.0
    require_free_space: bool = True


def _read_assignment(text: str, name: str) -> str | None:
    match = re.search(
        rf"^\s*{re.escape(name)}\s*=\s*([\"\'])(.*?)\1\s*(?:#.*)?$",
        text,
        re.MULTILINE,
    )
    return match.group(2) if match else None


def parse_release(root: Path) -> tuple[str, str]:
    path = Path(root) / "latka_jazn" / "version.py"
    text = path.read_text(encoding="utf-8")
    version = _read_assignment(text, "PACKAGE_VERSION")
    release = _read_assignment(text, "PACKAGE_RELEASE_NAME") or ""
    if not version:
        raise _pack_error(f"Nie znaleziono PACKAGE_VERSION w {path}")
    return version, release


def compose_package_version_full(
    package_version: str,
    package_release_name: str | None = None,
) -> str:
    version = str(package_version or "").strip().lstrip("v")
    release = str(package_release_name or "").strip()
    if release:
        suffix = f"-{release}"
        if version.casefold().endswith(suffix.casefold()):
            return version
        return f"{version}{suffix}"
    return version


def manifest_version_matches(
    manifest_version: str,
    package_version: str,
    package_release_name: str | None = None,
) -> bool:
    expected = compose_package_version_full(package_version, package_release_name)
    observed = str(manifest_version or "").strip().lstrip("v")
    return observed.casefold() == expected.casefold()


def virtual_entry(relative: str, data: bytes, classification: str) -> PlanEntry:
    payload = bytes(data)
    return PlanEntry(
        relative=PurePosixPath(relative).as_posix(),
        source=None,
        size_bytes=len(payload),
        sha256=_CORE.sha256_bytes(payload),
        classification=classification,
        virtual_bytes=payload,
    )


def hash_source_entry(root: Path, relative: str, classification: str = "file") -> PlanEntry:
    source = (Path(root) / Path(*PurePosixPath(relative).parts)).resolve()
    stat_result = source.stat()
    return PlanEntry(
        relative=PurePosixPath(relative).as_posix(),
        source=source,
        size_bytes=stat_result.st_size,
        sha256=_CORE.sha256_file(source),
        classification=classification,
        mtime_ns=stat_result.st_mtime_ns,
    )


def validate_release_provenance_payload(
    payload: dict[str, object],
    version: VersionInfo,
    *,
    context: str = "SOURCE_PROVENANCE.json",
) -> None:
    expected = compose_package_version_full(version.package_version, version.release_name)
    mismatches: list[str] = []
    for key in ("base_version", "runtime_version", "update_version"):
        value = str(payload.get(key) or "").strip()
        if value and not manifest_version_matches(value, version.package_version, version.release_name):
            mismatches.append(f"{key}={value!r}")
    if mismatches:
        raise _pack_error(
            f"{context} nie odpowiada version.py ({expected}): " + ", ".join(mismatches)
        )
    source = str(payload.get("version_source") or "").strip()
    if source and source.replace("\\", "/") != "latka_jazn/version.py":
        raise _pack_error(f"{context} ma niekanoniczny version_source={source!r}")


def validate_system_plan_release_metadata(plan: PackPlan) -> None:
    rows = {item.relative: item for item in plan.entries}
    provenance = rows.get(SOURCE_PROVENANCE)
    manifest = rows.get(PACKAGE_INTEGRITY_MANIFEST)
    if provenance is None or manifest is None:
        raise _pack_error("Odmowa pakowania: brak kanonicznych metadanych wydania")
    if provenance.virtual_bytes is None or manifest.virtual_bytes is None:
        raise _pack_error(
            "Odmowa pakowania: metadane wydania muszą pochodzić z kanonicznego planu wirtualnego"
        )
    try:
        payload = json.loads(provenance.virtual_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _pack_error(f"Odmowa pakowania: SOURCE_PROVENANCE jest niepoprawny: {exc}")
    if not isinstance(payload, dict):
        raise _pack_error("Odmowa pakowania: SOURCE_PROVENANCE nie jest obiektem")
    validate_release_provenance_payload(payload, plan.version, context=SOURCE_PROVENANCE)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="jazn_pack_generator", allow_abbrev=False)
    commands = root.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack", allow_abbrev=False)
    pack.add_argument("source", nargs="?", default=".")
    pack.add_argument("--profile", choices=PACK_PROFILE_CHOICES, default="dual")
    pack.add_argument(
        "--container-format",
        choices=("zip", "7z", "aes_zip", "rar"),
        default="zip",
        dest="container_format",
    )
    pack.add_argument("--encrypt-7z", action="store_true", dest="encrypt_7z")
    pack.add_argument("--password-env", dest="archive_password_env")
    pack.add_argument("--extract-max-ratio", type=float, default=500.0, dest="archive_max_ratio")
    return root


def _version_info(root: Path) -> VersionInfo:
    package_version, release_name = parse_release(root)
    full = compose_package_version_full(package_version, release_name)
    return VersionInfo(
        version_file=Path("latka_jazn/version.py"),
        package_version=package_version,
        release_name=release_name,
        full_version=full,
        filename_version=full.lstrip("v").replace(" ", "-"),
    )


def build_plan(
    root: Path,
    profile: str,
    custom_excludes: Sequence[str],
    *,
    base_excludes: Sequence[str] | None = None,
    manual_excludes_enabled: bool = True,
    synchronize_release_metadata: bool = False,
) -> PackPlan:
    del base_excludes, manual_excludes_enabled, synchronize_release_metadata
    root = Path(root).resolve()
    version = _version_info(root)
    normalized = str(profile).strip().lower()
    if normalized == "memory":
        candidates = (
            [
                path.relative_to(root).as_posix()
                for path in sorted((root / "memory").rglob("*"))
                if path.is_file() and not path.name.endswith(("-wal", "-shm"))
            ]
            if (root / "memory").is_dir()
            else []
        )
        return build_memory_plan(root, version, candidates, [], "filesystem")

    entries: list[PlanEntry] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(("memory/", "workspace_runtime/", ".git/", ".venv/")):
            continue
        if any(Path(relative).match(pattern) for pattern in custom_excludes):
            continue
        if relative in {SOURCE_PROVENANCE, PACKAGE_INTEGRITY_MANIFEST}:
            continue
        entries.append(hash_source_entry(root, relative, "system_file"))
    provenance_path = root / SOURCE_PROVENANCE
    manifest_path = root / PACKAGE_INTEGRITY_MANIFEST
    if provenance_path.is_file():
        raw = json.loads(provenance_path.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            raw["base_version"] = version.full_version
            raw["runtime_version"] = version.full_version
            raw["update_version"] = version.full_version
            raw["version_source"] = "latka_jazn/version.py"
            entries.append(
                virtual_entry(
                    SOURCE_PROVENANCE,
                    (json.dumps(raw, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
                    "static_project_file",
                )
            )
    if manifest_path.is_file():
        entries.append(
            virtual_entry(
                PACKAGE_INTEGRITY_MANIFEST,
                manifest_path.read_bytes(),
                "package_integrity_manifest",
            )
        )
    return PackPlan(root=root, profile=normalized, version=version, entries=entries)


def build_plans_for_options(options: PackOptions) -> list[PackPlan]:
    profile = str(options.profile).strip().lower()
    profiles = ("system", "memory") if profile == "dual" else (profile,)
    return [
        _CORE.build_plan(
            Path(options.source).resolve(),
            item,
            options.custom_excludes,
            base_excludes=options.base_excludes,
            manual_excludes_enabled=options.manual_excludes_enabled,
            synchronize_release_metadata=True,
        )
        for item in profiles
    ]


def _is_sqlite_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def build_memory_plan(
    root: Path,
    version: VersionInfo,
    candidates: Sequence[str],
    excluded: list[tuple[str, str]],
    scan_method: str,
    *,
    independent_contract: bool | None = None,
) -> PackPlan:
    del independent_contract
    root = Path(root).resolve()
    target_bytes = int(getattr(_CORE, "MEMORY_RAW_SEGMENT_TARGET_BYTES", MEMORY_RAW_SEGMENT_TARGET_BYTES))
    max_raw_bytes = int(getattr(_CORE, "MEMORY_RAW_SEGMENT_MAX_BYTES", MEMORY_RAW_SEGMENT_MAX_BYTES))
    sqlite_max = int(getattr(_CORE, "MEMORY_SQLITE_MEMBER_MAX_BYTES", MEMORY_SQLITE_MEMBER_MAX_BYTES))
    entries: list[PlanEntry] = []
    raw_segments: list[dict[str, Any]] = []
    databases: list[dict[str, Any]] = []
    staging = Path(tempfile.mkdtemp(prefix="jazn-memory-package-v3-"))
    used_staging = False
    try:
        for relative in candidates:
            relative = PurePosixPath(relative).as_posix()
            if relative == MEMORY_PACKAGE_MANIFEST:
                continue
            source = root / Path(*PurePosixPath(relative).parts)
            if _is_sqlite_file(source):
                if source.stat().st_size > sqlite_max:
                    raise _pack_error(
                        f"SQLite member {relative} exceeds safe package limit; shard/roll the database before packaging"
                    )
                entries.append(hash_source_entry(root, relative, "memory_sqlite"))
                databases.append(
                    {
                        "path": relative,
                        "role": "sqlite_memory",
                        "snapshot_method": "source_file_compat",
                        "size_bytes": source.stat().st_size,
                        "sha256": _CORE.sha256_file(source),
                    }
                )
                continue
            if relative.lower().endswith(".jsonl") and source.stat().st_size > target_bytes:
                used_staging = True
                segmenter = RawJsonlSegmenter(
                    RawMemorySegmentationPolicy(
                        target_segment_bytes=target_bytes,
                        max_segment_bytes=max_raw_bytes,
                    )
                )
                segmented = segmenter.segment(source, source_relative=relative, staging_root=staging)
                raw_segments.append(segmented.to_dict())
                for segment in segmented.segments:
                    segment_source = staging / Path(*PurePosixPath(segment.package_path).parts)
                    stat_result = segment_source.stat()
                    entries.append(
                        PlanEntry(
                            relative=segment.package_path,
                            source=segment_source,
                            size_bytes=stat_result.st_size,
                            sha256=segment.sha256,
                            classification="memory_raw_segment",
                            mtime_ns=stat_result.st_mtime_ns,
                        )
                    )
                continue
            entries.append(hash_source_entry(root, relative, "memory_file"))

        files = [
            {
                "path": item.relative,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "classification": item.classification,
            }
            for item in sorted(entries, key=lambda row: row.relative)
        ]
        created = _utc_now()
        payload = {
            "schema_version": MEMORY_MANIFEST_SCHEMA,
            "memory_format_version": MEMORY_FORMAT_VERSION,
            "snapshot_id": str(uuid.uuid4()),
            "created_at_utc": created,
            "generated_at_utc": created,
            "created_with_runtime": version.full_version,
            "compatibility": {
                "contract": MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
                "runtime_version_is_provenance_only": True,
                "memory_format_version": MEMORY_FORMAT_VERSION,
                "manifest_schema": MEMORY_MANIFEST_SCHEMA,
            },
            "file_count": len(files),
            "files": files,
            "databases": databases,
            "raw_segments": raw_segments,
            "package_member_limit_bytes": max_raw_bytes,
            "excluded_files": [path for path, _ in excluded if path.startswith("memory/")],
        }
        entries.append(
            virtual_entry(
                MEMORY_PACKAGE_MANIFEST,
                (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
                "memory_package_manifest",
            )
        )
        plan = PackPlan(
            root=root,
            profile="memory",
            version=version,
            entries=sorted(entries, key=lambda row: row.relative),
            excluded=excluded,
            scan_method=scan_method,
            manifest_builder="independent_memory_contract_v3+raw_jsonl_segmentation",
        )
        if used_staging:
            plan._temp_paths.append(staging)
        else:
            shutil.rmtree(staging, ignore_errors=True)
        return plan
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def sidecar_payload(
    base_zip_name: str,
    plan: PackPlan,
    archive_format: str,
    part_size: int,
    compression_level: int,
    outputs: Sequence[dict[str, Any]],
    logical_zip_sha256: str | None,
    compatibility: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "jazn_package_set/v2",
        "package_name": base_zip_name,
        "profile": plan.profile,
        "archive_format": archive_format,
        "package_version": "memory-format-v3" if plan.profile == "memory" else plan.version.full_version,
        "runtime_version": plan.version.full_version,
        "part_size_bytes": int(part_size),
        "compression_level": int(compression_level),
        "outputs": list(outputs),
        "entries": [
            {
                "path": item.relative,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "classification": item.classification,
            }
            for item in plan.entries
        ],
        "logical_zip_sha256": logical_zip_sha256,
        "compatibility": compatibility,
    }
    if plan.profile == "memory":
        payload.update(
            {
                "memory_transport_contract": "jazn_memory_package_transport/v1",
                "cloud_attach_compatible": True,
                "cloud_object_layout": {"kind": "flat_package_set", "provider": "s3_compatible"},
            }
        )
    return payload


@contextlib.contextmanager
def archive_settings_override(settings: GeneratorArchiveSettings) -> Iterator[None]:
    token = _ARCHIVE_SETTINGS.set(settings)
    try:
        yield
    finally:
        _ARCHIVE_SETTINGS.reset(token)


def _archive_limits(settings: GeneratorArchiveSettings) -> ArchiveSecurityLimits:
    return ArchiveSecurityLimits(
        max_members=int(settings.max_members),
        max_total_uncompressed_bytes=int(settings.max_total_uncompressed_bytes),
        max_member_bytes=int(settings.max_member_bytes),
        max_compression_ratio=float(settings.max_compression_ratio),
        require_free_space=bool(settings.require_free_space),
    )


def _container_output_name(base_name: str, container: str) -> str:
    path = Path(base_name)
    if container == "7z":
        return path.with_suffix(".7z").name
    if container == "rar":
        return path.with_suffix(".rar").name
    return path.with_suffix(".zip").name


def package_one(plan: PackPlan, options: PackOptions, base_zip_name: str) -> PackageResult:
    settings = _ARCHIVE_SETTINGS.get() or GeneratorArchiveSettings()
    container = str(settings.container_format or "zip").strip().lower()
    if container == "rar":
        raise _pack_error(
            "RAR creation is not provided by rarfile; use the v10 distribution RAR backend with an external rar executable"
        )
    output_name = _container_output_name(base_zip_name, container)
    out_dir = Path(options.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / output_name
    if output_path.exists():
        if not options.force:
            raise _pack_error(f"Plik już istnieje: {output_path}")
        output_path.unlink()

    writes = [
        ArchiveWriteEntry(
            arcname=item.relative,
            source=item.source if item.virtual_bytes is None else None,
            data=item.virtual_bytes,
        )
        for item in plan.entries
    ]
    password = os.environ.get(settings.password_env) if settings.password_env else None
    service = ArchiveExtractionService(_archive_limits(settings))
    service.create_archive(
        writes,
        output_path,
        archive_format=container,
        compression_level=int(options.compression_level),
        password=password,
        aes_bits=int(settings.aes_bits),
    )
    digest = _CORE.sha256_file(output_path)
    output = {
        "part_no": 1,
        "filename": output_path.name,
        "size_bytes": output_path.stat().st_size,
        "sha256": digest,
        "is_complete_zip": container in {"zip", "aes_zip"},
    }
    encryption = {
        "method": (
            f"WZ_AES_{int(settings.aes_bits)}"
            if container == "aes_zip"
            else ("7Z_AES256" if container == "7z" and password else "none")
        ),
        "password_env": settings.password_env,
        "secret_persisted": False,
    }
    payload = sidecar_payload(
        output_path.name,
        plan,
        "independent",
        int(options.part_size_mb) * 1024 * 1024,
        int(options.compression_level),
        [output],
        None,
        {"ok": True},
    )
    payload.update(
        {
            "container_format": container,
            "archive_io_contract": "jazn_archive_io/v1",
            "encryption": encryption,
        }
    )
    sidecar_path = out_dir / f"{output_path.name}.package.json"
    sidecar_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return PackageResult(
        package_name=output_path.name,
        package_path=output_path,
        sidecar_path=sidecar_path,
        committed_paths=[output_path, sidecar_path],
    )


def extract_package_sidecar(sidecar_path: Path, destination: Path) -> dict[str, Any]:
    payload = json.loads(Path(sidecar_path).read_text(encoding="utf-8-sig"))
    encryption = payload.get("encryption") if isinstance(payload, dict) else None
    password_env = str(encryption.get("password_env") or "").strip() if isinstance(encryption, dict) else ""
    password = os.environ.get(password_env) if password_env else None
    limits = _archive_limits(_ARCHIVE_SETTINGS.get() or GeneratorArchiveSettings())
    service = ArchiveExtractionService(limits)
    return service.extract_package_sidecar(
        Path(sidecar_path),
        Path(destination),
        password=password,
        replace_existing=False,
    )


def _dashboard_available() -> bool:
    # v10 deliberately retired the prompt_toolkit dashboard. Keep the public
    # probe so historical callers can detect that fact without AttributeError.
    return False


def install(core: Any) -> None:
    global _CORE
    _CORE = core
    core._parse_release = parse_release
    exports = {
        "VersionInfo": VersionInfo,
        "PlanEntry": PlanEntry,
        "PackPlan": PackPlan,
        "PackOptions": PackOptions,
        "PackageResult": PackageResult,
        "GeneratorArchiveSettings": GeneratorArchiveSettings,
        "PROFILE_CHOICES": PROFILE_CHOICES,
        "PACK_PROFILE_CHOICES": PACK_PROFILE_CHOICES,
        "PACKAGE_INTEGRITY_MANIFEST": PACKAGE_INTEGRITY_MANIFEST,
        "SOURCE_PROVENANCE": SOURCE_PROVENANCE,
        "MEMORY_PACKAGE_MANIFEST": MEMORY_PACKAGE_MANIFEST,
        "MEMORY_MANIFEST_SCHEMA": MEMORY_MANIFEST_SCHEMA,
        "MEMORY_FORMAT_VERSION": MEMORY_FORMAT_VERSION,
        "MEMORY_RAW_SEGMENT_TARGET_BYTES": MEMORY_RAW_SEGMENT_TARGET_BYTES,
        "MEMORY_RAW_SEGMENT_MAX_BYTES": MEMORY_RAW_SEGMENT_MAX_BYTES,
        "MEMORY_SQLITE_MEMBER_MAX_BYTES": MEMORY_SQLITE_MEMBER_MAX_BYTES,
        "parser": parser,
        "compose_package_version_full": compose_package_version_full,
        "manifest_version_matches": manifest_version_matches,
        "virtual_entry": virtual_entry,
        "hash_source_entry": hash_source_entry,
        "validate_release_provenance_payload": validate_release_provenance_payload,
        "validate_system_plan_release_metadata": validate_system_plan_release_metadata,
        "build_plan": build_plan,
        "build_plans_for_options": build_plans_for_options,
        "build_memory_plan": build_memory_plan,
        "sidecar_payload": sidecar_payload,
        "archive_settings_override": archive_settings_override,
        "package_one": package_one,
        "extract_package_sidecar": extract_package_sidecar,
        "_dashboard_available": _dashboard_available,
    }
    for name, value in exports.items():
        setattr(core, name, value)
