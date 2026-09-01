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
    MANIFEST_NAME,
    DependencyStudioError,
    activation_profile_names,
    current_platform_alias,
    default_environments_root,
    default_wheelhouse_root,
    distribution_name_from_requirement,
    environment_marker_path,
    import_name_for_distribution,
    inspect_current_requirements,
    resolve_profile_requirements,
    runtime_version,
)
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
        "print(json.dumps({'python_version':f'{sys.version_info.major}.{sys.version_info.minor}',"
        "'platform':t.get((s,m),f'{s}-{m}'),'executable':sys.executable}))"
    )
    completed = _run([executable, "-X", "utf8", "-c", code], cwd=Path.cwd(), timeout=30)
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise DependencyStudioError("Python probe returned a non-object")
    return {str(key): str(value) for key, value in payload.items()}


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

    requirements = [str(item) for item in manifest.get("requirements") or []]
    import_names = [
        import_name_for_distribution(project_root, distribution_name_from_requirement(item))
        for item in requirements
    ]
    manifest_sha = sha256_file(bundle / MANIFEST_NAME)
    envs_root = Path(environments_root).resolve() if environments_root else default_environments_root(project_root)
    alias = probe["platform"]
    pyver = probe["python_version"]
    env_root = envs_root / f"{alias}__py{pyver.replace('.', '')}__{manifest_sha[:12]}"
    env_python = _env_python(env_root)
    create = [base_python, "-m", "venv", str(env_root)]
    install = [
        str(env_python), "-m", "pip", "install", "--disable-pip-version-check",
        "--no-index", "--find-links", str(bundle), *requirements,
    ]
    plan: dict[str, Any] = {
        "environment_root": str(env_root),
        "managed_environments_root": str(envs_root),
        "python_executable": str(env_python),
        "bundle_dir": str(bundle),
        "manifest_sha256": manifest_sha,
        "requirements": requirements,
        "profiles": list(manifest.get("profiles") or []),
        "resolved_profiles": list(manifest.get("resolved_profiles") or manifest.get("profiles") or []),
        "offline": True,
        "commands": {"create_venv": create, "install": install, "pip_check": [str(env_python), "-m", "pip", "check"]},
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
    marker: dict[str, Any] = {
        "schema_version": ENVIRONMENT_SCHEMA,
        "runtime_version": runtime_version(),
        "ready": True,
        "project_root": str(project_root),
        "environment_root": str(env_root),
        "managed_environments_root": str(envs_root),
        "python_executable": str(env_python),
        "python_version": pyver,
        "platform": alias,
        "profiles": plan["profiles"],
        "resolved_profiles": plan["resolved_profiles"],
        "requirements": requirements,
        "wheelhouse_bundle": str(bundle),
        "wheelhouse_manifest_sha256": manifest_sha,
        "pip_check": pip_check.stdout.strip() or "No broken requirements found.",
        "import_smoke": json.loads(smoke.stdout.strip() or "{}"),
        "truth_boundary": "ready=true proves verified local wheelhouse install + pip check + direct import smoke; it does not certify package security.",
    }
    env_marker = env_root / ENVIRONMENT_MARKER_NAME
    _write_json(env_marker, marker)
    required = set(activation_profile_names(project_root))
    provided = set(str(item) for item in marker["resolved_profiles"])
    activation_eligible = required.issubset(provided)
    activation_marker = environment_marker_path(project_root)
    if activation_eligible:
        _write_json(activation_marker, marker)
    return {
        "ok": True,
        "state": "environment_ready" if activation_eligible else "optional_environment_ready",
        "environment_marker_path": str(env_marker),
        "activation_marker_path": str(activation_marker),
        "activation_marker_updated": activation_eligible,
        "marker": marker,
        **plan,
    }


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
        resolved_env = env_root.resolve()
        resolved_env.relative_to(allowed)
    except (OSError, RuntimeError, ValueError):
        resolved_env = env_root
        errors.append("environment_root_outside_managed_root")
    try:
        resolved_python = python_path.resolve()
        resolved_python.relative_to(resolved_env)
    except (OSError, RuntimeError, ValueError):
        resolved_python = python_path
        errors.append("python_outside_environment")
    if not resolved_python.is_file():
        errors.append("python_missing")
    observed_runtime = str(marker.get("runtime_version") or "")
    if runtime_version() != "unknown" and observed_runtime not in {runtime_version(), "unknown"}:
        errors.append("runtime_version_changed_reinstall_required")
    manifest_path = Path(str(marker.get("wheelhouse_bundle") or "")) / MANIFEST_NAME
    expected_sha = str(marker.get("wheelhouse_manifest_sha256") or "")
    if not manifest_path.is_file():
        errors.append("wheelhouse_manifest_missing")
    elif sha256_file(manifest_path) != expected_sha:
        errors.append("wheelhouse_manifest_changed")
    return {
        "ready": not errors,
        "status": "ready" if not errors else "invalid",
        "marker_path": str(marker_path),
        "python_executable": str(resolved_python),
        "environment_root": str(resolved_env),
        "profiles": list(marker.get("profiles") or []),
        "resolved_profiles": list(marker.get("resolved_profiles") or marker.get("profiles") or []),
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
    required_ready = bool(current_ready or (managed.get("ready") is True and managed_py_ok and managed_covers))
    return {
        "schema_version": "jazn_dependency_activation_status/v1",
        "required_ready": required_ready,
        "activation_profiles": list(profiles),
        "requirements": [item.to_dict() for item in current],
        "python_supported": python_supported,
        "minimum_python": "3.12",
        "current_interpreter_ready": current_ready,
        "current_interpreter": sys.executable,
        "managed_environment": managed,
        "managed_environment_covers_required_profiles": managed_covers,
        "selected_source": "current_interpreter" if current_ready else "managed_environment" if managed.get("ready" is True and managed_covers else "missing",
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
    explicit = os.environ.get("JAZN_DEPENDENCY_WHEELHSUSE")
    wheelhouse = Path(explicit).expanduser().resolve() if explicit else default_wheelhouse_root(project_root)
    bundles = discover_bundles(
        project_root,
        wheelhouse_root=wheelhouse,
        required_profiles=activation_profile_names(project_root),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
        platform_alias=current_platform_alias(),
        verify=True,
    )
    usable = next((item for item in bundles if (item.get("verification") or {}).get("ok") is True), None)
    if usable is None:
        return {"ok": False, "state": "dependencies_missing_no_verified_wheelhouse", "reexec_pythoon": None, "wheelhouse_root": str(wheelhouse), "status": status}
    installed = install_bundle(project_root, usable["bundle_dir"], offline=True)
    new_python = str((installed.get("marker") or {}).get("python_executable") or "")
    return {"ok": bool(installed.get("ok")), "state": "managed_environment_installed", "reexec_python": new_python or None, "installation": installed, "status_before": status}
