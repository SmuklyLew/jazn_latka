from __future__ import annotations

from contextlib import contextmanager
from email.parser import Parser
import importlib
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Callable, Iterator, Mapping
import zipfile

from latka_jazn.packaging.zip_resource_limits import validate_zip_resources
from latka_jazn.tools.safe_paths import validate_safe_relative_path

from .common import DependencyStudioError, canonicalize_distribution_name


_ARCHIVE_SUFFIXES = (".zip", ".whl", ".egg")
_PACKAGING_MODULE_PREFIX = "packaging"
_REQUIRED_BOOTSTRAP_MODULES = (
    "packaging",
    "packaging.specifiers",
    "packaging.utils",
    "packaging.version",
)


def _module_origin(module: Any) -> str:
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None) or getattr(module, "__file__", None) or ""
    return str(origin)


def _origin_is_archive_backed(origin: str) -> bool:
    normalized = str(origin or "").replace("\\", "/").lower()
    return any(
        part.endswith(_ARCHIVE_SUFFIXES)
        for part in normalized.split("/")
        if part
    )


def _module_is_unpacked(module: Any) -> bool:
    origin = _module_origin(module)
    if not origin or _origin_is_archive_backed(origin):
        return False
    loader = getattr(getattr(module, "__spec__", None), "loader", None)
    loader_module = str(getattr(loader.__class__, "__module__", "")) if loader is not None else ""
    return loader_module != "zipimport"


def packaging_runtime_available() -> bool:
    """Return True only when the validator dependency is importable from unpacked files."""

    try:
        packaging = importlib.import_module("packaging")
        specifiers = importlib.import_module("packaging.specifiers")
        utils = importlib.import_module("packaging.utils")
        version = importlib.import_module("packaging.version")
    except ImportError:
        return False
    return all(_module_is_unpacked(module) for module in (packaging, specifiers, utils, version))


def _safe_bootstrap_member(info: zipfile.ZipInfo, *, dist_info_prefix: str) -> str | None:
    if info.is_dir():
        return None
    name = validate_safe_relative_path(info.filename)
    lowered = name.lower()
    if lowered.endswith(".pth"):
        raise DependencyStudioError(f"packaging bootstrap forbids .pth members: {name}")
    mode = (int(info.external_attr) >> 16) & 0o170000
    if mode not in (0, stat.S_IFREG):
        raise DependencyStudioError(f"packaging bootstrap forbids non-regular members: {name}")
    if not (name.startswith("packaging/") or name.startswith(dist_info_prefix)):
        raise DependencyStudioError(f"packaging bootstrap member outside packaging distribution: {name}")
    return name


