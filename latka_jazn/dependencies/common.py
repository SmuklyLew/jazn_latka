from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform as platform_module
import re
import sys
import tomllib
from typing import Any, Iterable, Sequence

PROFILE_SCHEMA = "jazn_dependency_profiles/v1"
WHEELHOUSE_SCHEMA = "jazn_dependency_wheelhouse/v1"
ENVIRONMENT_SCHEMA = "jazn_dependency_environment/v1"
MANIFEST_NAME = "JAZN_WHEELHOUSE_MANIFEST.json"
ENVIRONMENT_MARKER_NAME = "JAZN_DEPENDENCY_ENVIRONMENT.json"
DEFAULT_TIMEOUT_SECONDS = 1800


class DependencyStudioError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TargetSpec:
    alias: str
    python_version: str
    implementation: str
    abi: str | None
    pip_platform: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RequirementStatus:
    requirement: str
    distribution: str
    import_name: str
    installed_version: str | None
    import_available: bool
    version_satisfies: bool | None
    ready: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def runtime_version() -> str:
    try:
        from latka_jazn.version import PACKAGE_VERSION_FULL
        return str(PACKAGE_VERSION_FULL)
    except (ImportError, AttributeError):
        return "unknown"


def canonicalize_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", str(value or "").strip()).lower()


def distribution_name_from_requirement(requirement: str) -> str:
    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", str(requirement or "").strip())
    if not match:
        raise DependencyStudioError(f"Invalid requirement: {requirement!r}")
    return canonicalize_distribution_name(match.group(1))


def profile_registry_path(root: Path | str) -> Path:
    return Path(root).resolve() / "latka_jazn" / "resources" / "dependencies" / "profiles.json"


def load_profile_registry(root: Path | str) -> dict[str, Any]:
    path = profile_registry_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DependencyStudioError(f"Cannot read dependency profile registry {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != PROFILE_SCHEMA:
        raise DependencyStudioError(f"Unsupported dependency profile registry: {path}")
    if not isinstance(payload.get("profiles"), dict) or not payload["profiles"]:
        raise DependencyStudioError("Dependency profile registry has no profiles")
    return payload


def project_dependency_groups(root: Path | str) -> tuple[list[str], dict[str, list[str]]]:
    path = Path(root).resolve() / "pyproject.toml"
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise DependencyStudioError(f"Cannot read pyproject.toml: {exc}") from exc
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    base = [str(item) for item in project.get("dependencies") or []]
    optional: dict[str, list[str]] = {}
    raw = project.get("optional-dependencies")
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, list):
                optional[str(key)] = [str(item) for item in value]
    return base, optional


def dedupe_requirements(requirements: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: dict[str, str] = {}
    for raw in requirements:
        requirement = str(raw).strip()
        if not requirement:
            continue
        name = distribution_name_from_requirement(requirement)
        previous = seen.get(name)
        if previous is not None and previous != requirement:
            raise DependencyStudioError(
                f"Conflicting requirements for {name}: {previous!r} vs {requirement!r}"
            )
        if previous is None:
            seen[name] = requirement
            result.append(requirement)
    return result


def expand_profile_names(root: Path | str, profile_names: Sequence[str]) -> tuple[str, ...]:
    profiles = load_profile_registry(root)["profiles"]
    requested = [str(item).strip() for item in profile_names if str(item).strip()] or ["core", "archive"]
    resolving: set[str] = set()
    resolved: list[str] = []

    def visit(name: str) -> None:
        if name in resolved:
            return
        if name in resolving:
            raise DependencyStudioError(f"Dependency profile cycle: {name}")
        raw = profiles.get(name)
        if not isinstance(raw, dict):
            raise DependencyStudioError(f"Unknown dependency profile: {name}")
        resolving.add(name)
        includes = raw.get("includes") or []
        if not isinstance(includes, list):
            raise DependencyStudioError(f"Invalid includes in profile {name}")
        for child in includes:
            visit(str(child))
        resolving.remove(name)
        resolved.append(name)

    for name in requested:
        visit(name)
    return tuple(resolved)


def resolve_profile_requirements(root: Path | str, profile_names: Sequence[str]) -> list[str]:
    registry = load_profile_registry(root)
    profiles = registry["profiles"]
    base, optional = project_dependency_groups(root)
    requirements: list[str] = []
    for name in expand_profile_names(root, profile_names):
        raw = profiles[name]
        if raw.get("source") == "project.dependencies":
            excluded = {
                canonicalize_distribution_name(str(item))
                for item in raw.get("exclude_distributions") or []
            }
            requirements.extend(
                item for item in base
                if distribution_name_from_requirement(item) not in excluded
            )
        group = str(raw.get("source_optional_group") or "").strip()
        if group:
            if group not in optional:
                raise DependencyStudioError(
                    f"Profile {name} references missing pyproject optional group {group!r}"
                )
            requirements.extend(optional[group])
        explicit = raw.get("requirements") or []
        if not isinstance(explicit, list):
            raise DependencyStudioError(f"Invalid requirements in profile {name}")
        requirements.extend(str(item) for item in explicit)
    return dedupe_requirements(requirements)


def activation_profile_names(root: Path | str) -> tuple[str, ...]:
    raw = load_profile_registry(root).get("activation_profiles") or []
    return tuple(str(item) for item in raw) if isinstance(raw, list) and raw else ("core", "archive")


def import_name_for_distribution(root: Path | str, distribution: str) -> str:
    overrides = load_profile_registry(root).get("import_name_overrides")
    key = canonicalize_distribution_name(distribution)
    if isinstance(overrides, dict):
        for raw_name, import_name in overrides.items():
            if canonicalize_distribution_name(str(raw_name)) == key:
                return str(import_name)
    return key.replace("-", "_")


def _specifier_text(requirement: str) -> str:
    match = re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[^\]]+\])?", str(requirement).strip())
    if not match:
        return ""
    remainder = str(requirement)[match.end():].split(";", 1)[0]
    return remainder.strip()


