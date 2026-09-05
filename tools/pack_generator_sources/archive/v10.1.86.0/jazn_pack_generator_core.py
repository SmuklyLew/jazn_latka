from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Iterable, Mapping, Sequence
import zipfile

from latka_jazn.dependencies.common import (
    default_wheelhouse_root,
    target_is_current_host,
    target_spec,
)
from latka_jazn.dependencies.wheelhouse import discover_bundles
from latka_jazn.version import PACKAGE_VERSION_FULL

GENERATOR_VERSION = "10.1.86.0"
GENERATOR_TITLE = "Generator dystrybucji Jaźni"
SETTINGS_SCHEMA = "jazn_pack_generator_settings/v10.1.86.0"

CONTENT_CHOICES = ("system", "memory", "system+memory")
LAYOUT_CHOICES = ("single", "separate")
ARCHIVE_FORMAT_CHOICES = ("zip", "split-zip", "7z", "tar", "rar")
DISTRIBUTION_MODE_CHOICES = (
    "system-thin",
    "system-portable",
    "memory-only",
    "dependencies-only",
    "system+memory",
    "system+memory+dependencies",
)
DISTRIBUTION_TARGET_CHOICES = ("current", "windows-x64", "linux-x64")
DISTRIBUTION_PYTHON_CHOICES = ("current", "3.12", "3.13", "3.13.5", "3.14")
MANAGED_PYTHON_RESOURCE_EXCLUDE = "latka_jazn/local_resources/python/**"

HARD_EXCLUDE_GLOBS = (
    ".git/**", ".hg/**", ".svn/**", ".codex/**", ".vscode/**", ".archives/**",
    ".venv/**", "venv/**", "__pycache__/**", ".pytest_cache/**", ".pytest-tmp/**",
    ".mypy_cache/**", ".ruff_cache/**", "*.pyc", "*.pyo", "*.egg-info/**",
    "workspace_runtime/**", "processed/**", "requests/**", "responses/**",
    "status/**", "logs/**", "log/**", "CHECKPOINTS/**", "checkpoints/**",
    "backups/**", "backups_git/**", "exports/**", "tmp/**", "temp/**",
    "latka_jazn/core/canon/local_private_canon_extension.py",
    "latka_jazn/local_resources/**",
    "*.sqlite-wal", "*.sqlite-shm", "*.sqlite3-wal", "*.sqlite3-shm",
    "*.db-wal", "*.db-shm", "*-wal", "*-shm", "*.tmp", "*.temp", "*.bak",
    "*.bad", "*.corrupt", "*.partial", "*.log",
    "jazn_pack_generator_settings.json", "__jazn_pack_generator_settings.json",
    "__jazn_pack_generator.lock.json", "memory_rebuild_settings.json",
    "root_scanner_*.txt", "*_root_scan*.txt",
)

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class PackError(RuntimeError):
    """User-facing packaging failure."""


@dataclass(slots=True)
class PlanEntry:
    relative: str
    source: Path | None
    size_bytes: int
    sha256: str
    classification: str = "file"
    virtual_bytes: bytes | None = None


@dataclass(slots=True)
class InteractiveState:
    source: Path = field(default_factory=Path.cwd)
    out_dir: Path = field(default_factory=lambda: default_output_dir())
    archive_basename: str = ""


@dataclass(frozen=True, slots=True)
class GeneratorRequest:
    source: str
    out_dir: str
    content: str
    layout: str
    archive_format: str
    split_size_mib: int
    target_alias: str
    python_version: str
    dependency_bundle: str | None
    materialize_dependencies: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_output_dir() -> Path:
    if os.name == "nt":
        return Path(r"D:\.AI\jazn_packages")
    return (Path.home() / "jazn_packages").resolve()


def _settings_path() -> Path:
    explicit = str(os.environ.get("JAZN_PACK_GENERATOR_SETTINGS") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    adjacent = Path(__file__).resolve().with_name("jazn_pack_generator_settings.json")
    if adjacent.is_file():
        return adjacent
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "Latka" / "JaznPackGenerator" / "settings-v10.1.86.0.json"
    return (
        Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
        / "latka"
        / "jazn-pack-generator-v10.1.86.0.json"
    )


def load_settings() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "schema_version": SETTINGS_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "ui_mode": "studio-terminal",
        "source": str(Path.cwd()),
        "out_dir": str(default_output_dir()),
        "content": "system",
        "layout": "single",
        "archive_format": "zip",
        "split_size_mib": 480,
        "target_alias": "current",
        "python_version": "current",
        "dependency_bundle": "",
        "materialize_dependencies": False,
    }
    path = _settings_path()
    if not path.is_file():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if isinstance(raw, dict):
        defaults.update({key: value for key, value in raw.items() if key in defaults})
    defaults["schema_version"] = SETTINGS_SCHEMA
    defaults["generator_version"] = GENERATOR_VERSION
    return defaults


