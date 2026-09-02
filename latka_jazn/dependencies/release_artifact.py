from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile

from latka_jazn.dependencies.common import activation_profile_names
from latka_jazn.dependencies.wheelhouse import download_bundle, verify_bundle, read_manifest, sha256_file
from latka_jazn.packaging.package_set_contract import build_single_zip_sidecar
from latka_jazn.version import PACKAGE_VERSION_FULL


def build_dependency_release_artifact(
    root: Path | str,
    output_dir: Path | str,
    *,
    profile_names: Sequence[str] | None = None,
    python_version: str | None = None,
    platform_alias: str | None = None,
    python_executable: str | None = None,
    system_zip: Path | None = None,
) -> dict[str, Any]:
    project_root = Path(root).resolve()
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    profiles = list(profile_names or activation_profile_names(project_root))
    with tempfile.TemporaryDirectory(prefix="jazn-dependency-release-") as temp_raw:
        temp = Path(temp_raw)
        result = download_bundle(
            project_root,
            profile_names=profiles,
            python_version=python_version,
            platform_alias=platform_alias,
            python_executable=python_executable,
            wheelhouse_root=temp / "wheelhouse",
        )
        if result.get("ok") is not True:
            raise RuntimeError(f"dependency wheelhouse download/verification failed: {result}")
        bundle = Path(str(result["bundle_dir"])).resolve()
        verified = verify_bundle(bundle)
        if verified.get("ok") is not True:
            raise RuntimeError(f"dependency wheelhouse verification failed: {verified.get('errors')}")
        manifest = read_manifest(bundle / "JAZN_WHEELHOUSE_MANIFEST.json") or {}
        raw_target = manifest.get("target")
        target: dict[str, Any] = dict(raw_target) if isinstance(raw_target, dict) else {}
        alias = str(target.get("alias") or "unknown")
        pyver = str(target.get("python_version") or "unknown").replace(".", "")
        zip_name = f"jazn_latka_{PACKAGE_VERSION_FULL}-dependencies-{alias}-py{pyver}.zip"
        zip_path = destination / zip_name
        entries: list[dict[str, Any]] = []
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True, compresslevel=6) as archive:
            for source in sorted(p for p in bundle.iterdir() if p.is_file() and not p.is_symlink()):
                arcname = f"{bundle.name}/{source.name}"
                archive.write(source, arcname)
                entries.append({
                    "path": arcname,
                    "size_bytes": source.stat().st_size,
                    "sha256": sha256_file(source),
                    "classification": "dependency_wheelhouse_file",
                })
        related: list[dict[str, Any]] = []
        if system_zip is not None:
            syszip = Path(system_zip).resolve()
            related.append({"role": "system", "filename": syszip.name, "sha256": sha256_file(syszip)})
        sidecar = build_single_zip_sidecar(
            package_name=zip_path.name,
            profile="dependencies",
            package_version=PACKAGE_VERSION_FULL,
            zip_path=zip_path,
            entries=entries,
            artifact_role="dependencies",
            related_artifacts=related,
            generator="latka_jazn.dependencies.release_artifact",
        )
        sidecar_path = zip_path.with_name(zip_path.name + ".package.json")
        sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        parts_path = zip_path.with_name(zip_path.name + ".parts.sha256")
        parts_path.write_text(f"{sha256_file(zip_path)}  {zip_path.name}\n", encoding="ascii")
        return {
            "ok": True,
            "zip_path": str(zip_path),
            "sidecar_path": str(sidecar_path),
            "parts_sha256_path": str(parts_path),
            "wheelhouse_bundle_name": bundle.name,
            "target": target,
            "profiles": profiles,
            "verification": verified,
            "related_artifacts": related,
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--python-version")
    parser.add_argument("--platform", default="current")
    parser.add_argument("--python-executable")
    parser.add_argument("--system-zip", type=Path)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args(list(argv) if argv is not None else None)
    result = build_dependency_release_artifact(
        ns.root, ns.output_dir,
        python_version=ns.python_version,
        platform_alias=ns.platform,
        python_executable=ns.python_executable,
        system_zip=ns.system_zip,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
