from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.python_runtime import runtime_target_from_mapping, verify_runtime_bundle

_CORE: Any = None
_ORIGINAL_RUN_DISTRIBUTION_PACK: Any = None


def _runtime_bundle_candidates(source: Path) -> tuple[Path, ...]:
    explicit = str(os.environ.get("JAZN_PYTHON_RUNTIME_BUNDLE") or "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    try:
        workspace = workspace_runtime_path(source)
        candidates.extend(
            [
                workspace / "local_resources" / "python_runtime" / "bundles",
                workspace / "local_resources" / "python_runtime",
            ]
        )
    except (OSError, RuntimeError, ValueError):
        pass
    candidates.extend(
        [
            source / "latka_jazn" / "local_resources" / "python_runtime" / "bundles",
            source / "latka_jazn" / "local_resources" / "python_runtime",
        ]
    )
    unique: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            resolved = candidate.absolute()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def find_matching_python_runtime_bundle(
    source: Path | str,
    target_alias: str,
    python_version: str,
) -> Path | None:
    source_root = Path(source).expanduser().resolve()
    target = _CORE.resolve_distribution_target_alias(target_alias)
    python_minor = _CORE.normalize_distribution_python_version(python_version)
    for candidate in _runtime_bundle_candidates(source_root):
        paths = [candidate] if candidate.is_file() else (
            sorted(candidate.glob("*.zip")) if candidate.is_dir() else []
        )
        for bundle in paths:
            verification = verify_runtime_bundle(bundle)
            if verification.get("ok") is not True:
                continue
            manifest = verification.get("manifest")
            if not isinstance(manifest, Mapping):
                continue
            try:
                runtime_target = runtime_target_from_mapping(
                    manifest.get("target") if isinstance(manifest.get("target"), Mapping) else {}
                )
            except ValueError:
                continue
            if runtime_target.alias == target and runtime_target.python_version == python_minor:
                return Path(bundle).resolve()
    return None


def run_distribution_pack(
    *,
    source: Path | str,
    out_dir: Path | str,
    mode: str,
    target_alias: str = "current",
    python_version: str = "current",
    dependency_bundle: Path | str | None = None,
    materialize_dependencies: bool = False,
    python_runtime_bundle: Path | str | None = None,
) -> dict[str, Any]:
    source_root = Path(source).expanduser().resolve()
    destination = Path(out_dir).expanduser().resolve()
    plan = _CORE.distribution_mode_plan(mode, target_alias=target_alias, python_version=python_version)
    target = _CORE.resolve_distribution_target_alias(target_alias)
    python_minor = _CORE.normalize_distribution_python_version(python_version)

    bundle: Path | None = None
    if plan["dependencies"]:
        if dependency_bundle:
            bundle = Path(dependency_bundle).expanduser().resolve()
        else:
            bundle = _CORE.find_matching_dependency_bundle(source_root, target, python_minor)
        if bundle is None and materialize_dependencies:
            bundle = _CORE.materialize_dependency_bundle(
                source_root, target_alias=target, python_version=python_minor
            )
        if bundle is None:
            raise _CORE.PackError(
                f"Brak zweryfikowanego dependency bundle dla {target}/py{python_minor}. "
                "Wskaż bundle albo włącz target-aware materializację zależności."
            )

    runtime_bundle: Path | None = None
    if plan["system"]:
        if python_runtime_bundle:
            runtime_bundle = Path(python_runtime_bundle).expanduser().resolve()
        else:
            runtime_bundle = find_matching_python_runtime_bundle(
                source_root, target, python_minor
            )
        if runtime_bundle is not None:
            verification = verify_runtime_bundle(runtime_bundle)
            if verification.get("ok") is not True:
                raise _CORE.PackError(
                    f"Python runtime bundle nie przeszedł weryfikacji: {verification.get('errors')}"
                )
            manifest = verification.get("manifest")
            if not isinstance(manifest, Mapping):
                raise _CORE.PackError("Python runtime bundle nie ma zweryfikowanego manifestu.")
            runtime_target = runtime_target_from_mapping(
                manifest.get("target") if isinstance(manifest.get("target"), Mapping) else {}
            )
            if runtime_target.alias != target or runtime_target.python_version != python_minor:
                raise _CORE.PackError(
                    f"Python runtime bundle nie pasuje do {target}/py{python_minor}: {runtime_target.target_id}"
                )

    env = dict(os.environ)
    env["PYTHONPATH"] = str(source_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    command = [
        _CORE.sys.executable,
        "-X",
        "utf8",
        "-m",
        "latka_jazn.tools.package_distribution",
        "--root",
        str(source_root),
        "--output-dir",
        str(destination),
        "--mode",
        str(mode),
        "--json",
    ]
    if plan["dependencies"]:
        command += [
            "--target",
            target,
            "--python-version",
            python_minor,
            "--dependency-bundle",
            str(bundle),
        ]
    if runtime_bundle is not None:
        if not plan["dependencies"]:
            command += ["--target", target, "--python-version", python_minor]
        command += ["--python-runtime-bundle", str(runtime_bundle)]

    report = _CORE._run_json(command, cwd=source_root, env=env)
    package_set = report.get("package_set")
    if not isinstance(package_set, dict) or package_set.get("schema_version") != "jazn_package_set/v3":
        raise RuntimeError("canonical package-distribution command did not produce jazn_package_set/v3")
    report["python_runtime"] = {
        "requested": str(python_runtime_bundle) if python_runtime_bundle else None,
        "selected": str(runtime_bundle) if runtime_bundle else None,
        "portable_interpreter_included": runtime_bundle is not None,
        "target": target if runtime_bundle else None,
        "python_version": python_minor if runtime_bundle else None,
    }
    return report


def install(core: Any) -> None:
    global _CORE, _ORIGINAL_RUN_DISTRIBUTION_PACK
    _CORE = core
    _ORIGINAL_RUN_DISTRIBUTION_PACK = core.run_distribution_pack
    core.find_matching_python_runtime_bundle = find_matching_python_runtime_bundle
    core.run_distribution_pack = run_distribution_pack
