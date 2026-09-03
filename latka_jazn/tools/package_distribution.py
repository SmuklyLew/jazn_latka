from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from latka_jazn.dependencies.common import DEPENDENCY_SET_NAME, DEPENDENCY_SET_SCHEMA
from latka_jazn.dependencies.wheelhouse import read_manifest, sha256_file, verify_bundle
from latka_jazn.packaging.dependency_package_contract import build_dependency_sidecar
from latka_jazn.packaging.package_plan import build_distribution_package_plan
from latka_jazn.packaging.package_set_contract import build_v3_package_set, verify_package_set
from latka_jazn.tools.package_export import export_package
from latka_jazn.version import PACKAGE_VERSION_FULL


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z+._-]+", "-", str(value).strip()).strip("-") or "unknown"


def _dependency_filename(manifest: dict[str, Any]) -> str:
    target = _mapping(manifest.get("target"))
    profiles = "+".join(str(item) for item in manifest.get("profiles") or ["core", "archive"])
    alias = _slug(str(target.get("alias") or "unknown"))
    python_version = _slug(str(target.get("python_version") or "unknown").replace(".", ""))
    return (
        f"jazn_latka_v{_slug(PACKAGE_VERSION_FULL)}.dependencies-{_slug(profiles)}"
        f"__{alias}__py{python_version}.zip"
    )


def _dependency_set_payload(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    public: list[dict[str, Any]] = []
    for artifact in artifacts:
        descriptor = _mapping(artifact.get("descriptor"))
        public.append({
            "role": "dependencies",
            "filename": artifact.get("filename"),
            "size_bytes": artifact.get("size_bytes"),
            "sha256": artifact.get("sha256"),
            "bundle_name": descriptor.get("bundle_name"),
            "profiles": descriptor.get("profiles") or [],
            "target": descriptor.get("target") or {},
            "dependency_contract_fingerprint": descriptor.get("dependency_contract_fingerprint"),
            "wheelhouse_manifest_sha256": descriptor.get("wheelhouse_manifest_sha256"),
            "hash_lock_sha256": descriptor.get("hash_lock_sha256"),
        })
    return {
        "schema_version": DEPENDENCY_SET_SCHEMA,
        "runtime_version": PACKAGE_VERSION_FULL,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": public,
        "selection_contract": "Match verified SHA-256 plus target alias, Python, implementation/ABI and libc; filename alone is never authoritative.",
        "network_fallback_allowed": False,
    }


def build_distribution_set(
    root: Path | str,
    output_dir: Path | str,
    *,
    mode: str,
    dependency_bundles: Sequence[Path | str] = (),
    target_alias: str | None = None,
    python_version: str | None = None,
) -> dict[str, Any]:
    project_root = Path(root).resolve()
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    plan = build_distribution_package_plan(
        mode,
        target_alias=target_alias,
        python_version=python_version,
    )

    dependency_artifacts: list[dict[str, Any]] = []
    if plan.include_dependencies:
        if not dependency_bundles:
            raise ValueError("dependency-bearing distribution mode requires at least one verified dependency bundle")
        for raw_bundle in dependency_bundles:
            bundle = Path(raw_bundle).resolve()
            verification = verify_bundle(bundle)
            if verification.get("ok") is not True:
                raise ValueError(f"dependency bundle is not verified: {bundle}: {verification.get('errors')}")
            manifest = read_manifest(bundle / "JAZN_WHEELHOUSE_MANIFEST.json") or {}
            target = _mapping(manifest.get("target"))
            if target_alias and str(target.get("alias") or "") != target_alias:
                raise ValueError(f"dependency bundle target mismatch: {target.get('alias')!r} != {target_alias!r}")
            if python_version and str(target.get("python_version") or "") != python_version:
                raise ValueError(
                    f"dependency bundle Python mismatch: {target.get('python_version')!r} != {python_version!r}"
                )
            sidecar = destination / _dependency_filename(manifest)
            dependency_artifacts.append(build_dependency_sidecar(bundle, sidecar))

    dependency_set = _dependency_set_payload(dependency_artifacts)
    dependency_set_text = json.dumps(dependency_set, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    outputs: list[dict[str, Any]] = []
    roles: list[str] = []

    if plan.include_system:
        system_name = f"jazn_latka_v{_slug(PACKAGE_VERSION_FULL)}"
        if plan.include_memory:
            system_name += ".system+memory"
        elif plan.include_dependencies:
            system_name += ".system-portable"
        else:
            system_name += ".system-thin"
        if plan.include_dependencies:
            system_name += f"__{_slug(target_alias or 'current')}__py{_slug((python_version or '').replace('.', ''))}"
        system_zip = destination / f"{system_name}.zip"
        export_mode = "full" if plan.include_memory else "system"
        export = export_package(
            project_root,
            export_mode,
            system_zip,
            virtual_files={DEPENDENCY_SET_NAME: dependency_set_text},
        )
        outputs.append({
            "filename": system_zip.name,
            "size_bytes": system_zip.stat().st_size,
            "sha256": export.sha256,
            "role": "system+memory" if plan.include_memory else "system",
            "is_complete_zip": True,
        })
        roles.extend(["system"] + (["memory"] if plan.include_memory else []))
    elif plan.include_memory:
        memory_zip = destination / f"jazn_latka_v{_slug(PACKAGE_VERSION_FULL)}.memory.zip"
        export = export_package(project_root, "memory", memory_zip)
        outputs.append({
            "filename": memory_zip.name,
            "size_bytes": memory_zip.stat().st_size,
            "sha256": export.sha256,
            "role": "memory",
            "is_complete_zip": True,
        })
        roles.append("memory")

    for artifact in dependency_artifacts:
        outputs.append({
            "filename": artifact["filename"],
            "size_bytes": artifact["size_bytes"],
            "sha256": artifact["sha256"],
            "role": "dependencies",
            "is_complete_zip": True,
        })
        if "dependencies" not in roles:
            roles.append("dependencies")

    package_name = f"jazn_latka_v{_slug(PACKAGE_VERSION_FULL)}.{_slug(mode)}"
    package_set = build_v3_package_set(
        package_name=package_name,
        package_version=PACKAGE_VERSION_FULL,
        profile=roles[0] if roles else "dependencies",
        roles=roles,
        outputs=outputs,
        dependency_artifacts=dependency_set["artifacts"],
        generator="latka_jazn.tools.package_distribution",
        generator_version="1",
    )
    package_set_path = destination / f"{package_name}.package.json"
    package_set_path.write_text(
        json.dumps(package_set, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dependency_set_path = destination / DEPENDENCY_SET_NAME
    dependency_set_path.write_text(dependency_set_text, encoding="utf-8")
    package_set_errors = verify_package_set(destination, package_set)
    if package_set_errors:
        raise ValueError(f"built package set failed verification: {package_set_errors}")
    return {
        "ok": True,
        "mode": mode,
        "runtime_version": PACKAGE_VERSION_FULL,
        "plan": plan.to_dict(),
        "package_set_path": str(package_set_path),
        "dependency_set_path": str(dependency_set_path),
        "package_set": package_set,
        "package_set_verification": {"ok": True, "errors": []},
        "dependency_set": dependency_set,
        "outputs": outputs,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Jaźń package-distribution artifact sets.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--dependency-bundle", action="append", default=[])
    parser.add_argument("--target")
    parser.add_argument("--python-version")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_distribution_set(
            args.root,
            args.output_dir,
            mode=args.mode,
            dependency_bundles=args.dependency_bundle,
            target_alias=args.target,
            python_version=args.python_version,
        )
    except Exception as exc:
        report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
