from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from typing import Any

from latka_jazn.dependencies.common import (
    LOCK_NAME,
    MANIFEST_NAME,
    distribution_name_from_requirement,
    import_name_for_distribution,
)
from latka_jazn.dependencies.wheelhouse import read_manifest, verify_bundle

from .bundle import safe_relative_path
from .contract import PythonRuntimeContractError, RuntimeTarget


def _probe_builder_python(executable: str) -> dict[str, str]:
    code = (
        "import json,platform,sys;"
        "s=platform.system().lower();m=platform.machine().lower();"
        "t={('windows','amd64'):'windows-x64',('windows','x86_64'):'windows-x64',"
        "('windows','arm64'):'windows-arm64',('windows','aarch64'):'windows-arm64',"
        "('linux','amd64'):'linux-x64',('linux','x86_64'):'linux-x64',"
        "('linux','arm64'):'linux-arm64',('linux','aarch64'):'linux-arm64',"
        "('darwin','amd64'):'macos-x64',('darwin','x86_64'):'macos-x64',"
        "('darwin','arm64'):'macos-arm64',('darwin','aarch64'):'macos-arm64'};"
        "lib=(platform.libc_ver()[0] or '').lower();"
        "lf=('musl' if 'musl' in lib else 'glibc' if lib in {'glibc','gnu libc','libc'} else 'unknown') if s=='linux' else 'not-applicable';"
        "impl='cp' if sys.implementation.name=='cpython' else sys.implementation.name[:2];"
        "abi=f'cp{sys.version_info.major}{sys.version_info.minor}' if impl=='cp' else '';"
        "print(json.dumps({'alias':t.get((s,m),f'{s}-{m}'),'python_version':f'{sys.version_info.major}.{sys.version_info.minor}',"
        "'implementation':impl,'abi':abi,'libc_family':lf}))"
    )
    completed = subprocess.run(
        [executable, "-X", "utf8", "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode:
        raise PythonRuntimeContractError(
            f"builder_python_probe_failed:{completed.returncode}:{completed.stderr.strip()}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PythonRuntimeContractError(f"builder_python_probe_invalid_json:{exc}") from exc
    if not isinstance(payload, dict):
        raise PythonRuntimeContractError("builder_python_probe_not_object")
    return {str(key): str(value) for key, value in payload.items()}


def _assert_builder_matches_target(probe: Mapping[str, str], target: RuntimeTarget) -> None:
    for key, expected in (
        ("alias", target.alias),
        ("python_version", target.python_version),
        ("implementation", target.implementation),
        ("abi", target.abi),
    ):
        if str(probe.get(key) or "") != expected:
            raise PythonRuntimeContractError(
                f"builder_python_target_mismatch:{key}:{probe.get(key)!r}!={expected!r}"
            )
    if target.alias.startswith("linux-") and str(probe.get("libc_family") or "") != target.libc_family:
        raise PythonRuntimeContractError(
            f"builder_python_target_mismatch:libc_family:{probe.get('libc_family')!r}!={target.libc_family!r}"
        )


def vendor_verified_dependencies(
    project_root: Path | str,
    runtime_root: Path | str,
    wheelhouse_bundle: Path | str,
    *,
    target: RuntimeTarget,
    packages_relative_path: str = "packages",
    builder_python: str | None = None,
    replace: bool = False,
    dry_run: bool = False,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    project = Path(project_root).resolve()
    runtime = Path(runtime_root).resolve()
    bundle = Path(wheelhouse_bundle).resolve()
    verification = verify_bundle(bundle)
    if verification.get("ok") is not True:
        raise PythonRuntimeContractError(
            f"wheelhouse_not_verified:{bundle}:{verification.get('errors')}"
        )
    manifest = read_manifest(bundle / MANIFEST_NAME)
    if not isinstance(manifest, Mapping):
        raise PythonRuntimeContractError("verified_wheelhouse_manifest_missing")
    raw_wheel_target = manifest.get("target")
    if not isinstance(raw_wheel_target, Mapping):
        raise PythonRuntimeContractError("verified_wheelhouse_target_missing")
    wheel_target: Mapping[object, object] = raw_wheel_target
    expected = target.to_dict()
    for key in ("alias", "python_version", "implementation", "abi", "libc_family"):
        if str(wheel_target.get(key) or "") != str(expected.get(key) or ""):
            raise PythonRuntimeContractError(
                f"wheelhouse_runtime_target_mismatch:{key}:{wheel_target.get(key)!r}!={expected.get(key)!r}"
            )

    builder = str(builder_python or sys.executable)
    probe = _probe_builder_python(builder)
    _assert_builder_matches_target(probe, target)

    packages_rel = safe_relative_path(packages_relative_path)
    packages = runtime.joinpath(*PurePosixPath(packages_rel).parts)
    try:
        packages.resolve().relative_to(runtime)
    except ValueError as exc:
        raise PythonRuntimeContractError("runtime_packages_path_escape") from exc
    if packages.exists() and any(packages.iterdir()) and not replace:
        raise PythonRuntimeContractError(
            "runtime_packages_not_empty; pass replace=True only for an explicit rebuild"
        )
    lock_path = bundle / LOCK_NAME
    if not lock_path.is_file():
        raise PythonRuntimeContractError("wheelhouse_hash_lock_missing")
    command = [
        builder,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-index",
        "--only-binary=:all:",
        "--require-hashes",
        "--find-links",
        str(bundle),
        "-r",
        str(lock_path),
        "--target",
        str(packages),
    ]
    requirements = [str(item) for item in manifest.get("requirements") or []]
    import_names = [
        import_name_for_distribution(project, distribution_name_from_requirement(item))
        for item in requirements
    ]
    plan = {
        "runtime_root": str(runtime),
        "packages_relative_path": packages_rel,
        "packages_path": str(packages),
        "wheelhouse_bundle": str(bundle),
        "target": target.to_dict(),
        "builder_python": builder,
        "requirements": requirements,
        "command": command,
    }
    if dry_run:
        return {"ok": True, "dry_run": True, **plan}

    if packages.exists() and replace:
        shutil.rmtree(packages)
    packages.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        command,
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(30, int(timeout_seconds)),
        check=False,
    )
    if completed.returncode:
        raise PythonRuntimeContractError(
            f"runtime_dependency_vendor_failed:{completed.returncode}:{completed.stderr.strip() or completed.stdout.strip()}"
        )

    smoke_code = (
        "import importlib,json,sys;"
        f"sys.path.insert(0,{str(packages)!r});"
        f"names={json.dumps(import_names)!r};"
        "names=json.loads(names);"
        "print(json.dumps({n:bool(importlib.import_module(n)) for n in names},sort_keys=True))"
    )
    smoke = subprocess.run(
        [builder, "-I", "-X", "utf8", "-c", smoke_code],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=min(max(30, int(timeout_seconds)), 300),
        check=False,
    )
    if smoke.returncode:
        raise PythonRuntimeContractError(
            f"runtime_dependency_import_smoke_failed:{smoke.returncode}:{smoke.stderr.strip() or smoke.stdout.strip()}"
        )
    return {
        "ok": True,
        "dry_run": False,
        "import_smoke": json.loads(smoke.stdout.strip() or "{}"),
        **plan,
    }
