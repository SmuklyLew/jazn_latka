"""Opt-in, read-only External Python environment policy.

No dependency installation, environment creation, deletion, or daemon lifecycle
is allowed here. An absent policy preserves the existing v127 installation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Any, Mapping

SCHEMA_VERSION = "jazn_python_environment/v1"
CONFIG_NAME = "python_environment.json"
MAX_CONFIG_BYTES = 65536
PROBE_TIMEOUT_SECONDS = 15

# The probe runs in the user-selected interpreter. -I ignores ambient Python
# paths and -B prevents writing bytecode into the external environment.
_PROBE_CODE = """
import importlib.metadata as metadata
import importlib.util
import json
import platform
import sys
from packaging.requirements import Requirement

requirements = json.loads(sys.argv[1])
aliases = json.loads(sys.argv[2])
missing = []
incompatible = []
imports_missing = []
for spec in requirements:
    requirement = Requirement(spec)
    if requirement.marker is not None and not requirement.marker.evaluate():
        continue
    try:
        installed = metadata.version(requirement.name)
    except metadata.PackageNotFoundError:
        missing.append(requirement.name)
        continue
    if requirement.specifier and not requirement.specifier.contains(installed, prereleases=True):
        incompatible.append({"distribution": requirement.name, "installed": installed, "required": str(requirement.specifier)})
        continue
    canonical = requirement.name.lower().replace("_", "-").replace(".", "-")
    module = aliases.get(canonical, canonical.replace("-", "_"))
    try:
        import_ready = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        import_ready = False
    if not import_ready:
        imports_missing.append(requirement.name)