def _version_tuple(value: str) -> tuple[int, ...] | None:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", str(value or ""))
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def version_satisfies_requirement(installed_version: str, requirement: str) -> bool | None:
    specifier = _specifier_text(requirement)
    if not specifier:
        return True
    installed = _version_tuple(installed_version)
    if installed is None:
        return None
    for clause in (part.strip() for part in specifier.split(",")):
        match = re.match(r"^(>=|<=|==|!=|>|<)\s*([^\s]+)$", clause)
        if not match:
            return None
        operator, raw_expected = match.groups()
        expected = _version_tuple(raw_expected)
        if expected is None:
            return None
        width = max(len(installed), len(expected))
        left = installed + (0,) * (width - len(installed))
        right = expected + (0,) * (width - len(expected))
        comparison = (left > right) - (left < right)
        passed = {
            ">=": comparison >= 0,
            "<=": comparison <= 0,
            ">": comparison > 0,
            "<": comparison < 0,
            "==": comparison == 0,
            "!=": comparison != 0,
        }[operator]
        if not passed:
            return False
    return True


def inspect_current_requirements(root: Path | str, requirements: Sequence[str]) -> list[RequirementStatus]:
    statuses: list[RequirementStatus] = []
    for requirement in requirements:
        distribution = distribution_name_from_requirement(requirement)
        import_name = import_name_for_distribution(root, distribution)
        try:
            installed_version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            installed_version = None
        try:
            import_available = importlib.util.find_spec(import_name) is not None
        except (ImportError, AttributeError, ValueError):
            import_available = False
        version_ok = (
            version_satisfies_requirement(installed_version, requirement)
            if installed_version is not None else False
        )
        statuses.append(RequirementStatus(
            requirement=requirement,
            distribution=distribution,
            import_name=import_name,
            installed_version=installed_version,
            import_available=import_available,
            version_satisfies=version_ok,
            ready=bool(import_available and version_ok is True),
        ))
    return statuses


def default_local_python_root(root: Path | str) -> Path:
    return Path(root).resolve() / "latka_jazn" / "local_resources" / "python"


def default_wheelhouse_root(root: Path | str) -> Path:
    return default_local_python_root(root) / "wheelhouse"


def default_environments_root(root: Path | str) -> Path:
    explicit = os.environ.get("JAZN_DEPENDENCY_ENVIRONMENTS")
    return Path(explicit).expanduser().resolve() if explicit else default_local_python_root(root) / "environments"


def environment_marker_path(root: Path | str) -> Path:
    return default_local_python_root(root) / ENVIRONMENT_MARKER_NAME


def current_platform_alias() -> str:
    system = platform_module.system().lower()
    machine = platform_module.machine().lower()
    table = {
        ("windows", "amd64"): "windows-x64", ("windows", "x86_64"): "windows-x64",
        ("windows", "arm64"): "windows-arm64", ("windows", "aarch64"): "windows-arm64",
        ("linux", "amd64"): "linux-x64", ("linux", "x86_64"): "linux-x64",
        ("linux", "arm64"): "linux-arm64", ("linux", "aarch64"): "linux-arm64",
        ("darwin", "arm64"): "macos-arm64", ("darwin", "aarch64"): "macos-arm64",
        ("darwin", "amd64"): "macos-x64", ("darwin", "x86_64"): "macos-x64",
    }
    return table.get((system, machine), f"{system or 'unknown'}-{machine or 'unknown'}")


def normalize_python_version(value: str | None) -> str:
    raw = str(value or f"{sys.version_info.major}.{sys.version_info.minor}").strip()
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", raw)
    if not match:
        raise DependencyStudioError(f"Unsupported Python target version: {value!r}")
    return f"{int(match.group(1))}.{int(match.group(2))}"


def target_spec(platform_alias: str | None, python_version: str | None) -> TargetSpec:
    py = normalize_python_version(python_version)
    alias = str(platform_alias or "current").strip().lower()
    current_alias = current_platform_alias()
    current_py = f"{sys.version_info.major}.{sys.version_info.minor}"
    if alias == "current":
        if py != current_py:
            raise DependencyStudioError(
                "A different Python version with --platform current is ambiguous; choose windows-x64/windows-arm64 explicitly"
            )
        return TargetSpec(current_alias, py, "cp", None, None)
    digits = py.replace(".", "")
    mappings = {
        "windows-x64": ("win_amd64", f"cp{digits}"),
        "windows-arm64": ("win_arm64", f"cp{digits}"),
    }
    if alias in mappings:
        pip_platform, abi = mappings[alias]
        return TargetSpec(alias, py, "cp", abi, pip_platform)
    if alias == current_alias:
        if py != current_py:
            raise DependencyStudioError(
                f"A different Python version for current platform {alias!r} is unsupported; use a supported explicit cross-platform target"
            )
        return TargetSpec(alias, py, "cp", None, None)
    raise DependencyStudioError(
        f"Cross-platform target {alias!r} unsupported in v1; use current, windows-x64 or windows-arm64"
    )
