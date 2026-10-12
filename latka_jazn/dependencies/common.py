from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform as platform_module
import re
import subprocess
import sys
import sysconfig
import tomllib
from typing import Any, Iterable, Sequence

PROFILE_SCHEMA = "jazn_dependency_profiles/v1"
WHEELHOUSE_SCHEMA = "jazn_dependency_wheelhouse/v3"
ENVIRONMENT_SCHEMA = "jazn_dependency_environment/v2"
DEPENDENCY_ARTIFACT_SCHEMA = "jazn_dependency_artifact/v2"
DEPENDENCY_SET_SCHEMA = "jazn_dependency_set/v1"
MANIFEST_NAME = "JAZN_WHEELHOUSE_MANIFEST.json"
LOCK_NAME = "JAZN_WHEELHOUSE_REQUIREMENTS.txt"
ENVIRONMENT_MARKER_NAME = "JAZN_DEPENDENCY_ENVIRONMENT.json"
DEPENDENCY_SET_NAME = "JAZN_DEPENDENCY_SET.json"
DEFAULT_TIMEOUT_SECONDS = 1800
LINUX_GLIBC_MINIMUM = "2.17"
# A glibc 2.17 target accepts wheels whose declared minimum is 2.17 or older.
# Keep the PEP 600 spellings and the bounded legacy aliases explicit so pip's
# candidate selection and the post-download tag verifier use the same set.
LINUX_X64_PIP_PLATFORMS = (
    "manylinux_2_17_x86_64",
    "manylinux2014_x86_64",
    "manylinux_2_16_x86_64",
    "manylinux_2_15_x86_64",
    "manylinux_2_14_x86_64",
    "manylinux_2_13_x86_64",
    "manylinux_2_12_x86_64",
    "manylinux2010_x86_64",
    "manylinux_2_11_x86_64",
    "manylinux_2_10_x86_64",
    "manylinux_2_9_x86_64",
    "manylinux_2_8_x86_64",
    "manylinux_2_7_x86_64",
    "manylinux_2_6_x86_64",
    "manylinux_2_5_x86_64",
    "manylinux1_x86_64",
)


class DependencyStudioError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TargetSpec:
    alias: str
    python_version: str
    implementation: str
    abi: str | None
    pip_platform: str | None
    pip_platforms: tuple[str, ...]
    platform_family: str
    architecture: str
    libc_family: str
    minimum_libc_version: str | None = None
    compatible_tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["compatible_pip_platforms"] = list(self.pip_platforms)
        payload.pop("pip_platforms", None)
        payload["compatible_platform_tags"] = list(self.compatible_tags)
        payload.pop("compatible_tags", None)
        return payload


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


def _packaging_requirement(text: str) -> Any | None:
    """Parse with PyPA packaging when available, without making bootstrap depend on it."""
    try:
        from packaging.requirements import Requirement
    except ImportError:
        return None
    try:
        return Requirement(str(text))
    except Exception as exc:
        raise DependencyStudioError(f"Invalid requirement: {text!r}: {exc}") from exc


def canonicalize_distribution_name(value: str) -> str:
    try:
        from packaging.utils import canonicalize_name
    except ImportError:
        return re.sub(r"[-_.]+", "-", str(value or "").strip()).lower()
    return str(canonicalize_name(str(value or "").strip()))


def distribution_name_from_requirement(requirement: str) -> str:
    parsed = _packaging_requirement(requirement)
    if parsed is not None:
        return canonicalize_distribution_name(parsed.name)
    # stdlib-only bootstrap fallback supports package names and ordinary extras.
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
    project = payload.get("project")
    if not isinstance(project, dict):
        project = {}
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
            raise DependencyStudioError(f"Conflicting requirements for {name}: {previous!r} vs {requirement!r}")
        if previous is None:
            seen[name] = requirement
            result.append(requirement)
    return result


