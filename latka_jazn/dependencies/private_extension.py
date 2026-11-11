"""Operator-approved, additive-only installation into the canonical ROOT/.venv.

This path never creates or selects another Python interpreter. It refuses
package upgrades, active runtime markers, incompatible wheelhouses, and
unverified installs. Failures may leave optional wheels installed but must
never mark an incomplete environment ready.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from latka_jazn.core.runtime_root import active_runtime_marker_path

from .common import (
    ENVIRONMENT_MARKER_NAME,
    ENVIRONMENT_SCHEMA,
    DependencyStudioError,
    canonicalize_distribution_name,
    current_platform_alias,
    dependency_contract_fingerprint,
    environment_marker_path,
    import_name_for_distribution,
    root_local_resources_enabled,
    runtime_version,
)
from .environment import (
    _inspect_inventory,
    _pip_inspect,
    _probe_python,
    _run,
    _write_json,
)
from .private_python import private_python_path, private_python_status
from .wheelhouse import (
    LOCK_NAME,
    MANIFEST_NAME,
    read_manifest,
    render_hash_lock,
    sha256_file,
    verify_bundle,
)


def _path_key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def missing_distributions(
    resolved: Sequence[Mapping[str, Any]], installed: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Return only absent wheels; refuse ALL version replacements.

    This is intentionally more conservative than pip's resolver. A change to
    an existing distribution needs a separately reviewed, offline upgrade.
    """
    missing: list[dict[str, Any]] = []
    names: set[str] = set()
    if not resolved:
        raise DependencyStudioError("empty_verified_dependency_inventory")
    for row in resolved:
        name = canonicalize_distribution_name(str(row.get("name") or ""))
        version = str(row.get("version") or "")
        if not name or not version or name in names:
            raise DependencyStudioError("duplicate_or_invalid_dependency_inventory")
        if not str(row.get("sha256") or ""):
            raise DependencyStudioError("missing_dependency_hash")
        names.add(name)
        actual = installed.get(name)
        if actual is None:
            missing.append(dict(row))
        elif actual != version:
            raise DependencyStudioError(
                "existing_package_version_drift: " + name
                + "; use a reviewed offline reinstall, not a live upgrade"
            )
    return missing