def save_settings(**updates: Any) -> dict[str, Any]:
    payload = load_settings()
    payload.update(updates)
    if payload["content"] not in CONTENT_CHOICES:
        raise ValueError(f"unsupported content: {payload['content']!r}")
    if payload["layout"] not in LAYOUT_CHOICES:
        raise ValueError(f"unsupported layout: {payload['layout']!r}")
    if payload["archive_format"] not in ARCHIVE_FORMAT_CHOICES:
        raise ValueError(f"unsupported archive format: {payload['archive_format']!r}")
    if payload["target_alias"] not in DISTRIBUTION_TARGET_CHOICES:
        raise ValueError(f"unsupported target: {payload['target_alias']!r}")
    normalize_distribution_python_version(str(payload["python_version"]))
    payload["split_size_mib"] = max(1, int(payload["split_size_mib"]))
    payload["schema_version"] = SETTINGS_SCHEMA
    payload["generator_version"] = GENERATOR_VERSION
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return payload


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _parse_release(root: Path) -> tuple[str, str]:
    path = root / "latka_jazn" / "version.py"
    text = path.read_text(encoding="utf-8")
    version_match = re.search(r'^PACKAGE_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    release_match = re.search(r'^PACKAGE_RELEASE_NAME\s*=\s*"([^"]*)"', text, re.MULTILINE)
    if not version_match:
        raise PackError(f"Nie znaleziono PACKAGE_VERSION w {path}")
    return version_match.group(1), release_match.group(1) if release_match else ""


def refresh_archive_basename_for_current_release(state: InteractiveState) -> bool:
    version, release = _parse_release(Path(state.source).resolve())
    expected = f"jazn_latka_v{version}" + (f"-{release}" if release else "")
    current = str(state.archive_basename or "")
    if not current or (current.startswith("jazn_latka_v") and current != expected):
        state.archive_basename = expected
        return True
    return False


def validate_portable_member_names(plan: Any) -> None:
    seen: dict[str, str] = {}
    for entry in getattr(plan, "entries", ()):
        raw = str(getattr(entry, "relative", "")).replace("\\", "/")
        path = PurePosixPath(raw)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise PackError(f"Niebezpieczna ścieżka archiwum: {raw}")
        for part in path.parts:
            stem = part.rstrip(" .").split(".", 1)[0].upper()
            if stem in _WINDOWS_RESERVED:
                raise PackError(f"Nazwa zarezerwowana w Windows: {raw}")
            if ":" in part:
                raise PackError(f"Niedozwolony znak ':' / ADS w nazwie: {raw}")
        key = raw.casefold()
        previous = seen.get(key)
        if previous is not None and previous != raw:
            raise PackError(f"Kolizja nazw bez rozróżnienia wielkości liter: {previous!r} vs {raw!r}")
        seen[key] = raw


def interoperability_profile(container: str, split_mode: str) -> dict[str, Any]:
    c = str(container).strip().lower()
    s = str(split_mode).strip().lower()
    if c == "zip" and s == "binary":
        return {
            "portable_standard_zip": False,
            "requires_join": True,
            "targets": {"windows_11_file_explorer": "join_required", "python_zipfile": "join_required"},
        }
    if c == "zip" and s == "independent":
        return {
            "portable_standard_zip": True,
            "requires_join": False,
            "targets": {"windows_11_file_explorer": "direct", "python_zipfile": "direct"},
        }
    return {
        "portable_standard_zip": c == "zip",
        "requires_join": False,
        "targets": {"windows_11_file_explorer": "unknown", "python_zipfile": "unknown"},
    }


def write_zip_file(target: Path | str, entries: Iterable[PlanEntry], compression_level: int = 6) -> Path:
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries_tuple = tuple(entries)
    validate_portable_member_names(type("_Plan", (), {"entries": entries_tuple})())
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=max(0, min(9, int(compression_level))),
        allowZip64=True,
    ) as archive:
        for entry in entries_tuple:
            arcname = str(PurePosixPath(entry.relative))
            if entry.virtual_bytes is not None:
                archive.writestr(arcname, entry.virtual_bytes)
            elif entry.source is not None:
                archive.write(entry.source, arcname)
            else:
                raise PackError(f"PlanEntry bez źródła danych: {entry.relative}")
    with zipfile.ZipFile(path, "r") as archive:
        bad = archive.testzip()
    if bad is not None:
        raise PackError(f"Test CRC ZIP nie powiódł się dla: {bad}")
    return path


def normalize_distribution_python_version(value: str | None) -> str:
    raw = str(value or "current").strip().lower()
    if raw in {"", "current"}:
        return f"{sys.version_info.major}.{sys.version_info.minor}"
    parts = raw.split(".")
    if len(parts) not in {2, 3} or any(not item.isdigit() for item in parts):
        raise ValueError(f"invalid Python version: {value!r}")
    return f"{int(parts[0])}.{int(parts[1])}"


def current_distribution_target_alias() -> str:
    if os.name == "nt":
        return "windows-x64"
    if sys.platform.startswith("linux"):
        return "linux-x64"
    raise RuntimeError("Current host platform is not a supported Jaźń dependency release target.")