def expand_profile_names(root: Path | str, profile_names: Sequence[str]) -> tuple[str, ...]:
    profiles = load_profile_registry(root)["profiles"]
    requested = [str(item).strip() for item in profile_names if str(item).strip()]
    if not requested:
        requested = list(activation_profile_names(root))
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
            excluded = {canonicalize_distribution_name(str(item)) for item in raw.get("exclude_distributions") or []}
            requirements.extend(item for item in base if distribution_name_from_requirement(item) not in excluded)
        group = str(raw.get("source_optional_group") or "").strip()
        if group:
            if group not in optional:
                raise DependencyStudioError(f"Profile {name} references missing pyproject optional group {group!r}")
            requirements.extend(optional[group])
        explicit = raw.get("requirements") or []
        if not isinstance(explicit, list):
            raise DependencyStudioError(f"Invalid requirements in profile {name}")
        requirements.extend(str(item) for item in explicit)
    return dedupe_requirements(requirements)


def dependency_contract_fingerprint(root: Path | str, profile_names: Sequence[str]) -> str:
    project_root = Path(root).resolve()
    registry = load_profile_registry(project_root)
    payload = {
        "profiles": list(profile_names),
        "resolved_profiles": list(expand_profile_names(project_root, profile_names)),
        "requirements": resolve_profile_requirements(project_root, profile_names),
        "registry": registry,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def activation_profile_names(root: Path | str) -> tuple[str, ...]:
    raw = load_profile_registry(root).get("activation_profiles") or []
    return tuple(str(item) for item in raw) if isinstance(raw, list) and raw else ("core",)


def release_profile_names(root: Path | str) -> tuple[str, ...]:
    registry = load_profile_registry(root)
    raw = registry.get("release_profiles") or []
    if isinstance(raw, list) and raw:
        return tuple(str(item) for item in raw)
    return activation_profile_names(root)


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
    return str(requirement)[match.end():].split(";", 1)[0].strip()


def _version_tuple(value: str) -> tuple[int, ...] | None:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", str(value or ""))
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def version_satisfies_requirement(installed_version: str, requirement: str) -> bool | None:
    parsed = _packaging_requirement(requirement)
    if parsed is not None:
        try:
            from packaging.version import Version
            return Version(str(installed_version)) in parsed.specifier
        except Exception:
            return None
    # Minimal bootstrap fallback. Full PEP 440 validation is performed after handoff.
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
        if not {">=": comparison >= 0, "<=": comparison <= 0, ">": comparison > 0, "<": comparison < 0,
                "==": comparison == 0, "!=": comparison != 0}[operator]:
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
        version_ok = version_satisfies_requirement(installed_version, requirement) if installed_version is not None else False
        statuses.append(RequirementStatus(requirement, distribution, import_name, installed_version,
                                          import_available, version_ok, bool(import_available and version_ok is True)))
    return statuses


def default_local_python_root(root: Path | str) -> Path:
    """Return host-level mutable dependency state, never a directory inside active_root."""
    from latka_jazn.core.runtime_root import workspace_runtime_path

    project_root = Path(root).expanduser().resolve()
    return workspace_runtime_path(project_root) / "local_resources" / "python"


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


def current_libc_family() -> str:
    if platform_module.system().lower() != "linux":
        return "not-applicable"
    libc_name, _ = platform_module.libc_ver()
    lowered = str(libc_name or "").lower()
    if "musl" in lowered:
        return "musl"
    if lowered in {"glibc", "gnu libc", "libc"}:
        return "glibc"
    # platform.libc_ver can be empty in minimal containers. Ask ldd without making it mandatory.
    try:
        cp = subprocess.run(["ldd", "--version"], capture_output=True, text=True, timeout=2, check=False)
        text = (cp.stdout + cp.stderr).lower()
        if "musl" in text:
            return "musl"
        if "glibc" in text or "gnu libc" in text:
            return "glibc"
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def normalize_python_version(value: str | None) -> str:
    raw = str(value or f"{sys.version_info.major}.{sys.version_info.minor}").strip()
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", raw)
    if not match:
        raise DependencyStudioError(f"Unsupported Python target version: {value!r}")
    return f"{int(match.group(1))}.{int(match.group(2))}"


def _architecture_for_alias(alias: str) -> str:
    if alias.endswith("-x64"):
        return "x86_64"
    if alias.endswith("-arm64"):
        return "arm64"
    return platform_module.machine().lower() or "unknown"


def current_implementation_tag() -> str:
    name = str(getattr(getattr(sys, "implementation", None), "name", "") or "").strip().lower()
    if name == "cpython":
        return "cp"
    if name == "pypy":
        return "pp"
    return name[:2] or "unknown"


def current_abi_tag() -> str | None:
    implementation = current_implementation_tag()
    if implementation == "cp":
        flags = str(getattr(sys, "abiflags", "") or "")
        return f"cp{sys.version_info.major}{sys.version_info.minor}{flags}"
    return None


def _target_tags(
    alias: str,
    py: str,
    abi: str | None,
    pip_platforms: Sequence[str],
) -> tuple[str, ...]:
    try:
        from packaging.tags import compatible_tags, cpython_tags, sys_tags
    except ImportError:
        return ()
    if pip_platforms:
        major, minor = (int(x) for x in py.split("."))
        abis = [abi] if abi else None
        platforms = list(pip_platforms)
        tags = list(cpython_tags((major, minor), abis=abis, platforms=platforms))
        tags.extend(
            compatible_tags(
                (major, minor),
                interpreter=f"cp{major}{minor}",
                platforms=platforms,
            )
        )
        return tuple(dict.fromkeys(str(tag) for tag in tags))
    current_py = f"{sys.version_info.major}.{sys.version_info.minor}"
    if alias == current_platform_alias() and py == current_py:
        return tuple(str(tag) for tag in sys_tags())
    return ()


def target_is_current_host(target: TargetSpec) -> bool:
    current_py = f"{sys.version_info.major}.{sys.version_info.minor}"
    if target.alias != current_platform_alias() or target.python_version != current_py:
        return False
    if target.implementation != current_implementation_tag():
        return False
    if target.platform_family == "linux":
        return target.libc_family == current_libc_family()
    return True


def target_spec(platform_alias: str | None, python_version: str | None) -> TargetSpec:
    py = normalize_python_version(python_version)
    alias = str(platform_alias or "current").strip().lower()
    current_alias = current_platform_alias()
    current_py = f"{sys.version_info.major}.{sys.version_info.minor}"
    if alias == "current":
        alias = current_alias
    digits = py.replace(".", "")
    native_target = alias == current_alias and py == current_py
    implementation = current_implementation_tag() if native_target else "cp"
    abi: str | None = current_abi_tag() if native_target else None
    pip_platforms: tuple[str, ...] = ()
    libc = "not-applicable"
    minimum_libc_version: str | None = None
    if alias == "windows-x64":
        pip_platforms = ("win_amd64",)
        abi = abi or f"cp{digits}"
    elif alias == "windows-arm64":
        pip_platforms = ("win_arm64",)
        abi = abi or f"cp{digits}"
    elif alias == "linux-x64":
        actual_libc = current_libc_family() if alias == current_alias else None
        if actual_libc not in {None, "glibc"}:
            raise DependencyStudioError(
                "no_compatible_dependency_bundle: linux-x64 release target requires glibc"
            )
        pip_platforms = LINUX_X64_PIP_PLATFORMS
        abi = abi or f"cp{digits}"
        libc = "glibc"
        minimum_libc_version = LINUX_GLIBC_MINIMUM
    elif alias in {"linux-arm64", "macos-x64", "macos-arm64"}:
        # ARM Linux and macOS remain native-only until their release policies and
        # clean-room matrices are explicitly accepted.
        if alias != current_alias or py != current_py:
            raise DependencyStudioError(
                f"Cross-target {alias!r} must be materialized on a native runner with Python {py}; "
                "the release does not define a deterministic compatibility policy"
            )
    else:
        raise DependencyStudioError(f"Unsupported dependency target alias: {alias!r}")

    family = alias.split("-", 1)[0]
    if family == "linux" and alias != "linux-x64":
        libc = current_libc_family() if alias == current_alias else "native-required"
        if libc == "musl":
            raise DependencyStudioError(
                "no_compatible_dependency_bundle: musl is not release-supported in 16.3.25.5"
            )
    tags = _target_tags(alias, py, abi, pip_platforms)
    return TargetSpec(
        alias=alias,
        python_version=py,
        implementation=implementation,
        abi=abi,
        pip_platform=pip_platforms[0] if pip_platforms else None,
        pip_platforms=pip_platforms,
        platform_family=family,
        architecture=_architecture_for_alias(alias),
        libc_family=libc,
        minimum_libc_version=minimum_libc_version,
        compatible_tags=tags,
    )