def extend_private_environment(
    root: Path | str,
    bundle_dir: Path | str,
    *,
    python_executable: str | None = None,
    offline: bool = True,
    timeout_seconds: int = 1800,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install only missing verified wheels into ROOT/.venv, then publish evidence.

    Operator approval belongs to setup.ps1 or the JSS consent dialog. The
    current daemon and MEMORY are never started, stopped, or modified.
    """
    if not offline:
        raise DependencyStudioError("private_venv_extension_requires_offline")
    project_root = Path(root).resolve()
    if not root_local_resources_enabled(project_root):
        raise DependencyStudioError("private_venv_extension_requires_prepared_root")
    private = private_python_status(project_root)
    if private.get("ready") is not True:
        raise DependencyStudioError("private_venv_missing_or_invalid")
    interpreter = private_python_path(project_root)
    if python_executable and _path_key(python_executable) != _path_key(interpreter):
        raise DependencyStudioError("extension_interpreter_must_be_root_private_venv")
    # A stale marker is a blocker, not permission to overwrite ownership.
    if active_runtime_marker_path(project_root).is_file():
        raise DependencyStudioError("active_runtime_marker_present_no_venv_mutation")
    if not interpreter.is_file():
        raise DependencyStudioError("private_python_missing")

    bundle = Path(bundle_dir).resolve()
    checked = verify_bundle(bundle)
    if checked.get("ok") is not True:
        raise DependencyStudioError("private_extension_bundle_not_verified")
    manifest = read_manifest(bundle / MANIFEST_NAME)
    if not manifest:
        raise DependencyStudioError("private_extension_manifest_missing")
    profiles = [str(name) for name in manifest.get("profiles") or []]
    resolved_profiles = [str(name) for name in manifest.get("resolved_profiles") or profiles]
    if "core" not in resolved_profiles:
        raise DependencyStudioError("extension_bundle_must_cover_core")

    target = manifest.get("target") or {}
    probe = _probe_python(str(interpreter))
    for field, observed in (
        ("alias", probe.get("platform")),
        ("python_version", probe.get("python_version")),
        ("implementation", probe.get("implementation")),
        ("abi", probe.get("abi")),
    ):
        if str(target.get(field) or "") != str(observed or ""):
            raise DependencyStudioError("extension_bundle_target_mismatch: " + field)
    resolved = manifest.get("resolved_distributions") or []
    if not isinstance(resolved, list):
        raise DependencyStudioError("extension_invalid_resolved_inventory")

    old_inventory = _inspect_inventory(_pip_inspect(
        interpreter, cwd=project_root, timeout=min(timeout_seconds, 300),
    ))
    missing = missing_distributions(resolved, old_inventory)
    env_marker = project_root / ".venv" / ENVIRONMENT_MARKER_NAME
    activation_marker = environment_marker_path(project_root)
    if (env_marker.is_symlink() or activation_marker.is_symlink()
            or not activation_marker.parent.resolve().is_relative_to(project_root)):
        raise DependencyStudioError("unsafe_private_dependency_marker_path")

    result: dict[str, Any] = {
        "ok": True,
        "state": "private_environment_extension_plan" if dry_run else "private_environment_extended",
        "environment_root": str(project_root / ".venv"),
        "python_executable": str(interpreter),
        "environment_marker_path": str(env_marker),
        "activation_marker_path": str(activation_marker),
        "profiles": profiles,
        "resolved_profiles": resolved_profiles,
        "missing_count": len(missing),
        "already_satisfied_count": len(resolved) - len(missing),
        "activation_marker_updated": False,
        "offline": True,
    }
    if dry_run:
        return {"dry_run": True, **result}

    if missing:
        # The verified bundle supplies every wheel; --no-deps prevents pip
        # from upgrading other distributions behind the operator's back.
        python_dir = project_root / "local_resources" / "python"
        if python_dir.is_symlink() or (hasattr(python_dir, "is_junction") and python_dir.is_junction()):
            raise DependencyStudioError("unsafe_private_python_state_root")
        python_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="jazn-additive-lock-", dir=python_dir) as staging:
            lock_path = Path(staging) / LOCK_NAME
            lock_path.write_text(render_hash_lock(missing), encoding="utf-8")
            _run([
                str(interpreter), "-m", "pip", "install", "--disable-pip-version-check",
                "--no-index", "--only-binary=:all:", "--require-hashes", "--no-deps",
                "--find-links", str(bundle), "-r", str(lock_path),
            ], cwd=project_root, timeout=timeout_seconds)

    pip_check = _run(
        [str(interpreter), "-m", "pip", "check"],
        cwd=project_root, timeout=min(timeout_seconds, 300),
    )
    requirements = [str(req) for req in manifest.get("requirements") or []]
    from .common import distribution_name_from_requirement
    import_names = list(dict.fromkeys(
        import_name_for_distribution(project_root, distribution_name_from_requirement(req))
        for req in requirements
    ))
    smoke = _run([
        str(interpreter), "-X", "utf8", "-c",
        "import importlib,json; names=" + json.dumps(import_names) +
        "; print(json.dumps({n:bool(importlib.import_module(n)) for n in names},sort_keys=True))",
    ], cwd=project_root, timeout=min(timeout_seconds, 300))
    inspected = _pip_inspect(interpreter, cwd=project_root, timeout=min(timeout_seconds, 300))
    inventory = _inspect_inventory(inspected)
    missing_after = missing_distributions(resolved, inventory)
    if missing_after:
        raise DependencyStudioError("extension_inventory_incomplete")
    fingerprint = dependency_contract_fingerprint(project_root, profiles)
    if fingerprint != str(manifest.get("dependency_contract_fingerprint") or ""):
        raise DependencyStudioError("extension_dependency_contract_changed")

    manifest_sha = sha256_file(bundle / MANIFEST_NAME)
    environment_identity = (
        str(probe["platform"]) + "__py" + str(probe["python_version"]).replace(".", "")
        + "__" + fingerprint[:12] + "__" + manifest_sha[:12] + "__root-venv"
    )
    marker: dict[str, Any] = {
        "schema_version": ENVIRONMENT_SCHEMA,
        "created_for_runtime_version": runtime_version(),
        "ready": True,
        "project_root": str(project_root),
        "environment_root": str(project_root / ".venv"),
        "managed_environments_root": str(project_root),
        "environment_identity": environment_identity,
        "python_executable": str(interpreter),
        "python_version": probe["python_version"],
        "platform": probe["platform"],
        "implementation": probe["implementation"],
        "abi": probe["abi"],
        "libc_family": probe.get("libc_family"),
        "minimum_libc_version": target.get("minimum_libc_version"),
        "profiles": profiles,
        "resolved_profiles": resolved_profiles,
        "requirements": requirements,
        "dependency_contract_fingerprint": fingerprint,
        "wheelhouse_bundle": str(bundle),
        "wheelhouse_manifest_sha256": manifest_sha,
        "hash_lock_sha256": sha256_file(bundle / LOCK_NAME),
        "pip_check": pip_check.stdout.strip() or "No broken requirements found.",
        "import_smoke": json.loads(smoke.stdout.strip() or "{}"),
        "pip_inspect": inspected,
        "installed_inventory": inventory,
        "truth_boundary": (
            "Only absent SHA-256-locked wheels were installed to ROOT/.venv. "
            "All existing distribution versions were preserved, then pip check, "
            "import smoke and pip inspect were verified before marker publication."
        ),
    }
    # Publish the project activation marker LAST. Failure before this point
    # never advertises an incomplete environment as the new active Python.
    _write_json(env_marker, marker)
    _write_json(activation_marker, marker)
    return {**result, "activation_marker_updated": True, "environment_identity": environment_identity}