print(json.dumps({
    "executable": sys.executable,
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "python_version": [sys.version_info.major, sys.version_info.minor],
    "implementation": sys.implementation.name,
    "architecture": platform.machine(),
    "missing": missing,
    "incompatible": incompatible,
    "imports_missing": imports_missing,
}, sort_keys=True))
"""


class EnvironmentPolicyError(ValueError):
    """Invalid policy; never fall back to another interpreter."""


def policy_path(root: Path | str) -> Path:
    return Path(root).resolve() / ".settings_local" / CONFIG_NAME


def _path_key(value: Path | str) -> str:
    # POSIX venv/bin/python is normally a symlink. Do not dereference it.
    return os.path.normcase(os.path.abspath(os.fspath(value)))


def load_environment_policy(root: Path | str) -> dict[str, Any] | None:
    """Read an explicit operator policy without modifying any files."""
    target = policy_path(root)
    if not target.exists() and not target.is_symlink():
        return None  # Backward compatibility: no implicit migration.
    if target.is_symlink() or not target.is_file():
        raise EnvironmentPolicyError("environment_policy_not_regular_file")
    try:
        if not 0 < target.stat().st_size <= MAX_CONFIG_BYTES:
            raise EnvironmentPolicyError("environment_policy_size_invalid")
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EnvironmentPolicyError("environment_policy_unreadable") from exc
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise EnvironmentPolicyError("environment_policy_schema_invalid")
    mode = document.get("mode")
    if mode not in {"external", "managed", "portable"}:
        raise EnvironmentPolicyError("environment_policy_mode_invalid")
    if mode != "external":
        # The explicit Managed/Portable contracts require separate migrations.
        # Do not accidentally interpret an unfinished policy as legacy.
        raise EnvironmentPolicyError("environment_policy_mode_not_implemented")
    for name in ("automatic_installation", "automatic_updates", "allow_environment_deletion"):
        if document.get(name, False) is not False:
            raise EnvironmentPolicyError("external_mutation_forbidden:" + name)
    raw_python = document.get("python_executable")
    if not isinstance(raw_python, str) or not raw_python.strip():
        raise EnvironmentPolicyError("external_python_missing")
    executable = Path(raw_python)
    if not executable.is_absolute():
        raise EnvironmentPolicyError("external_python_must_be_absolute")
    profiles = document.get("required_profiles", ["core"])
    if (not isinstance(profiles, list) or not profiles
            or any(not isinstance(name, str) or not name.strip() for name in profiles)
            or len(set(profiles)) != len(profiles) or "core" not in profiles):
        raise EnvironmentPolicyError("external_profiles_invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "external",
        "python_executable": str(executable),
        "required_profiles": list(profiles),
        "automatic_installation": False,
        "automatic_updates": False,
        "allow_environment_deletion": False,
    }


def require_operator_managed_environment(root: Path | str) -> None:
    """Guard direct installers, not just main.py and the JSS buttons.

    The presence of an invalid or unsupported policy also blocks mutation.
    Legacy operation is preserved only if there is no explicit policy file.
    """
    selected = load_environment_policy(root)
    if selected is not None:
        raise EnvironmentPolicyError("external_environment_mutation_forbidden")


def _requirements(root: Path, profiles: list[str]) -> tuple[list[str], dict[str, str]]:
    with (root / "pyproject.toml").open("rb") as stream:
        pyproject = tomllib.load(stream)
    project = pyproject.get("project") or {}
    optional = project.get("optional-dependencies") or {}
    registry_path = root / "latka_jazn" / "resources" / "dependencies" / "profiles.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    available = registry.get("profiles") or {}
    requirements: list[str] = list(project.get("dependencies") or [])
    for profile in profiles:
        entry = available.get(profile)
        if not isinstance(entry, dict) or profile == "all":
            raise EnvironmentPolicyError("external_unknown_profile:" + profile)
        if profile == "core":
            if entry.get("source") != "project.dependencies":
                raise EnvironmentPolicyError("external_core_profile_invalid")
            continue
        group = entry.get("source_optional_group")
        if not isinstance(group, str) or group not in optional:
            raise EnvironmentPolicyError("external_profile_mapping_invalid:" + profile)
        requirements.extend(optional[group])
    if not all(isinstance(item, str) for item in requirements):
        raise EnvironmentPolicyError("external_requirements_invalid")
    aliases = registry.get("import_name_overrides") or {}
    if not isinstance(aliases, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in aliases.items()):
        raise EnvironmentPolicyError("external_import_mapping_invalid")
    return requirements, aliases


def inspect_external_environment(
    root: Path | str, policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify a selected interpreter and its declared profiles without pip."""
    directory = Path(root).resolve()
    if policy is None:
        policy = load_environment_policy(directory)
    if policy is None:
        return {"mode": "external", "status": "NOT_CONFIGURED", "ready": False,
                "current": False, "errors": ["environment_policy_absent"]}
    executable = str(policy["python_executable"])
    profiles = list(policy["required_profiles"])
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "external",
        "status": "BLOCKED",
        "ready": False,
        "current": False,
        "python_executable": executable,
        "required_profiles": profiles,
        "errors": [],
    }
    if not Path(executable).is_file():
        result["status"] = "INVALID"
        result["errors"].append("external_python_not_a_file")
        return result
    try:
        requirements, aliases = _requirements(directory, profiles)
    except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError) as exc:
        result["status"] = "INVALID"
        result["errors"].append(str(exc) if isinstance(exc, EnvironmentPolicyError)
                                else "external_requirements_unreadable")
        return result
    try:
        completed = subprocess.run(
            [executable, "-I", "-B", "-X", "utf8", "-c", _PROBE_CODE,
             json.dumps(requirements, ensure_ascii=False),
             json.dumps(aliases, ensure_ascii=False)],
            cwd=directory, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False, timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        result["errors"].append("external_python_probe_failed")
        return result
    if completed.returncode or len(completed.stdout) > 32768:
        result["errors"].append("external_python_probe_failed")
        return result
    try:
        probe = json.loads(completed.stdout)
        version = probe["python_version"]
        if (not isinstance(probe, dict) or not isinstance(version, list)
                or len(version) != 2 or not all(type(n) is int for n in version)):
            raise ValueError("invalid Python probe")
    except (ValueError, TypeError, KeyError):
        result["errors"].append("external_python_probe_invalid")
        return result
    result["probe"] = probe
    result["current"] = _path_key(sys.executable) == _path_key(executable)
    if _path_key(probe.get("executable", "")) != _path_key(executable):
        result["errors"].append("external_python_identity_mismatch")
    if probe.get("implementation") != "cpython" or not (3, 12) <= tuple(version) <= (3, 14):
        result["errors"].append("external_python_unsupported_version")
    if probe.get("missing"):
        result["errors"].append("external_required_distributions_missing")
    if probe.get("incompatible"):
        result["errors"].append("external_required_distributions_incompatible")
    if probe.get("imports_missing"):
        result["errors"].append("external_required_imports_missing")
    if not result["errors"]:
        result["status"] = "READY"
        result["ready"] = True
    return result
