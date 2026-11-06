"""Explicit operator provisioning for ROOT-local Jaźń prerequisites.

This is a bounded JSS adapter, not the Jaźń runtime or a second dependency
resolver. Dependency resolution and SHA-256 validation belong to Dependency
Studio. None of these actions runs during a normal conversation turn.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_MODEL = "gemma3:latest"
MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}(?::[A-Za-z0-9][A-Za-z0-9._-]{0,127})?$")
OLLAMA_BASE = "http://127.0.0.1:11434"


class ProvisioningError(RuntimeError):
    """An explicit prerequisite operation failed without changing runtime authority."""


def root_paths(root: str | Path) -> dict[str, Path]:
    project = Path(root).expanduser().resolve()
    if not ((project / "run.py").is_file() and (project / "latka_jazn").is_dir()):
        raise ProvisioningError("not_a_jazn_system_root")
    resources = project / "local_resources"
    return {
        "root": project,
        "venv": project / ".venv",
        "resources": resources,
        "wheelhouse": resources / "wheelhouse",
        "python": resources / "python",
        "ollama": resources / "ollama",
        "models": resources / "models",
        "nlp": resources / "nlp",
        "manifests": resources / "manifests",
    }


def prepare_resources(root: str | Path, *, approved: bool) -> dict[str, Any]:
    if not approved:
        raise ProvisioningError("explicit_operator_approval_required")
    paths = root_paths(root)
    for name in ("resources", "wheelhouse", "python", "ollama", "models", "nlp", "manifests"):
        target = paths[name]
        if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
            raise ProvisioningError("local_resources_link_not_allowed")
        target.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "state": "root_resources_prepared", "resources": str(paths["resources"])}


def venv_python(root: str | Path) -> Path:
    folder = root_paths(root)["venv"]
    return folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def python_314(executable: str | Path) -> bool:
    try:
        outcome = subprocess.run(
            [str(executable), "-I", "-c",
             "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,14) else 3)"],
            capture_output=True, timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return outcome.returncode == 0


def inspect(root: str | Path) -> dict[str, Any]:
    paths = root_paths(root)
    executable = venv_python(root)
    executable_ready = executable.is_file() and python_314(executable)
    detected_ollama = detect_ollama()
    api = ollama_api("GET", "/api/tags", timeout=3)
    models = [
        str(item.get("name"))
        for item in api.get("models", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ] if api.get("ok") else []
    return {
        "schema_version": "jazn_jss_prerequisites/v1",
        "ready": executable_ready,
        "root": str(paths["root"]),
        "venv_path": str(paths["venv"]),
        "venv_python": str(executable),
        "python_314_ready": executable_ready,
        "local_resources": str(paths["resources"]),
        "wheelhouse_present": paths["wheelhouse"].is_dir(),
        "ollama_executable": detected_ollama or None,
        "ollama_api_ready": api.get("ok") is True,
        "models": models,
        "default_model": DEFAULT_MODEL,
        "default_model_present": DEFAULT_MODEL in models or "gemma3:4b" in models,
        "runtime_ready": None,  # deliberately not inferred from dependencies or Ollama
    }


def prepare_venv(root: str | Path, *, base_python: str, approved: bool) -> dict[str, Any]:
    if not approved:
        raise ProvisioningError("explicit_operator_approval_required")
    paths = root_paths(root)
    target = paths["venv"]
    target_python = venv_python(root)
    if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
        raise ProvisioningError("root_venv_link_not_allowed")
    if target.exists():
        if not (target / "pyvenv.cfg").is_file() or not python_314(target_python):
            raise ProvisioningError("existing_root_venv_invalid_manual_recovery_required")
        return {"ok": True, "state": "existing_venv_reused", "python": str(target_python)}
    if not python_314(base_python):
        raise ProvisioningError("python_3_14_required")
    outcome = subprocess.run(
        [str(base_python), "-I", "-m", "venv", str(target)],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180, check=False,
    )
    if outcome.returncode or not python_314(target_python):
        # Preserve incomplete state for explicit recovery; never delete an
        # unexpectedly concurrent operator-owned directory.
        raise ProvisioningError("venv_creation_failed_manual_recovery_required")
    return {"ok": True, "state": "created", "python": str(target_python)}


def _verify_bundle(root: str | Path, bundle: str | Path) -> tuple[Path, Path]:
    from latka_jazn.dependencies.common import LOCK_NAME, MANIFEST_NAME
    from latka_jazn.dependencies.wheelhouse import verify_bundle, read_manifest

    directory = Path(bundle).expanduser().resolve()
    paths = root_paths(root)
    if not directory.is_dir() or not directory.is_relative_to(paths["wheelhouse"].resolve()):
        raise ProvisioningError("bundle_must_be_in_root_wheelhouse")
    verified = verify_bundle(directory)
    if verified.get("ok") is not True:
        raise ProvisioningError("wheelhouse_verification_failed")
    manifest = read_manifest(directory / MANIFEST_NAME)
    target = manifest.get("target") if isinstance(manifest, dict) else None
    if not isinstance(target, dict) or target.get("python_version") != "3.14":
        raise ProvisioningError("wheelhouse_python_target_mismatch")
    if target.get("alias") != ("windows-x64" if os.name == "nt" else "linux-x64"):
        raise ProvisioningError("wheelhouse_platform_target_mismatch")
    profiles = set(str(item) for item in (manifest.get("resolved_profiles") or manifest.get("profiles") or []))
    if not {"core", "run-studio"}.issubset(profiles):
        raise ProvisioningError("core_and_run_studio_profiles_required")
    return directory, directory / LOCK_NAME


def _record_verified_environment(root: str | Path, directory: Path,
                                 requirements_path: Path, python: Path) -> dict[str, Any]:
    """Commit the canonical v2 marker only after pip+imports+inventory verification."""
    from latka_jazn.dependencies.common import (
        ENVIRONMENT_SCHEMA, MANIFEST_NAME, activation_profile_names,
        canonicalize_distribution_name, current_libc_family, current_platform_alias,
        dependency_contract_fingerprint, distribution_name_from_requirement,
        environment_marker_path, import_name_for_distribution, runtime_version,
    )
    from latka_jazn.dependencies.wheelhouse import read_manifest, sha256_file

    root_dir = root_paths(root)["root"]
    manifest = read_manifest(directory / MANIFEST_NAME)
    if not isinstance(manifest, dict):
        raise ProvisioningError("verified_manifest_missing")
    profiles = [str(value) for value in (manifest.get("resolved_profiles") or
                                         manifest.get("profiles") or [])]
    if not set(activation_profile_names(root_dir)).issubset(set(profiles)):
        raise ProvisioningError("activation_profiles_missing")
    fingerprint = dependency_contract_fingerprint(root_dir, profiles)
    if fingerprint != str(manifest.get("dependency_contract_fingerprint") or ""):
        raise ProvisioningError("dependency_contract_mismatch")
    requirements = [str(req) for req in manifest.get("requirements") or []]
    imports = sorted({import_name_for_distribution(root_dir, distribution_name_from_requirement(req))
                      for req in requirements})
    if not imports or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", name) for name in imports):
        raise ProvisioningError("unsafe_or_empty_import_smoke")
    smoke_code = (
        "import importlib,json; names=" + json.dumps(imports) +
        "; print(json.dumps({n:bool(importlib.import_module(n)) for n in names}))"
    )
    smoke = subprocess.run([str(python), "-X", "utf8", "-c", smoke_code],
                           cwd=root_dir, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300, check=False)
    if smoke.returncode:
        raise ProvisioningError("direct_requirement_import_failed")
    try:
        import_smoke = json.loads(smoke.stdout)
    except json.JSONDecodeError as exc:
        raise ProvisioningError("import_smoke_invalid_json") from exc
    if not isinstance(import_smoke, dict) or not all(x is True for x in import_smoke.values()):
        raise ProvisioningError("import_smoke_not_ready")

    inspection = subprocess.run(
        [str(python), "-m", "pip", "inspect", "--local"],
        cwd=root_dir, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300, check=False,
    )
    if inspection.returncode:
        raise ProvisioningError("pip_inspect_failed")
    try:
        inspected = json.loads(inspection.stdout)
    except json.JSONDecodeError as exc:
        raise ProvisioningError("pip_inspect_invalid_json") from exc
    if not isinstance(inspected, dict):
        raise ProvisioningError("pip_inspect_invalid_shape")
    inventory: dict[str, str] = {}
    for item in inspected.get("installed") or []:
        metadata = item.get("metadata") if isinstance(item, dict) else {}
        if isinstance(metadata, dict) and metadata.get("name") and metadata.get("version"):
            inventory[canonicalize_distribution_name(str(metadata["name"]))] = str(metadata["version"])
    expected = {
        canonicalize_distribution_name(str(item["name"])): str(item["version"])
        for item in manifest.get("resolved_distributions") or []
        if isinstance(item, dict) and item.get("name") and item.get("version")
    }
    if not expected or any(inventory.get(name) != version for name, version in expected.items()):
        raise ProvisioningError("pip_inventory_mismatch")

    path = environment_marker_path(root_dir)
    env_marker = root_dir / ".venv" / "JAZN_DEPENDENCY_ENVIRONMENT.json"
    if path.exists() or env_marker.exists():
        raise ProvisioningError("environment_marker_exists_use_explicit_repair")
    payload: dict[str, Any] = {
        "schema_version": ENVIRONMENT_SCHEMA,
        "created_for_runtime_version": runtime_version(),
        "dependency_contract_fingerprint": fingerprint,
        "ready": True,
        "project_root": str(root_dir),
        "environment_root": str(root_dir / ".venv"),
        "environment_identity": "root-local-py314-" + sha256_file(directory / MANIFEST_NAME)[:12],
        "managed_environments_root": str(root_dir),
        "python_executable": str(python),
        "python_version": "3.14",
        "platform": current_platform_alias(),
        "implementation": "cp",
        "abi": "cp314",
        "libc_family": current_libc_family(),
        "profiles": list(manifest.get("profiles") or []),
        "resolved_profiles": profiles,
        "requirements": requirements,
        "wheelhouse_bundle": str(directory),
        "wheelhouse_manifest_sha256": sha256_file(directory / MANIFEST_NAME),
        "hash_lock_sha256": sha256_file(requirements_path),
        "pip_check": "No broken requirements found.",
        "import_smoke": import_smoke,
        "pip_inspect": inspected,
        "installed_inventory": inventory,
        "truth_boundary": "Ready after verified offline wheelhouse, pip check, imports and inventory.",
    }
    for destination in (env_marker, path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        if temporary.exists():
            raise ProvisioningError("environment_marker_staging_conflict")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                             encoding="utf-8")
        os.replace(temporary, destination)
    return {"marker_path": str(path), "environment_root": str(root_dir / ".venv"),
            "installed_distributions": len(expected)}


def install_offline(root: str | Path, *, bundle: str | Path, approved: bool) -> dict[str, Any]:
    if not approved:
        raise ProvisioningError("explicit_operator_approval_required")
    from latka_jazn.core.runtime_root import active_runtime_marker_path
    marker = active_runtime_marker_path(root_paths(root)["root"])
    if marker.is_file():
        raise ProvisioningError("runtime_marker_present_verify_live_state_before_install")
    directory, requirements = _verify_bundle(root, bundle)
    python = venv_python(root)
    if not python_314(python):
        raise ProvisioningError("root_venv_python_314_missing")
    commands = (
        [str(python), "-m", "pip", "install", "--disable-pip-version-check",
         "--no-index", "--only-binary=:all:", "--require-hashes",
         "--find-links", str(directory), "-r", str(requirements)],
        [str(python), "-m", "pip", "check"],
    )
    for command in commands:
        result = subprocess.run(command, cwd=root_paths(root)["root"],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=1800, check=False)
        if result.returncode:
            raise ProvisioningError("offline_install_or_pip_check_failed")
    receipt = _record_verified_environment(root, directory, requirements, python)
    return {"ok": True, "state": "installed_verified_and_marked",
            "python": str(python), **receipt}


def download_dependencies(root: str | Path, *, base_python: str, approved: bool) -> dict[str, Any]:
    if not approved:
        raise ProvisioningError("explicit_operator_approval_required")
    if not python_314(base_python):
        raise ProvisioningError("python_3_14_required")
    paths = root_paths(root)
    paths["wheelhouse"].mkdir(parents=True, exist_ok=True)
    # Reuse canonical Dependency Studio resolution and its wheelhouse contract.
    command = [
        str(base_python), "-X", "utf8", "-m", "latka_jazn.tools.dependency_studio",
        "--root", str(paths["root"]), "--wheelhouse-root", str(paths["wheelhouse"]),
        "--json", "download", "--profile", "core,run-studio",
        "--python-version", "3.14", "--platform", "current",
        "--python-executable", str(base_python),
    ]
    result = subprocess.run(command, cwd=paths["root"], capture_output=True,
                            text=True, encoding="utf-8", errors="replace",
                            timeout=1800, check=False)
    if result.returncode:
        raise ProvisioningError("dependency_studio_download_failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProvisioningError("dependency_studio_invalid_json") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ProvisioningError("dependency_studio_download_not_verified")
    return {"ok": True, "bundle_dir": payload.get("bundle_dir"),
            "state": payload.get("state")}


def detect_ollama() -> str:
    candidate = shutil.which("ollama")
    if candidate and Path(candidate).is_file():
        return candidate
    if os.name == "nt":
        app = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if app.is_file():
            return str(app)
    return ""


def ollama_api(method: str, route: str, *, payload: dict[str, Any] | None = None,
               timeout: float = 5) -> dict[str, Any]:
    if route not in {"/api/tags", "/api/chat"}:
        raise ProvisioningError("ollama_api_route_not_allowed")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(OLLAMA_BASE + route, method=method, data=body,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return {"ok": False, "error_code": "ollama_http_error"}
            content = json.load(response)
        return {"ok": True, **content} if isinstance(content, dict) else {"ok": False}
    except (OSError, HTTPError, URLError, ValueError):
        return {"ok": False, "error_code": "ollama_unreachable_or_invalid"}


def ollama_pull(*, model: str = DEFAULT_MODEL, approved: bool,
                progress: Any = None) -> dict[str, Any]:
    if not approved:
        raise ProvisioningError("explicit_operator_approval_required")
    if not MODEL_NAME.fullmatch(model):
        raise ProvisioningError("invalid_model_name")
    request = Request(
        OLLAMA_BASE + "/api/pull", method="POST",
        data=json.dumps({"model": model, "stream": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=1800) as response:
            last: dict[str, Any] = {}
            for line in response:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ProvisioningError("ollama_pull_invalid_event")
                if item.get("error"):
                    raise ProvisioningError("ollama_pull_rejected")
                last = item
                if callable(progress):
                    completed, total = item.get("completed"), item.get("total")
                    progress({
                        "model": model,
                        "status": str(item.get("status") or "")[:100],
                        "completed": completed if isinstance(completed, int) else None,
                        "total": total if isinstance(total, int) else None,
                    })
    except (OSError, HTTPError, URLError, json.JSONDecodeError) as exc:
        raise ProvisioningError("ollama_pull_failed") from exc
    if last.get("status") != "success":
        raise ProvisioningError("ollama_pull_unconfirmed")
    return {"ok": True, "model": model, "state": "downloaded"}


def install_python_windows(*, approved: bool) -> dict[str, Any]:
    if not approved:
        raise ProvisioningError("explicit_operator_approval_required")
    if os.name != "nt":
        raise ProvisioningError("windows_only")
    winget = shutil.which("winget")
    if not winget:
        raise ProvisioningError("winget_missing_use_official_python_installer")
    result = subprocess.run([
        winget, "install", "--id", "Python.Python.3.14", "--exact", "--source", "winget",
        "--accept-source-agreements", "--accept-package-agreements",
    ], capture_output=True, timeout=1200, check=False)
    if result.returncode:
        raise ProvisioningError("python_winget_install_failed")
    return {"ok": True, "state": "installer_completed_recheck_required"}


def start_ollama(*, approved: bool, launch: str = "cli") -> dict[str, Any]:
    if not approved:
        raise ProvisioningError("explicit_operator_approval_required")
    if ollama_api("GET", "/api/tags", timeout=2).get("ok") is True:
        return {"ok": True, "state": "already_running"}
    executable = detect_ollama()
    if not executable:
        raise ProvisioningError("ollama_not_installed")
    if launch not in {"cli", "app"}:
        raise ProvisioningError("unsupported_ollama_launch_mode")
    if launch == "app":
        if os.name != "nt":
            raise ProvisioningError("ollama_app_windows_only")
        # Ollama's Windows GUI is independent of the CLI server process.
        candidate = Path(executable).with_name("Ollama app.exe")
        if not candidate.is_file():
            raise ProvisioningError("ollama_app_executable_missing")
        command = [str(candidate)]
    else:
        command = [executable, "serve"]
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=flags)
    except OSError as exc:
        raise ProvisioningError("ollama_process_start_failed") from exc
    # Starting a process is not evidence of API readiness.
    return {"ok": True, "state": "spawned_unverified", "pid": process.pid,
            "requires_followup_api_check": True}


def install_ollama_windows(*, approved: bool) -> dict[str, Any]:
    if not approved:
        raise ProvisioningError("explicit_operator_approval_required")
    if os.name != "nt":
        raise ProvisioningError("windows_only")
    winget = shutil.which("winget")
    if not winget:
        raise ProvisioningError("winget_missing_use_official_ollama_installer")
    result = subprocess.run([
        winget, "install", "--id", "Ollama.Ollama", "--exact", "--source", "winget",
        "--accept-source-agreements", "--accept-package-agreements",
    ], capture_output=True, timeout=1200, check=False)
    if result.returncode:
        raise ProvisioningError("ollama_winget_install_failed")
    return {"ok": True, "state": "installer_completed_recheck_required"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JSS — jawne przygotowanie ROOT/.venv, wheelhouse i Ollamy")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect")
    prepare = sub.add_parser("prepare-resources")
    prepare.add_argument("--yes", action="store_true")
    for name in ("prepare-venv", "download-deps"):
        operation = sub.add_parser(name)
        operation.add_argument("--python", required=True)
        operation.add_argument("--yes", action="store_true")
    install = sub.add_parser("install-offline")
    install.add_argument("--bundle", required=True)
    install.add_argument("--yes", action="store_true")
    for name in ("install-python", "install-ollama", "start-ollama", "pull-model"):
        operation = sub.add_parser(name)
        operation.add_argument("--yes", action="store_true")
        if name == "pull-model":
            operation.add_argument("--model", default=DEFAULT_MODEL)
        if name == "start-ollama":
            operation.add_argument("--launch", choices=("cli", "app"), default="cli")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            data = inspect(args.root)
        elif args.command == "prepare-resources":
            data = prepare_resources(args.root, approved=args.yes)
        elif args.command == "install-python":
            data = install_python_windows(approved=args.yes)
        elif args.command == "start-ollama":
            data = start_ollama(approved=args.yes, launch=args.launch)
        elif args.command == "prepare-venv":
            data = prepare_venv(args.root, base_python=args.python, approved=args.yes)
        elif args.command == "download-deps":
            data = download_dependencies(args.root, base_python=args.python, approved=args.yes)
        elif args.command == "install-offline":
            data = install_offline(args.root, bundle=args.bundle, approved=args.yes)
        elif args.command == "install-ollama":
            data = install_ollama_windows(approved=args.yes)
        else:
            data = ollama_pull(
                model=args.model, approved=args.yes,
                progress=lambda event: print(
                    json.dumps({"progress": event}, ensure_ascii=False), flush=True
                ),
            )
    except ProvisioningError as exc:
        print(json.dumps({"ok": False, "error_code": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
