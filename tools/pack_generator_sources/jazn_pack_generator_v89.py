from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

GENERATOR_VERSION = "8.9"
SETTINGS_SCHEMA = "jazn_pack_generator_settings/v8.9"
DISTRIBUTION_MODE_CHOICES = (
    "system-thin",
    "system-portable",
    "memory-only",
    "dependencies-only",
    "system+memory",
    "system+memory+dependencies",
)
DISTRIBUTION_TARGET_CHOICES = ("current", "windows-x64", "linux-x64")
DISTRIBUTION_PYTHON_CHOICES = ("current", "3.12", "3.13", "3.13.5", "3.14")
MANAGED_PYTHON_RESOURCE_EXCLUDE = "latka_jazn/local_resources/python/**"


def _load_legacy():
    source = Path(__file__).with_name("jazn_pack_generator_v88.py")
    spec = importlib.util.spec_from_file_location("_jazn_pack_generator_v88_legacy", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load legacy generator core: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


legacy = _load_legacy()


def _legacy_core():
    return getattr(getattr(legacy, "_impl", None), "_core", None)


def _install_legacy_safety_overlay() -> None:
    core = _legacy_core()
    if core is None:
        return
    legacy.GENERATOR_VERSION = GENERATOR_VERSION
    legacy.SETTINGS_SCHEMA = SETTINGS_SCHEMA
    if hasattr(legacy, "_impl"):
        legacy._impl.GENERATOR_VERSION = GENERATOR_VERSION
        legacy._impl.SETTINGS_SCHEMA = SETTINGS_SCHEMA
    core.GENERATOR_VERSION = GENERATOR_VERSION
    core.SETTINGS_SCHEMA = SETTINGS_SCHEMA
    original = getattr(core, "build_plan", None)
    if not callable(original) or getattr(original, "_jazn_v89_safe", False):
        return

    def build_plan(*args, **kwargs):
        base_excludes = tuple(kwargs.get("base_excludes") or ())
        if MANAGED_PYTHON_RESOURCE_EXCLUDE not in base_excludes:
            base_excludes += (MANAGED_PYTHON_RESOURCE_EXCLUDE,)
        kwargs["base_excludes"] = base_excludes
        return original(*args, **kwargs)

    build_plan._jazn_v89_safe = True  # type: ignore[attr-defined]
    core.build_plan = build_plan
    if hasattr(legacy, "_impl"):
        legacy._impl.build_plan = build_plan
    legacy.build_plan = build_plan


_install_legacy_safety_overlay()


def normalize_distribution_python_version(value: str | None) -> str:
    raw = str(value or "current").strip().lower()
    if raw in {"", "current"}:
        return f"{sys.version_info.major}.{sys.version_info.minor}"
    parts = raw.split(".")
    if len(parts) not in {2, 3} or any(not item.isdigit() for item in parts):
        raise ValueError(f"invalid Python version: {value!r}")
    return f"{int(parts[0])}.{int(parts[1])}"


def distribution_mode_plan(
    mode: str,
    *,
    target_alias: str | None = None,
    python_version: str | None = None,
) -> dict[str, Any]:
    normalized = str(mode or "").strip().lower()
    if normalized not in DISTRIBUTION_MODE_CHOICES:
        raise ValueError(f"unsupported distribution mode: {mode!r}")
    include_system = normalized in {"system-thin", "system-portable", "system+memory", "system+memory+dependencies"}
    include_memory = normalized in {"memory-only", "system+memory", "system+memory+dependencies"}
    include_dependencies = normalized in {"dependencies-only", "system-portable", "system+memory+dependencies"}
    target = str(target_alias or "current").strip().lower()
    if include_dependencies and target not in DISTRIBUTION_TARGET_CHOICES:
        raise ValueError(f"unsupported distribution target: {target_alias!r}")
    requested_python = str(python_version or "current").strip()
    resolved_python = normalize_distribution_python_version(requested_python)
    return {
        "schema_version": "jazn_pack_generator_distribution_plan/v2",
        "generator_version": GENERATOR_VERSION,
        "mode": normalized,
        "system": include_system,
        "memory": include_memory,
        "dependencies": include_dependencies,
        "target_runtime": (
            {
                "alias": target,
                "python_version": resolved_python,
                "requested_python_version": requested_python,
            }
            if include_dependencies
            else None
        ),
    }


def _bundle_manifest(path: Path) -> dict[str, Any] | None:
    manifest = path / "JAZN_WHEELHOUSE_MANIFEST.json"
    if not manifest.is_file():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def find_matching_dependency_bundle(
    source: Path | str,
    target_alias: str,
    python_version: str,
) -> Path | None:
    source_root = Path(source).expanduser().resolve()
    target = str(target_alias or "current").strip().lower()
    python_minor = normalize_distribution_python_version(python_version)
    wheelhouse = source_root / "latka_jazn" / "local_resources" / "python" / "wheelhouse"
    if not wheelhouse.is_dir():
        return None
    for candidate in sorted(path for path in wheelhouse.iterdir() if path.is_dir()):
        manifest = _bundle_manifest(candidate)
        if manifest is None:
            continue
        raw_target = manifest.get("target")
        if not isinstance(raw_target, dict):
            continue
        alias = str(raw_target.get("alias") or "").strip().lower()
        py = normalize_distribution_python_version(str(raw_target.get("python_version") or ""))
        if alias == target and py == python_minor:
            return candidate.resolve()
    return None


def _run_json(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        list(command), cwd=str(cwd), env=env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"command failed ({result.returncode}): {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not return JSON: {result.stdout[-2000:]}") from exc
    if not isinstance(payload, dict) or payload.get("ok") is False:
        raise RuntimeError(f"command reported failure: {payload}")
    return payload


def materialize_native_dependency_bundle(
    source: Path | str,
    *,
    target_alias: str,
    python_version: str,
) -> Path:
    source_root = Path(source).expanduser().resolve()
    target = str(target_alias or "current").strip().lower()
    python_minor = normalize_distribution_python_version(python_version)
    current_alias = "windows-x64" if os.name == "nt" else ("linux-x64" if sys.platform.startswith("linux") else "current")
    if target not in {"current", current_alias}:
        raise RuntimeError(
            "Cross-target dependency materialization is forbidden. Build the dependency bundle on its native runner."
        )
    wheelhouse_root = source_root / "latka_jazn" / "local_resources" / "python" / "wheelhouse"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(source_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    report = _run_json(
        [
            sys.executable, "-X", "utf8", "-m", "latka_jazn.tools.dependency_studio",
            "--root", str(source_root), "--wheelhouse-root", str(wheelhouse_root), "--json",
            "download", "--profile", "core", "--profile", "archive",
            "--python-version", python_minor, "--platform", "current",
        ],
        cwd=source_root,
        env=env,
    )
    bundle = Path(str(report.get("bundle_dir") or "")).resolve()
    manifest = _bundle_manifest(bundle)
    if manifest is None:
        raise RuntimeError(f"materialized dependency bundle lacks manifest: {bundle}")
    return bundle


def run_distribution_pack(
    *,
    source: Path | str,
    out_dir: Path | str,
    mode: str,
    target_alias: str = "current",
    python_version: str = "current",
    dependency_bundle: Path | str | None = None,
    materialize_dependencies: bool = False,
) -> dict[str, Any]:
    source_root = Path(source).expanduser().resolve()
    destination = Path(out_dir).expanduser().resolve()
    plan = distribution_mode_plan(mode, target_alias=target_alias, python_version=python_version)
    target = str(target_alias or "current").strip().lower()
    python_minor = normalize_distribution_python_version(python_version)
    bundle: Path | None = None
    if plan["dependencies"]:
        if dependency_bundle:
            bundle = Path(dependency_bundle).expanduser().resolve()
        else:
            bundle = find_matching_dependency_bundle(source_root, target, python_minor)
        if bundle is None and materialize_dependencies:
            bundle = materialize_native_dependency_bundle(
                source_root, target_alias=target, python_version=python_minor,
            )
        if bundle is None:
            raise RuntimeError(
                f"No verified dependency bundle for {target}/py{python_minor}. "
                "Select a native bundle or enable native materialization."
            )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(source_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    command = [
        sys.executable, "-X", "utf8", "-m", "latka_jazn.tools.package_distribution",
        "--root", str(source_root), "--output-dir", str(destination), "--mode", str(mode), "--json",
    ]
    if plan["dependencies"]:
        command += ["--target", target, "--python-version", python_minor, "--dependency-bundle", str(bundle)]
    report = _run_json(command, cwd=source_root, env=env)
    package_set = report.get("package_set")
    if not isinstance(package_set, dict) or package_set.get("schema_version") != "jazn_package_set/v3":
        raise RuntimeError("canonical package-distribution command did not produce jazn_package_set/v3")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "distribution-pack":
        parser = argparse.ArgumentParser(prog="jazn_pack_generator.py distribution-pack", allow_abbrev=False)
        parser.add_argument("mode", choices=DISTRIBUTION_MODE_CHOICES)
        parser.add_argument("--source", default=".")
        parser.add_argument("--out-dir", required=True)
        parser.add_argument("--target", default="current", choices=DISTRIBUTION_TARGET_CHOICES)
        parser.add_argument("--python-version", default="current", choices=DISTRIBUTION_PYTHON_CHOICES)
        parser.add_argument("--dependency-bundle")
        parser.add_argument("--materialize-dependencies", action="store_true")
        args = parser.parse_args(raw[1:])
        try:
            report = run_distribution_pack(
                source=args.source, out_dir=args.out_dir, mode=args.mode,
                target_alias=args.target, python_version=args.python_version,
                dependency_bundle=args.dependency_bundle,
                materialize_dependencies=args.materialize_dependencies,
            )
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    return int(legacy.main(raw))


def __getattr__(name: str) -> Any:
    return getattr(legacy, name)