def _bootstrap_row(manifest: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    resolved = manifest.get("resolved_distributions")
    files = manifest.get("files")
    if not isinstance(resolved, list) or not isinstance(files, list):
        raise DependencyStudioError("packaging bootstrap requires Wheelhouse v2 inventory")

    packaging_rows = [
        item for item in resolved
        if isinstance(item, Mapping)
        and canonicalize_distribution_name(str(item.get("name") or "")) == "packaging"
    ]
    if len(packaging_rows) != 1:
        raise DependencyStudioError(
            f"packaging bootstrap requires exactly one packaging distribution, found {len(packaging_rows)}"
        )
    resolved_row = packaging_rows[0]
    filename = str(resolved_row.get("filename") or "")
    if not filename or Path(filename).name != filename or not filename.lower().endswith(".whl"):
        raise DependencyStudioError("packaging bootstrap wheel filename is unsafe")

    file_rows = [
        item for item in files
        if isinstance(item, Mapping) and str(item.get("filename") or "") == filename
    ]
    if len(file_rows) != 1:
        raise DependencyStudioError("packaging bootstrap manifest file row is missing or duplicated")
    file_row = file_rows[0]

    for field in ("sha256", "size_bytes"):
        if str(file_row.get(field) or "") != str(resolved_row.get(field) or ""):
            raise DependencyStudioError(f"packaging bootstrap {field} differs between manifest inventories")
    return resolved_row, file_row


def _validate_bootstrap_wheel(
    directory: Path,
    manifest: Mapping[str, Any],
    *,
    sha256_file: Callable[[Path], str],
    record_verification: Callable[[zipfile.ZipFile, str], Mapping[str, Any]],
) -> tuple[Path, list[zipfile.ZipInfo], str]:
    resolved_row, file_row = _bootstrap_row(manifest)
    filename = str(resolved_row["filename"])
    wheel = directory / filename
    if not wheel.is_file() or wheel.is_symlink():
        raise DependencyStudioError("packaging bootstrap wheel is missing or not a regular file")
    try:
        expected_size = int(file_row.get("size_bytes", -1))
    except (TypeError, ValueError) as exc:
        raise DependencyStudioError("packaging bootstrap wheel size is invalid") from exc
    if wheel.stat().st_size != expected_size:
        raise DependencyStudioError("packaging bootstrap wheel size mismatch")
    expected_sha = str(file_row.get("sha256") or "").lower()
    if not expected_sha or sha256_file(wheel) != expected_sha:
        raise DependencyStudioError("packaging bootstrap wheel SHA-256 mismatch")

    declared_metadata = file_row.get("metadata") if isinstance(file_row.get("metadata"), Mapping) else {}
    declared_filename = (
        declared_metadata.get("filename")
        if isinstance(declared_metadata.get("filename"), Mapping)
        else {}
    )
    expected_version = str(resolved_row.get("version") or "")
    if not expected_version:
        raise DependencyStudioError("packaging bootstrap version is missing")
    if canonicalize_distribution_name(str(declared_filename.get("distribution") or "")) != "packaging":
        raise DependencyStudioError("packaging bootstrap declared filename distribution is not packaging")
    if str(declared_filename.get("version") or "") != expected_version:
        raise DependencyStudioError("packaging bootstrap declared filename version mismatch")

    try:
        with zipfile.ZipFile(wheel) as archive:
            validate_zip_resources(archive)
            bad = archive.testzip()
            if bad:
                raise DependencyStudioError(f"packaging bootstrap wheel CRC failed: {bad}")
            infos = archive.infolist()
            names = [info.filename for info in infos if not info.is_dir()]
            if len(names) != len(set(names)):
                raise DependencyStudioError("packaging bootstrap wheel contains duplicate members")
            metas = [name for name in names if name.endswith(".dist-info/METADATA")]
            wheels = [name for name in names if name.endswith(".dist-info/WHEEL")]
            records = [name for name in names if name.endswith(".dist-info/RECORD")]
            if len(metas) != 1 or len(wheels) != 1 or len(records) != 1:
                raise DependencyStudioError("packaging bootstrap wheel metadata layout is invalid")
            dist_info_prefix = metas[0][:-len("METADATA")]
            safe_names: list[str] = []
            for info in infos:
                safe = _safe_bootstrap_member(info, dist_info_prefix=dist_info_prefix)
                if safe is not None:
                    safe_names.append(safe)
            if "packaging/__init__.py" not in safe_names:
                raise DependencyStudioError("packaging bootstrap package root is missing")
            for required in ("packaging/utils.py", "packaging/specifiers.py", "packaging/version.py"):
                if required not in safe_names:
                    raise DependencyStudioError(f"packaging bootstrap required module is missing: {required}")

            metadata_message = Parser().parsestr(
                archive.read(metas[0]).decode("utf-8", errors="strict")
            )
            wheel_message = Parser().parsestr(
                archive.read(wheels[0]).decode("utf-8", errors="strict")
            )
            if canonicalize_distribution_name(str(metadata_message.get("Name") or "")) != "packaging":
                raise DependencyStudioError("packaging bootstrap METADATA Name is not packaging")
            if str(metadata_message.get("Version") or "") != expected_version:
                raise DependencyStudioError("packaging bootstrap METADATA Version mismatch")
            if str(declared_metadata.get("name") or "") and canonicalize_distribution_name(
                str(declared_metadata.get("name") or "")
            ) != "packaging":
                raise DependencyStudioError("packaging bootstrap manifest metadata Name mismatch")
            if str(declared_metadata.get("version") or "") != expected_version:
                raise DependencyStudioError("packaging bootstrap manifest metadata Version mismatch")
            if str(wheel_message.get("Root-Is-Purelib") or "").strip().lower() != "true":
                raise DependencyStudioError("packaging bootstrap wheel must be purelib")
            tags = {str(item).strip() for item in (wheel_message.get_all("Tag") or [])}
            if "py3-none-any" not in tags:
                raise DependencyStudioError("packaging bootstrap wheel must expose py3-none-any")
            record = record_verification(archive, records[0])
            if record.get("ok") is not True:
                raise DependencyStudioError("packaging bootstrap RECORD verification failed")
            return wheel, infos, dist_info_prefix
    except (OSError, UnicodeError, zipfile.BadZipFile) as exc:
        raise DependencyStudioError(f"packaging bootstrap wheel is unreadable: {exc}") from exc


def _under(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


@contextmanager
def unpacked_packaging_bootstrap(
    directory: Path,
    manifest: Mapping[str, Any],
    *,
    sha256_file: Callable[[Path], str],
    record_verification: Callable[[zipfile.ZipFile, str], Mapping[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Temporarily expose a verified packaging wheel only after safe unpacking.

    The wheel archive is never placed on ``sys.path`` and never imported from
    directly. Full Wheelhouse v2 verification remains the authoritative check.
    """

    directory = Path(directory).resolve()
    wheel, infos, dist_info_prefix = _validate_bootstrap_wheel(
        directory,
        manifest,
        sha256_file=sha256_file,
        record_verification=record_verification,
    )

    saved_modules = {
        name: module
        for name, module in list(sys.modules.items())
        if name == _PACKAGING_MODULE_PREFIX or name.startswith(_PACKAGING_MODULE_PREFIX + ".")
    }
    restorable_modules = {
        name: module for name, module in saved_modules.items() if _module_is_unpacked(module)
    }
    for name in saved_modules:
        sys.modules.pop(name, None)

    with tempfile.TemporaryDirectory(prefix="jazn-unpacked-packaging-") as temp_dir:
        extracted_root = Path(temp_dir).resolve()
        try:
            with zipfile.ZipFile(wheel) as archive:
                # Re-check the exact archive before extraction. The first pass proves
                # it is safe to inspect; this pass ensures extraction reads the same file.
                validate_zip_resources(archive)
                if archive.testzip() is not None:
                    raise DependencyStudioError("packaging bootstrap wheel changed before extraction")
                for info in infos:
                    safe = _safe_bootstrap_member(info, dist_info_prefix=dist_info_prefix)
                    if safe is None:
                        continue
                    destination = extracted_root.joinpath(*safe.split("/"))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(info.filename))

            path_text = str(extracted_root)
            if any(_origin_is_archive_backed(item) for item in (path_text,)):
                raise DependencyStudioError("packaging bootstrap extraction root is archive-backed")
            sys.path.insert(0, path_text)
            importlib.invalidate_caches()
            try:
                imported = [importlib.import_module(name) for name in _REQUIRED_BOOTSTRAP_MODULES]
                for module in imported:
                    origin = Path(_module_origin(module)).resolve()
                    if not _module_is_unpacked(module) or not _under(extracted_root, origin):
                        raise DependencyStudioError(
                            f"packaging bootstrap imported outside unpacked staging: {_module_origin(module)}"
                        )
                yield {
                    "mode": "verified_unpacked_packaging_bootstrap",
                    "wheel": wheel.name,
                    "extracted_root": str(extracted_root),
                }
            finally:
                while path_text in sys.path:
                    sys.path.remove(path_text)
                for name in list(sys.modules):
                    if name == _PACKAGING_MODULE_PREFIX or name.startswith(_PACKAGING_MODULE_PREFIX + "."):
                        sys.modules.pop(name, None)
                sys.modules.update(restorable_modules)
                importlib.invalidate_caches()
        finally:
            # TemporaryDirectory removes the unpacked bootstrap after all imports
            # and full verification are complete; no archive or deleted temp path
            # remains part of the runtime import graph.
            pass
