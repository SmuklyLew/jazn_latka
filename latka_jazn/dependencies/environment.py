from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

from .common import (
    DEFAULT_TIMEOUT_SECONDS,
    ENVIRONMENT_MARKER_NAME,
    ENVIRONMENT_SCHEMA,
    LOCK_NAME,
    MANIFEST_NAME,
    DependencyStudioError,
    activation_profile_names,
    current_abi_tag,
    current_implementation_tag,
    current_libc_family,
    current_platform_alias,
    default_environments_root,
    default_wheelhouse_root,
    dependency_contract_fingerprint,
    distribution_name_from_requirement,
    environment_marker_path,
    import_name_for_distribution,
    inspect_current_requirements,
    resolve_profile_requirements,
    runtime_version,
)
from .release_artifact import materialize_compatible_dependency_artifact
from .wheelhouse import discover_bundles, read_manifest, sha256_file, verify_bundle


def _env_python(root: Path) -> Path:
    return root / "Scripts" / "python.exe" if os.name == "nt" else root / "bin" / "python"


def _run(command: Sequence[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command), cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=max(30, int(timeout)), check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DependencyStudioError(f"Command failed ({completed.returncode}): {' '.join(command)}\n{detail}")
    return completed


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _probe_python(executable: str) -> dict[str, str]:
    code = (
        "import json,platform,sys; m=platform.machine().lower(); s=platform.system().lower();"
        "t={('windows','amd64'):'windows-x64',('windows','x86_64'):'windows-x64',"
        "('windows','arm64'):'windows-arm64',('windows','aarch64'):'windows-arm64',"
        "('linux','amd64'):'linux-x64',('linux','x86_64'):'linux-x64',"
        "('linux','arm64'):'linux-arm64',('linux','aarch64'):'linux-arm64',"
        "('darwin','arm64'):'macos-arm64',('darwin','aarch64'):'macos-arm64',"
        "('darwin','amd64'):'macos-x64',('darwin','x86_64'):'macos-x64'};"
        "libc=(platform.libc_ver()[0] or '').lower();"
        "lf=('musl' if 'musl' in libc else 'glibc' if libc in {'glibc','gnu libc','libc'} else 'unknown') if s=='linux' else 'not-applicable';"
        "impl=('cp' if sys.implementation.name=='cpython' else 'pp' if sys.implementation.name=='pypy' else sys.implementation.name[:2]);"
        "abi=(f'cp{sys.version_info.major}{sys.version_info.minor}{getattr(sys,\"abiflags\",\"\")}' if impl=='cp' else '');"
        "print(json.dumps({'python_version':f'{sys.version_info.major}.{sys.version_info.minor}',"
        "'platform':t.get((s,m),f'{s}-{m}'),'libc_family':lf,'implementation':impl,'abi':abi,'executable':sys.executable}))"
    )
    completed = _run([executable, "-X", "utf8", "-c", code], cwd=Path.cwd(), timeout=30)
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise DependencyStudioError("Python probe returned a non-object")
    result = {str(key): str(value) for key, value in payload.items()}
    if result.get("platform", "").startswith("linux-") and result.get("libc_family") == "unknown":
        result["libc_family"] = current_libc_family()
    return result


def _pip_inspect(env_python: Path, *, cwd: Path, timeout: int) -> dict[str, Any]:
    completed = _run([str(env_python), "-m", "pip", "inspect", "--local"], cwd=cwd, timeout=timeout)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise DependencyStudioError(f"pip inspect returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DependencyStudioError("pip inspect returned a non-object")
    return payload


def _inspect_inventory(payload: Mapping[str, Any]) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for item in payload.get("installed") or []:
        if not isinstance(item, Mapping):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        name = str(metadata.get("name") or "").lower().replace("_", "-")
        version = str(metadata.get("version") or "")
        if name and version:
            inventory[name] = version
    return inventory


def install_bundle(
    root: Path | str,
    bundle_dir: Path | str,
    *,
    python_executable: str | None = None,
    environments_root: Path | str | None = None,
    offline: bool = True,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not offline:
        raise DependencyStudioError("Dependency Studio installs only from a verified local wheelhouse; pass --offline")
    project_root = Path(root).resolve()
    bundle = Path(bundle_dir).resolve()
    verification = verify_bundle(bundle)
    if verification.get("ok") is not True:
        raise DependencyStudioError(f"Wheelhouse verification failed: {verification.get('errors')}")
    manifest = read_manifest(bundle / MANIFEST_NAME)
    if manifest is None:
        raise DependencyStudioError("Verified wheelhouse manifest disappeared")

    base_python = str(python_executable or sys.executable)
    probe = _probe_python(base_python)
    target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}
    if str(target.get("alias") or "") != probe["platform"]:
        raise DependencyStudioError("Wheelhouse platform does not match selected interpreter")
    if str(target.get("python_version") or "") != probe["python_version"]:
        raise DependencyStudioError("Wheelhouse Python version does not match selected interpreter")
    if str(target.get("implementation") or "") != probe.get("implementation"):
        raise DependencyStudioError("Wheelhouse Python implementation does not match selected interpreter")
    if str(target.get("abi") or "") != str(probe.get("abi") or ""):
        raise DependencyStudioError("Wheelhouse Python ABI does not match selected interpreter")
    if probe["platform"].startswith("linux-") and str(target.get("libc_family") or "") != probe["libc_family"]:
        raise DependencyStudioError("Wheelhouse libc family does not match selected interpreter")

    requirements = [str(item) for item in manifest.get("requirements") or []]
    import_names = [import_name_for_distribution(project_root, distribution_name_from_requirement(item)) for item in requirements]
    manifest_sha = sha256_file(bundle / MANIFEST_NAME)
    lock_path = bundle / LOCK_NAME
    lock_sha = sha256_file(lock_path)
    contract_fingerprint = str(manifest.get("dependency_contract_fingerprint") or "")
    if not contract_fingerprint:
        raise DependencyStudioError("Wheelhouse manifest is missing dependency_contract_fingerprint")
    envs_root = Path(environments_root).resolve() if environments_root else default_environments_root(project_root)
    alias = probe["platform"]
    pyver = probe["python_version"]
    env_root = envs_root / f"{alias}__py{pyver.replace('.', '')}__{contract_fingerprint[:12]}__{manifest_sha[:12]}"
    env_python = _env_python(env_root)
    create = [base_python, "-m", "venv", str(env_root)]
    install = [
        str(env_python), "-m", "pip", "install", "--disable-pip-version-check",
        "--no-index", "--only-binary=:all:", "--require-hashes", "--find-links", str(bundle),
        "-r", str(lock_path),
    ]
    plan: dict[str, Any] = {
        "environment_root": str(env_root),
        "managed_environments_root": str(envs_root),
        "python_executable": str(env_python),
        "bundle_dir": str(bundle),
        "manifest_sha256": manifest_sha,
        "hash_lock_sha256": lock_sha,
        "dependency_contract_fingerprint": contract_fingerprint,
        "requirements": requirements,
        "profiles": list(manifest.get("profiles") or []),
        "resolved_profiles": list(manifest.get("resolved_profiles") or manifest.get("profiles") or []),
        "offline": True,
        "commands": {"create_venv": create, "install": install, "pip_check": [str(env_python), "-m", "pip", "check"],
                     "pip_inspect": [str(env_python), "-m", "pip", "inspect", "--local"]},
    }
    if dry_run:
        return {"ok": True, "dry_run": True, **plan}

    envs_root.mkdir(parents=True, exist_ok=True)
    if not env_python.is_file():
        if env_root.exists():
            shutil.rmtree(env_root)
        _run(create, cwd=project_root, timeout=timeout_seconds)
    _run(install, cwd=project_root, timeout=timeout_seconds)
    pip_check = _run([str(env_python), "-m", "pip", "check"], cwd=project_root, timeout=timeout_seconds)
    smoke_code = (
        "import importlib,json; names=" + json.dumps(import_names) +
        "; print(json.dumps({n:bool(importlib.import_module(n)) for n in names},sort_keys=True))"
    )
    smoke = _run([str(env_python), "-X", "utf8", "-c", smoke_code], cwd=project_root, timeout=min(timeout_seconds, 300))
    inspect_payload = _pip_inspect(env_python, cwd=project_root, timeout=min(timeout_seconds, 300))
    inventory = _inspect_inventory(inspect_payload)
    expected_inventory = {str(item.get("name") or ""): str(item.get("version") or "") for item in manifest.get("resolved_distributions") or [] if isinstance(item, Mapping)}
    missing = {name: version for name, version in expected_inventory.items() if inventory.get(name) != version}
    if missing:
        raise DependencyStudioError(f"pip inspect inventory does not match wheelhouse manifest: {missing}")

    marker: dict[str, Any] = {
        "schema_version": ENVIRONMENT_SCHEMA,
        "created_for_runtime_version": runtime_version(),
        "dependency_contract_fingerprint": contract_fingerprint,
        "ready": True,
        "project_root": str(project_root),
        "environment_root": str(env_root),
        "managed_environments_root": str(envs_root),
        "python_executable": str(env_python),
        "python_version": pyver,
        "platform": alias,
        "implementation": probe.get("implementation"),
        "abi": probe.get("abi"),
        "libc_family": probe.get("libc_family"),
        "profiles": plan["profiles"],
        "resolved_profiles": plan["resolved_profiles"],
        "requirements": requirements,
        "wheelhouse_bundle": str(bundle),
        "wheelhouse_manifest_sha256": manifest_sha,
        "hash_lock_sha256": lock_sha,
        "pip_check": pip_check.stdout.strip() or "No broken requirements found.",
        "import_smoke": json.loads(smoke.stdout.strip() or "{}"),
        "pip_inspect": inspect_payload,
        "installed_inventory": inventory,
        "truth_boundary": "v2 ready proves verified hash-locked offline wheelhouse install + pip check + import smoke + pip inspect inventory.",
    }
    env_marker = env_root / ENVIRONMENT_MARKER_NAME
    _write_json(env_marker, marker)
    required = set(activation_profile_names(project_root))
    provided = set(str(item) for item in marker["resolved_profiles"])
    activation_eligible = required.issubset(provided)
    activation_marker = environment_marker_path(project_root)
    if activation_eligible:
        _write_json(activation_marker, marker)
    return {"ok": True, "state": "environment_ready" if activation_eligible else "optional_environment_ready",
            "environment_marker_path": str(env_marker), "activation_marker_path": str(activation_marker),
            "activation_marker_updated": activation_eligible, "marker": marker, **plan}


def managed_environment_status(root: Path | str) -> dict[str, Any]:
    project_root = Path(root).resolve()
    marker_path = environment_marker_path(project_root)
    marker = read_manifest(marker_path)
    if marker is None:
        return {"ready": False, "status": "marker_missing", "marker_path": str(marker_path)}
    errors: list[str] = []
    if marker.get("schema_version") != ENVIRONMENT_SCHEMA or marker.get("ready") is not True:
        errors.append("marker_invalid")
    env_root = Path(str(marker.get("environment_root") or "")).expanduser()
    python_path = Path(str(marker.get("python_executable") or "")).expanduser()
    declared = str(marker.get("managed_environments_root") or "").strip()
    allowed = Path(declared).expanduser().resolve() if declared else default_environments_root(project_root).resolve()
    try:
        resolved_env = env_root.resolve(); resolved_env.relative_to(allowed)
    except (OSError, RuntimeError, ValueError):
        resolved_env = env_root; errors.append("environment_root_outside_managed_root")
    try:
        resolved_python = python_path.resolve(); resolved_python.relative_to(resolved_env)
    except (OSError, RuntimeError, ValueError):
        resolved_python = python_path; errors.append("python_outside_environment")
    if not resolved_python.is_file():
        errors.append("python_missing")
    current_python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if str(marker.get("python_version") or "") != current_python_version:
        errors.append("environment_python_target_changed_reinstall_required")
    if str(marker.get("platform") or "") != current_platform_alias():
        errors.append("environment_platform_target_changed_reinstall_required")
    if str(marker.get("implementation") or "") != current_implementation_tag():
        errors.append("environment_implementation_changed_reinstall_required")
    if str(marker.get("abi") or "") != str(current_abi_tag() or ""):
        errors.append("environment_abi_changed_reinstall_required")
    if current_platform_alias().startswith("linux-") and str(marker.get("libc_family") or "") != current_libc_family():
        errors.append("environment_libc_changed_reinstall_required")

    profiles = list(marker.get("resolved_profiles") or marker.get("profiles") or [])
    try:
        current_fingerprint = dependency_contract_fingerprint(project_root, profiles)
    except DependencyStudioError:
        current_fingerprint = ""
    if current_fingerprint and str(marker.get("dependency_contract_fingerprint") or "") != current_fingerprint:
        errors.append("dependency_contract_changed_reinstall_required")
    manifest_path = Path(str(marker.get("wheelhouse_bundle") or "")) / MANIFEST_NAME
    lock_path = manifest_path.parent / LOCK_NAME
    if not manifest_path.is_file():
        errors.append("wheelhouse_manifest_missing")
    elif sha256_file(manifest_path) != str(marker.get("wheelhouse_manifest_sha256") or ""):
        errors.append("wheelhouse_manifest_changed")
    if not lock_path.is_file() or sha256_file(lock_path) != str(marker.get("hash_lock_sha256") or ""):
        errors.append("hash_lock_changed")
    smoke = marker.get("import_smoke") if isinstance(marker.get("import_smoke"), dict) else {}
    if smoke and not all(value is True for value in smoke.values()):
        errors.append("import_smoke_not_ready")
    return {
        "ready": not errors,
        "status": "ready" if not errors else "invalid",
        "marker_path": str(marker_path),
        "python_executable": str(resolved_python),
        "environment_root": str(resolved_env),
        "profiles": list(marker.get("profiles") or []),
        "resolved_profiles": profiles,
        "created_for_runtime_version": marker.get("created_for_runtime_version"),
        "dependency_contract_fingerprint": marker.get("dependency_contract_fingerprint"),
        "errors": errors,
        "wheelhouse_manifest_present": manifest_path.is_file(),
    }


def dependency_activation_status(root: Path | str) -> dict[str, Any]:
    project_root = Path(root).resolve()
    profiles = activation_profile_names(project_root)
    requirements = resolve_profile_requirements(project_root, profiles)
    current = inspect_current_requirements(project_root, requirements)
    python_supported = sys.version_info >= (3, 12)
    current_ready = bool(python_supported and all(item.ready for item in current))
    managed = managed_environment_status(project_root)
    managed_profiles = set(str(item) for item in managed.get("resolved_profiles") or [])
    managed_covers = set(profiles).issubset(managed_profiles)
    marker = read_manifest(environment_marker_path(project_root)) or {}
    try:
        managed_py_ok = tuple(int(part) for part in str(marker.get("python_version") or "").split(".")[:2]) >= (3, 12)
    except (TypeError, ValueError):
        managed_py_ok = False
    managed_ready = bool(managed.get("ready") is True and managed_py_ok and managed_covers)
    required_ready = bool(current_ready or managed_ready)
    return {
        "schema_version": "jazn_dependency_activation_status/v2",
        "required_ready": required_ready,
        "activation_profiles": list(profiles),
        "dependency_contract_fingerprint": dependency_contract_fingerprint(project_root, profiles),
        "requirements": [item.to_dict() for item in current],
        "python_supported": python_supported,
        "minimum_python": "3.12",
        "current_interpreter_ready": current_ready,
        "current_interpreter": sys.executable,
        "managed_environment": managed,
        "managed_environment_covers_required_profiles": managed_covers,
        "selected_source": "current_interpreter" if current_ready else "managed_environment" if managed_ready else "missing",
        "missing_or_incompatible_distributions": [item.distribution for item in current if not item.ready],
        "truth_boundary": "Required readiness proves Python/package availability only; optional capability profiles remain separate.",
    }


def prepare_entrypoint_environment(root: Path | str, *, auto_install: bool = True) -> dict[str, Any]:
    project_root = Path(root).resolve()
    if os.environ.get("JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE") == "1":
        return {"ok": True, "state": "reexec_guard_active", "reexec_python": None}
    status = dependency_activation_status(project_root)
    if status.get("current_interpreter_ready") is True:
        return {"ok": True, "state": "current_interpreter_ready", "reexec_python": None, "status": status}
    managed = status.get("managed_environment") if isinstance(status.get("managed_environment"), dict) else {}
    managed_python = str(managed.get("python_executable") or "")
    if status.get("required_ready") is True and managed.get("ready") is True and managed_python:
        try:
            same = Path(managed_python).resolve() == Path(sys.executable).resolve()
        except (OSError, RuntimeError, ValueError):
            same = managed_python == sys.executable
        return {"ok": True, "state": "managed_environment_ready", "reexec_python": None if same else managed_python, "status": status}
    disabled = os.environ.get("JAZN_DEPENDENCY_AUTOBOOTSTRAP", "1").strip().lower() in {"0", "false", "no", "off"}
    if not auto_install or disabled:
        return {"ok": False, "state": "dependencies_missing_autobootstrap_disabled", "reexec_python": None, "status": status}

    artifact = materialize_compatible_dependency_artifact(project_root)
    explicit = os.environ.get("JAZN_DEPENDENCY_WHEELHOUSE")
    wheelhouse = Path(explicit).expanduser().resolve() if explicit else default_wheelhouse_root(project_root)
    bundles = discover_bundles(project_root, wheelhouse_root=wheelhouse,
                               required_profiles=activation_profile_names(project_root),
                               python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
                               platform_alias=current_platform_alias(), verify=True)
    usable = next((item for item in bundles if (item.get("verification") or {}).get("ok") is True), None)
    if usable is None:
        artifact_state = str(artifact.get("state") or "")
        state = (
            artifact_state
            if artifact_state in {"no_compatible_verified_dependency_bundle", "dependency_package_set_unverified"}
            else "dependencies_missing_no_verified_wheelhouse"
        )
        return {"ok": False, "state": state, "reexec_python": None, "wheelhouse_root": str(wheelhouse),
                "dependency_artifact_discovery": artifact, "status": status}
    installed = install_bundle(project_root, usable["bundle_dir"], offline=True)
    new_python = str((installed.get("marker") or {}).get("python_executable") or "")
    return {"ok": bool(installed.get("ok")), "state": "managed_environment_installed", "reexec_python": new_python or None,
            "installation": installed, "dependency_artifact_discovery": artifact, "status_before": status}


def dependency_environment_gc(root: Path | str, *, dry_run: bool = True) -> dict[str, Any]:
    project_root = Path(root).resolve()
    envs_root = default_environments_root(project_root)
    marker = read_manifest(environment_marker_path(project_root)) or {}
    active = str(marker.get("environment_root") or "")
    active_path = Path(active).resolve() if active else None
    candidates: list[str] = []
    removed: list[str] = []
    if envs_root.is_dir():
        for child in sorted(envs_root.iterdir()):
            if not child.is_dir() or child.is_symlink():
                continue
            try:
                is_active = active_path is not None and child.resolve() == active_path
            except OSError:
                is_active = False
            if is_active:
                continue
            candidates.append(str(child))
            if not dry_run:
                shutil.rmtree(child)
                removed.append(str(child))
    return {"ok": True, "dry_run": dry_run, "managed_environments_root": str(envs_root),
            "active_environment": str(active_path) if active_path else None,
            "gc_candidates": candidates, "removed": removed}