def resolve_distribution_target_alias(value: str | None) -> str:
    raw = str(value or "current").strip().lower()
    if raw == "current":
        return current_distribution_target_alias()
    if raw not in DISTRIBUTION_TARGET_CHOICES:
        raise ValueError(f"unsupported distribution target: {value!r}")
    return raw


def canonical_dependency_lock_path(source: Path | str, target_alias: str, python_version: str) -> Path:
    source_root = Path(source).expanduser().resolve()
    target = resolve_distribution_target_alias(target_alias)
    python_minor = normalize_distribution_python_version(python_version)
    return (
        source_root / "latka_jazn" / "resources" / "dependencies" / "locks" / "core+archive"
        / f"{target}-py{python_minor.replace('.', '')}.txt"
    ).resolve()


def distribution_mode_plan(
    mode: str,
    *,
    target_alias: str | None = None,
    python_version: str | None = None,
) -> dict[str, Any]:
    normalized = str(mode or "").strip().lower()
    if normalized not in DISTRIBUTION_MODE_CHOICES:
        raise ValueError(f"unsupported distribution mode: {mode!r}")
    include_system = normalized in {"system-thin", "system-portable", "system+memory", "system+memory+dependencies"}
    include_memory = normalized in {"memory-only", "system+memory", "system+memory+dependencies"}
    include_dependencies = normalized in {"dependencies-only", "system-portable", "system+memory+dependencies"}
    requested_target = str(target_alias or "current").strip().lower()
    target = resolve_distribution_target_alias(requested_target) if include_dependencies else requested_target
    requested_python = str(python_version or "current").strip()
    resolved_python = normalize_distribution_python_version(requested_python)
    return {
        "schema_version": "jazn_pack_generator_distribution_plan/v3",
        "generator_version": GENERATOR_VERSION,
        "mode": normalized,
        "system": include_system,
        "memory": include_memory,
        "dependencies": include_dependencies,
        "target_runtime": (
            {
                "alias": target,
                "requested_alias": requested_target,
                "python_version": resolved_python,
                "requested_python_version": requested_python,
            }
            if include_dependencies
            else None
        ),
    }


def _bundle_manifest(path: Path) -> dict[str, Any] | None:
    manifest = path / "JAZN_WHEELHOUSE_MANIFEST.json"
    if not manifest.is_file():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def dependency_wheelhouse_root(source: Path | str) -> Path:
    explicit = str(os.environ.get("JAZN_DEPENDENCY_WHEELHOUSE") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return default_wheelhouse_root(Path(source).expanduser().resolve())


def find_matching_dependency_bundle(source: Path | str, target_alias: str, python_version: str) -> Path | None:
    source_root = Path(source).expanduser().resolve()
    target = resolve_distribution_target_alias(target_alias)
    python_minor = normalize_distribution_python_version(python_version)
    bundles = discover_bundles(
        source_root,
        wheelhouse_root=dependency_wheelhouse_root(source_root),
        required_profiles=("core", "archive"),
        python_version=python_minor,
        platform_alias=target,
        verify=True,
    )
    for candidate in bundles:
        verification = candidate.get("verification")
        if isinstance(verification, Mapping) and verification.get("ok") is True:
            return Path(str(candidate["bundle_dir"])).resolve()
    return None


def _run_json(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        list(command), cwd=str(cwd), env=env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"command failed ({result.returncode}): {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not return JSON: {result.stdout[-2000:]}") from exc
    if not isinstance(payload, dict) or payload.get("ok") is False:
        raise RuntimeError(f"command reported failure: {payload}")
    return payload


def dependency_materialization_mode(
    source: Path | str,
    *,
    target_alias: str,
    python_version: str,
) -> str:
    source_root = Path(source).expanduser().resolve()
    target = resolve_distribution_target_alias(target_alias)
    python_minor = normalize_distribution_python_version(python_version)
    descriptor = target_spec(target, python_minor)
    lock_path = canonical_dependency_lock_path(source_root, target, python_minor)
    if target_is_current_host(descriptor):
        return "native-locked" if lock_path.is_file() else "native-resolve"
    return "cross-target-locked" if lock_path.is_file() else "cross-target-lock-missing"


def materialize_dependency_bundle(
    source: Path | str,
    *,
    target_alias: str,
    python_version: str,
) -> Path:
    source_root = Path(source).expanduser().resolve()
    target = resolve_distribution_target_alias(target_alias)
    python_minor = normalize_distribution_python_version(python_version)
    descriptor = target_spec(target, python_minor)
    native = target_is_current_host(descriptor)
    wheelhouse_root = dependency_wheelhouse_root(source_root)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(source_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    lock_path = canonical_dependency_lock_path(source_root, target, python_minor)
    if not native and not lock_path.is_file():
        raise RuntimeError(
            f"Brak kanonicznego locka cross-target dla {target}/py{python_minor}: {lock_path}"
        )
    command = [
        sys.executable, "-X", "utf8", "-m", "latka_jazn.tools.dependency_studio",
        "--root", str(source_root), "--wheelhouse-root", str(wheelhouse_root), "--json",
        "download", "--profile", "core", "--profile", "archive",
        "--python-version", python_minor, "--platform", target,
    ]
    if lock_path.is_file():
        command += ["--lock-file", str(lock_path)]
    report = _run_json(command, cwd=source_root, env=env)
    bundle = Path(str(report.get("bundle_dir") or "")).resolve()
    manifest = _bundle_manifest(bundle)
    if manifest is None:
        raise RuntimeError(f"materialized dependency bundle lacks manifest: {bundle}")
    raw_target = manifest.get("target")
    target_data = raw_target if isinstance(raw_target, Mapping) else {}
    if str(target_data.get("alias") or "").strip().lower() != target:
        raise RuntimeError("materialized dependency bundle target mismatch")
    if normalize_distribution_python_version(str(target_data.get("python_version") or "")) != python_minor:
        raise RuntimeError("materialized dependency bundle Python mismatch")
    return bundle


def materialize_native_dependency_bundle(
    source: Path | str,
    *,
    target_alias: str,
    python_version: str,
) -> Path:
    """Compatibility alias for callers of the retired v10.0.1 API."""

    return materialize_dependency_bundle(
        source,
        target_alias=target_alias,
        python_version=python_version,
    )


def run_distribution_pack(
    *,
    source: Path | str,
    out_dir: Path | str,
    mode: str,
    target_alias: str = "current",
    python_version: str = "current",
    dependency_bundle: Path | str | None = None,
    materialize_dependencies: bool = False,
) -> dict[str, Any]:
    source_root = Path(source).expanduser().resolve()
    destination = Path(out_dir).expanduser().resolve()
    plan = distribution_mode_plan(mode, target_alias=target_alias, python_version=python_version)
    target = resolve_distribution_target_alias(target_alias)
    python_minor = normalize_distribution_python_version(python_version)
    bundle: Path | None = None
    if plan["dependencies"]:
        if dependency_bundle:
            bundle = Path(dependency_bundle).expanduser().resolve()
        else:
            bundle = find_matching_dependency_bundle(source_root, target, python_minor)
        if bundle is None and materialize_dependencies:
            bundle = materialize_dependency_bundle(
                source_root,
                target_alias=target,
                python_version=python_minor,
            )
        if bundle is None:
            raise PackError(
                f"Brak zweryfikowanego dependency bundle dla {target}/py{python_minor}. "
                "Wskaż bundle albo włącz target-aware materializację zależności."
            )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(source_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    command = [
        sys.executable, "-X", "utf8", "-m", "latka_jazn.tools.package_distribution",
        "--root", str(source_root), "--output-dir", str(destination), "--mode", str(mode), "--json",
    ]
    if plan["dependencies"]:
        command += [
            "--target", target, "--python-version", python_minor,
            "--dependency-bundle", str(bundle),
        ]
    report = _run_json(command, cwd=source_root, env=env)
    package_set = report.get("package_set")
    if not isinstance(package_set, dict) or package_set.get("schema_version") != "jazn_package_set/v3":
        raise RuntimeError("canonical package-distribution command did not produce jazn_package_set/v3")
    return report


def _validate_output_location(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise PackError("Katalog wynikowy nie może być katalogiem źródłowym.")
    try:
        destination.relative_to(source)
    except ValueError:
        return
    raise PackError("Katalog wynikowy nie może znajdować się wewnątrz repozytorium źródłowego.")


def distribution_request_plan(
    *,
    content: str,
    layout: str,
    archive_format: str,
    source: Path | str | None = None,
    target_alias: str = "current",
    python_version: str = "current",
) -> dict[str, Any]:
    normalized_content = str(content).strip().lower()
    normalized_layout = str(layout).strip().lower()
    normalized_format = str(archive_format).strip().lower()
    if normalized_content not in CONTENT_CHOICES:
        raise ValueError(f"unsupported content: {content!r}")
    if normalized_layout not in LAYOUT_CHOICES:
        raise ValueError(f"unsupported layout: {layout!r}")
    if normalized_format not in ARCHIVE_FORMAT_CHOICES:
        raise ValueError(f"unsupported archive format: {archive_format!r}")
    if normalized_content != "system+memory":
        normalized_layout = "single"
    if normalized_content == "system":
        jobs = (("system", "system-portable"),)
    elif normalized_content == "memory":
        jobs = (("memory", "memory-only"),)
    elif normalized_layout == "single":
        jobs = (("system+memory", "system+memory+dependencies"),)
    else:
        jobs = (("system", "system-portable"), ("memory", "memory-only"))
    return {
        "schema_version": "jazn_pack_generator_request_plan/v2",
        "generator_version": GENERATOR_VERSION,
        "generator_title": GENERATOR_TITLE,
        "content": normalized_content,
        "layout": normalized_layout,
        "archive_format": normalized_format,
        "jobs": [{"role": role, "distribution_mode": mode} for role, mode in jobs],
        "system_dependencies_included": normalized_content in {"system", "system+memory"},
        "dependency_materialization": (
            {
                "target": resolve_distribution_target_alias(target_alias),
                "python_version": normalize_distribution_python_version(python_version),
                "mode": dependency_materialization_mode(
                    source or Path.cwd(),
                    target_alias=target_alias,
                    python_version=python_version,
                ),
            }
            if normalized_content in {"system", "system+memory"}
            else None
        ),
        "memory_export_is_canonical": normalized_content in {"memory", "system+memory"},
        "hard_excludes": list(HARD_EXCLUDE_GLOBS),
        "local_private_canon_extension_in_system": False,
    }


def _safe_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or normalized.startswith("/") or any(part in {"", ".", ".."} for part in path.parts):
        raise PackError(f"Niebezpieczna ścieżka w archiwum: {name}")
    if path.parts and re.match(r"^[A-Za-z]:", path.parts[0]):
        raise PackError(f"Bezwzględna ścieżka Windows w archiwum: {name}")
    return str(path)


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _archive_zip_directory(source_dir: Path, target: Path) -> None:
    entries: list[PlanEntry] = []
    for path in sorted(item for item in source_dir.rglob("*") if item.is_file()):
        entries.append(
            PlanEntry(
                relative=path.relative_to(source_dir).as_posix(),
                source=path,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
                classification="transport",
            )
        )
    write_zip_file(target, entries, 6)


def _archive_7z_directory(source_dir: Path, target: Path) -> None:
    try:
        import py7zr  # type: ignore
    except ImportError as exc:
        raise PackError("Format 7z wymaga biblioteki py7zr.") from exc
    with py7zr.SevenZipFile(target, "w") as archive:
        for path in sorted(item for item in source_dir.rglob("*") if item.is_file()):
            archive.write(path, arcname=path.relative_to(source_dir).as_posix())


def _archive_tar_directory(source_dir: Path, target: Path) -> None:
    with tarfile.open(target, "w") as archive:
        for path in sorted(source_dir.rglob("*")):
            relative = path.relative_to(source_dir).as_posix()
            if relative:
                archive.add(path, arcname=relative, recursive=False)


def _rar_executable() -> str | None:
    candidates = [shutil.which("rar")]
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidates.append(str(Path(base) / "WinRAR" / "rar.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    return None


def _archive_rar_directory(source_dir: Path, target: Path) -> None:
    executable = _rar_executable()
    if not executable:
        raise PackError("Tworzenie RAR wymaga zewnętrznego rar.exe/rar; rarfile jest biblioteką odczytu.")
    result = subprocess.run(
        [executable, "a", "-r", "-ep1", str(target), "*"],
        cwd=str(source_dir), check=False, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise PackError(result.stderr.strip() or result.stdout.strip() or "rar.exe zakończył się błędem")


def archive_backend_status() -> dict[str, Any]:
    try:
        import py7zr  # noqa: F401
        seven = True
    except ImportError:
        seven = False
    try:
        import pyzipper  # noqa: F401
        aes_zip = True
    except ImportError:
        aes_zip = False
    try:
        import rarfile  # noqa: F401
        rar_read = True
    except ImportError:
        rar_read = False
    rar_create = _rar_executable()
    return {
        "zip": {"create": True, "extract": True, "backend": "python.stdlib.zipfile"},
        "split-zip": {"create": True, "extract": True, "backend": "binary transport + zipfile"},
        "aes-zip": {"create": aes_zip, "extract": aes_zip, "backend": "pyzipper"},
        "7z": {"create": seven, "extract": seven, "backend": "py7zr"},
        "tar": {"create": True, "extract": True, "backend": "python.stdlib.tarfile"},
        "rar": {
            "create": bool(rar_create), "extract": rar_read,
            "backend": "rar.exe/rar for create; rarfile + external decompressor for extract",
            "rar_executable": rar_create,
        },
    }


def _split_binary_file(path: Path, part_size_bytes: int, *, remove_original: bool = True) -> dict[str, Any]:
    if part_size_bytes <= 0:
        raise ValueError("part_size_bytes must be positive")
    logical_sha = hashlib.sha256()
    parts: list[dict[str, Any]] = []
    with path.open("rb") as source:
        index = 1
        while True:
            chunk = source.read(part_size_bytes)
            if not chunk:
                break
            logical_sha.update(chunk)
            part = path.with_name(f"{path.name}.{index:03d}")
            part.write_bytes(chunk)
            parts.append({"filename": part.name, "size_bytes": len(chunk), "sha256": sha256_bytes(chunk)})
            index += 1
    if not parts:
        raise PackError(f"Nie utworzono części dla {path}")
    sidecar = path.with_name(path.name + ".parts.sha256")
    lines = [f"logical_sha256  {logical_sha.hexdigest()}", f"logical_filename  {path.name}"]
    lines.extend(f"{item['sha256']}  {item['filename']}" for item in parts)
    sidecar.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if remove_original:
        path.unlink()
    return {
        "logical_filename": path.name,
        "logical_sha256": logical_sha.hexdigest(),
        "part_size_bytes": part_size_bytes,
        "parts": parts,
        "sidecar": sidecar.name,
    }


def _split_parts_for(first_part: Path) -> tuple[Path, list[Path]]:
    match = re.match(r"^(?P<base>.+\.zip)\.(?P<index>\d{3})$", first_part.name, flags=re.IGNORECASE)
    if not match:
        raise PackError("Oczekiwano pierwszej części w postaci *.zip.001")
    if match.group("index") != "001":
        raise PackError("Rozpakowanie split ZIP rozpocznij od części .001")
    base = first_part.with_name(match.group("base"))
    parts: list[Path] = []
    index = 1
    while True:
        candidate = base.with_name(f"{base.name}.{index:03d}")
        if not candidate.exists():
            break
        parts.append(candidate)
        index += 1
    if not parts:
        raise PackError("Nie znaleziono części split ZIP")
    return base, parts


def join_split_zip(first_part: Path | str, target: Path | str | None = None) -> Path:
    first = Path(first_part).resolve()
    base, parts = _split_parts_for(first)
    destination = Path(target).resolve() if target else base
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".join.tmp")
    digest = hashlib.sha256()
    with temp.open("wb") as output:
        for part in parts:
            with part.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    output.write(chunk)
    sidecar = base.with_name(base.name + ".parts.sha256")
    if sidecar.is_file():
        first_line = sidecar.read_text(encoding="utf-8-sig").splitlines()[0].split()
        if len(first_line) >= 2 and first_line[0] == "logical_sha256" and digest.hexdigest() != first_line[1]:
            temp.unlink(missing_ok=True)
            raise PackError("SHA-256 złączonego ZIP-a nie zgadza się z sidecarem.")
    os.replace(temp, destination)
    return destination


def _transport_extension(archive_format: str) -> str:
    return {"zip": ".zip", "split-zip": ".zip", "7z": ".7z", "tar": ".tar", "rar": ".rar"}[archive_format]


def _build_transport(source_dir: Path, target: Path, archive_format: str, split_size_mib: int) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    if archive_format in {"zip", "split-zip"}:
        _archive_zip_directory(source_dir, target)
    elif archive_format == "7z":
        _archive_7z_directory(source_dir, target)
    elif archive_format == "tar":
        _archive_tar_directory(source_dir, target)
    elif archive_format == "rar":
        _archive_rar_directory(source_dir, target)
    else:
        raise ValueError(archive_format)
    result: dict[str, Any] = {
        "filename": target.name,
        "sha256": sha256_file(target),
        "size_bytes": target.stat().st_size,
        "archive_format": archive_format,
    }
    if archive_format == "split-zip":
        result["split"] = _split_binary_file(target, int(split_size_mib) * 1024 * 1024, remove_original=True)
        result["filename"] = None
    return result


def run_pack_request(
    *,
    source: Path | str,
    out_dir: Path | str,
    content: str = "system",
    layout: str = "single",
    archive_format: str = "zip",
    split_size_mib: int = 480,
    target_alias: str = "current",
    python_version: str = "current",
    dependency_bundle: Path | str | None = None,
    materialize_dependencies: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    source_root = Path(source).expanduser().resolve()
    output_root = Path(out_dir).expanduser().resolve()
    _validate_output_location(source_root, output_root)
    plan = distribution_request_plan(
        content=content,
        layout=layout,
        archive_format=archive_format,
        source=source_root,
        target_alias=target_alias,
        python_version=python_version,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    release_slug = re.sub(r"[^0-9A-Za-z+._-]+", "-", PACKAGE_VERSION_FULL).strip("-")
    final_dir = output_root / f"jazn_latka_v{release_slug}"
    if final_dir.exists():
        if not overwrite:
            raise PackError(f"Katalog wyniku już istnieje: {final_dir}. Użyj --overwrite.")
        shutil.rmtree(final_dir)
    final_dir.mkdir(parents=True)
    work_root = Path(tempfile.mkdtemp(prefix=".jazn-pack-v101860-", dir=str(output_root)))
    reports: list[dict[str, Any]] = []
    transports: list[dict[str, Any]] = []
    try:
        for job in plan["jobs"]:
            role = str(job["role"])
            mode = str(job["distribution_mode"])
            job_dir = work_root / role.replace("+", "_")
            job_dir.mkdir(parents=True, exist_ok=True)
            report = run_distribution_pack(
                source=source_root,
                out_dir=job_dir,
                mode=mode,
                target_alias=target_alias,
                python_version=python_version,
                dependency_bundle=dependency_bundle,
                materialize_dependencies=materialize_dependencies,
            )
            reports.append({"role": role, "report": report})
            target = final_dir / f"jazn_latka_v{release_slug}.{role}.package{_transport_extension(archive_format)}"
            transport = _build_transport(job_dir, target, archive_format, int(split_size_mib))
            transport["role"] = role
            transports.append(transport)
        public_report = {
            "ok": True,
            "schema_version": "jazn_pack_generator_result/v1",
            "generator_version": GENERATOR_VERSION,
            "generator_title": GENERATOR_TITLE,
            "runtime_version": PACKAGE_VERSION_FULL,
            "plan": plan,
            "source": str(source_root),
            "output_dir": str(final_dir),
            "transports": transports,
            "canonical_distribution_reports": reports,
            "truth_boundary": (
                "Generator v10.1.86.0 zachowuje kanoniczne artefakty package_distribution wewnątrz warstwy transportowej. "
                "SYSTEM korzysta z manifestu i zweryfikowanego dependency bundle; PAMIĘĆ korzysta z kanonicznego eksportera. "
                "local_private_canon_extension.py nie jest źródłem SYSTEMU."
            ),
        }
        (final_dir / "JAZN_PACK_GENERATOR_REPORT.json").write_text(
            json.dumps(public_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return public_report
    except Exception:
        shutil.rmtree(final_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


def inspect_archive(path: Path | str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    lower = source.name.lower()
    joined_temp: Path | None = None
    candidate = source
    try:
        if re.search(r"\.zip\.001$", lower):
            joined_temp = Path(tempfile.mkstemp(suffix=".zip")[1])
            candidate = join_split_zip(source, joined_temp)
            lower = candidate.name.lower()
        if lower.endswith(".zip"):
            with zipfile.ZipFile(candidate, "r") as archive:
                names = [_safe_member_name(info.filename) for info in archive.infolist()]
                for info in archive.infolist():
                    if _zip_member_is_symlink(info):
                        raise PackError(f"ZIP zawiera symlink: {info.filename}")
                bad = archive.testzip()
            return {"ok": bad is None, "format": "zip", "members": names, "integrity_error": bad}
        if lower.endswith(".7z"):
            try:
                import py7zr  # type: ignore
            except ImportError as exc:
                raise PackError("Odczyt 7z wymaga py7zr.") from exc
            with py7zr.SevenZipFile(candidate, "r") as archive:
                names = [_safe_member_name(name) for name in archive.getnames()]
                test_result = archive.test()
            return {"ok": test_result in {None, True}, "format": "7z", "members": names}
        if lower.endswith(".tar") or ".tar." in lower:
            with tarfile.open(candidate, "r:*") as archive:
                names = [_safe_member_name(info.name) for info in archive.getmembers()]
            return {"ok": True, "format": "tar", "members": names}
        if lower.endswith(".rar"):
            try:
                import rarfile  # type: ignore
            except ImportError as exc:
                raise PackError("Odczyt RAR wymaga rarfile oraz backendu dekompresji.") from exc
            with rarfile.RarFile(candidate) as archive:
                names = [_safe_member_name(name) for name in archive.namelist()]
                bad = archive.testrar()
            return {"ok": bad is None, "format": "rar", "members": names, "integrity_error": bad}
        raise PackError(f"Nieobsługiwany format archiwum: {source.name}")
    finally:
        if joined_temp is not None:
            joined_temp.unlink(missing_ok=True)


def unpack_archive(archive_path: Path | str, destination: Path | str, *, overwrite: bool = False) -> dict[str, Any]:
    source = Path(archive_path).expanduser().resolve()
    dest = Path(destination).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dest.name}.extract-", dir=str(dest.parent)))
    joined_temp: Path | None = None
    candidate = source
    lower = source.name.lower()
    committed = False
    try:
        if re.search(r"\.zip\.001$", lower):
            joined_temp = Path(tempfile.mkstemp(suffix=".zip")[1])
            candidate = join_split_zip(source, joined_temp)
            lower = candidate.name.lower()
        if lower.endswith(".zip"):
            with zipfile.ZipFile(candidate, "r") as archive:
                for info in archive.infolist():
                    _safe_member_name(info.filename)
                    if _zip_member_is_symlink(info):
                        raise PackError(f"ZIP zawiera symlink: {info.filename}")
                if archive.testzip() is not None:
                    raise PackError("ZIP nie przeszedł testu CRC.")
                archive.extractall(staging)
        elif lower.endswith(".7z"):
            try:
                import py7zr  # type: ignore
            except ImportError as exc:
                raise PackError("Rozpakowanie 7z wymaga py7zr.") from exc
            with py7zr.SevenZipFile(candidate, "r") as archive:
                for name in archive.getnames():
                    _safe_member_name(name)
                archive.extractall(staging)
        elif lower.endswith(".tar") or ".tar." in lower:
            with tarfile.open(candidate, "r:*") as archive:
                for info in archive.getmembers():
                    _safe_member_name(info.name)
                archive.extractall(staging, filter="data")
        elif lower.endswith(".rar"):
            try:
                import rarfile  # type: ignore
            except ImportError as exc:
                raise PackError("Rozpakowanie RAR wymaga rarfile oraz backendu dekompresji.") from exc
            with rarfile.RarFile(candidate) as archive:
                for name in archive.namelist():
                    _safe_member_name(name)
                if archive.testrar() is not None:
                    raise PackError("RAR nie przeszedł testu integralności.")
                archive.extractall(staging)
        else:
            raise PackError(f"Nieobsługiwany format archiwum: {source.name}")
        if dest.exists():
            if not overwrite:
                raise PackError(f"Katalog docelowy już istnieje: {dest}")
            shutil.rmtree(dest)
        os.replace(staging, dest)
        committed = True
        return {"ok": True, "archive": str(source), "destination": str(dest)}
    finally:
        if joined_temp is not None:
            joined_temp.unlink(missing_ok=True)
        if not committed and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def config_report() -> dict[str, Any]:
    return {
        "ok": True,
        "generator_version": GENERATOR_VERSION,
        "generator_title": GENERATOR_TITLE,
        "runtime_version": PACKAGE_VERSION_FULL,
        "settings_path": str(_settings_path()),
        "default_output_dir": str(default_output_dir()),
        "archive_backends": archive_backend_status(),
        "hard_excludes": list(HARD_EXCLUDE_GLOBS),
        "content_choices": list(CONTENT_CHOICES),
        "layout_choices": list(LAYOUT_CHOICES),
        "archive_format_choices": list(ARCHIVE_FORMAT_CHOICES),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jazn_pack_generator.py",
        description=f"Jaźń Pack Generator v{GENERATOR_VERSION} — {GENERATOR_TITLE}",
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command")

    pack = sub.add_parser("pack", allow_abbrev=False)
    pack.add_argument("--source", default=".")
    pack.add_argument("--out-dir", default=str(default_output_dir()))
    pack.add_argument("--content", choices=CONTENT_CHOICES, default="system")
    pack.add_argument("--layout", choices=LAYOUT_CHOICES, default="single")
    pack.add_argument("--format", dest="archive_format", choices=ARCHIVE_FORMAT_CHOICES, default="zip")
    pack.add_argument("--split-size-mib", type=int, default=480)
    pack.add_argument("--target", default="current", choices=DISTRIBUTION_TARGET_CHOICES)
    pack.add_argument("--python-version", default="current", choices=DISTRIBUTION_PYTHON_CHOICES)
    pack.add_argument("--dependency-bundle")
    pack.add_argument("--materialize-dependencies", action="store_true")
    pack.add_argument("--overwrite", action="store_true")

    legacy = sub.add_parser("distribution-pack", allow_abbrev=False)
    legacy.add_argument("mode", choices=DISTRIBUTION_MODE_CHOICES)
    legacy.add_argument("--source", default=".")
    legacy.add_argument("--out-dir", required=True)
    legacy.add_argument("--target", default="current", choices=DISTRIBUTION_TARGET_CHOICES)
    legacy.add_argument("--python-version", default="current", choices=DISTRIBUTION_PYTHON_CHOICES)
    legacy.add_argument("--dependency-bundle")
    legacy.add_argument("--materialize-dependencies", action="store_true")

    inspect_cmd = sub.add_parser("inspect", allow_abbrev=False)
    inspect_cmd.add_argument("archive")

    unpack = sub.add_parser("unpack", allow_abbrev=False)
    unpack.add_argument("archive")
    unpack.add_argument("--destination", required=True)
    unpack.add_argument("--overwrite", action="store_true")

    sub.add_parser("config", allow_abbrev=False)

    ui = sub.add_parser("ui", allow_abbrev=False)
    ui.add_argument("mode", choices=("tekstowy", "kursorowy", "studio-terminal"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw:
        raw = ["config"]
    args = _parser().parse_args(raw)
    try:
        if args.command == "pack":
            payload = run_pack_request(
                source=args.source, out_dir=args.out_dir, content=args.content, layout=args.layout,
                archive_format=args.archive_format, split_size_mib=args.split_size_mib,
                target_alias=args.target, python_version=args.python_version,
                dependency_bundle=args.dependency_bundle,
                materialize_dependencies=args.materialize_dependencies,
                overwrite=args.overwrite,
            )
        elif args.command == "distribution-pack":
            payload = run_distribution_pack(
                source=args.source, out_dir=args.out_dir, mode=args.mode,
                target_alias=args.target, python_version=args.python_version,
                dependency_bundle=args.dependency_bundle,
                materialize_dependencies=args.materialize_dependencies,
            )
        elif args.command == "inspect":
            payload = inspect_archive(args.archive)
        elif args.command == "unpack":
            payload = unpack_archive(args.archive, args.destination, overwrite=args.overwrite)
        elif args.command == "config":
            payload = config_report()
        elif args.command == "ui":
            raise PackError("Tryby UI uruchamiaj przez publiczny tools/jazn_pack_generator.py")
        else:
            _parser().print_help()
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
