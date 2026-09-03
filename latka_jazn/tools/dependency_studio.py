from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from latka_jazn.dependencies.runtime import (
    DependencyStudioError,
    activation_profile_names,
    audit_project_dependencies,
    benchmark_dependency_layer,
    current_platform_alias,
    default_wheelhouse_root,
    discover_bundles,
    download_bundle,
    dependency_environment_gc,
    install_bundle,
    normalize_python_version,
    verify_bundle,
)


def _profile_list(value: str | None, *, default: Sequence[str]) -> list[str]:
    if not value:
        return list(default)
    result: list[str] = []
    for part in str(value).split(","):
        item = part.strip()
        if item and item not in result:
            result.append(item)
    return result or list(default)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="JaznDependencyStudio",
        description="Terminal operator Studio for versioned Jaźń Python wheelhouses and offline environments.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Jaźń repository/runtime root.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--wheelhouse-root", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("audit", allow_abbrev=False)

    for name in ("download", "update"):
        child = sub.add_parser(name, allow_abbrev=False)
        child.add_argument("--profile", default="core,archive")
        child.add_argument("--python-version")
        child.add_argument("--platform", default="current")
        child.add_argument("--python-executable")
        child.add_argument("--lock-file", type=Path)
        child.add_argument("--dry-run", action="store_true")

    child = sub.add_parser("verify", allow_abbrev=False)
    child.add_argument("--bundle", type=Path)
    child.add_argument("--profile")
    child.add_argument("--python-version")
    child.add_argument("--platform")

    child = sub.add_parser("install", allow_abbrev=False)
    child.add_argument("--bundle", type=Path)
    child.add_argument("--profile", default="core,archive")
    child.add_argument("--python-executable")
    child.add_argument("--environment-root", type=Path)
    child.add_argument("--offline", action="store_true")
    child.add_argument("--dry-run", action="store_true")

    sub.add_parser("benchmark", allow_abbrev=False)

    child = sub.add_parser("gc", allow_abbrev=False)
    child.add_argument("--dry-run", action="store_true")
    child.add_argument("--apply", action="store_true")
    return parser


def _latest_verified_bundle(
    root: Path,
    *,
    profiles: Sequence[str],
    wheelhouse_root: Path | None,
) -> Path:
    bundles = discover_bundles(
        root,
        wheelhouse_root=wheelhouse_root,
        required_profiles=profiles,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
        platform_alias=current_platform_alias(),
        verify=True,
    )
    for item in bundles:
        if (item.get("verification") or {}).get("ok") is True:
            return Path(str(item["bundle_dir"]))
    raise DependencyStudioError(
        "No verified wheelhouse bundle matches the current Python/platform and requested profiles"
    )


def execute(ns: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    root = Path(ns.root).resolve()
    wheelhouse = Path(ns.wheelhouse_root).resolve() if ns.wheelhouse_root else None

    if ns.command == "audit":
        payload = audit_project_dependencies(root)
        unresolved = payload.get("undeclared_or_unmapped_external_imports") or {}
        payload["ok"] = bool(payload.get("ok") and not unresolved)
        payload["command"] = "audit"
        return (0 if payload["ok"] else 3), payload

    if ns.command in {"download", "update"}:
        profiles = _profile_list(ns.profile, default=activation_profile_names(root))
        payload = download_bundle(
            root,
            profile_names=profiles,
            python_version=ns.python_version,
            platform_alias=ns.platform,
            python_executable=ns.python_executable,
            wheelhouse_root=wheelhouse,
            lock_file=ns.lock_file,
            timeout_seconds=ns.timeout_seconds,
            dry_run=bool(ns.dry_run),
        )
        if isinstance(payload.get("command"), list):
            payload["pip_command"] = payload.pop("command")
        payload["command"] = ns.command
        if ns.command == "update":
            if payload.get("state") == "bundle_downloaded":
                payload["state"] = "updated_bundle_created"
            elif payload.get("state") == "bundle_reused":
                payload["state"] = "no_dependency_changes"
        return (0 if payload.get("ok") else 4), payload

    if ns.command == "verify":
        if ns.bundle:
            payload = verify_bundle(ns.bundle)
            payload["command"] = "verify"
            return (0 if payload.get("ok") else 5), payload
        profiles = _profile_list(ns.profile, default=[])
        bundles = discover_bundles(
            root,
            wheelhouse_root=wheelhouse,
            required_profiles=profiles,
            python_version=ns.python_version,
            platform_alias=ns.platform,
            verify=True,
        )
        ok = bool(bundles) and all((item.get("verification") or {}).get("ok") is True for item in bundles)
        payload = {
            "command": "verify",
            "ok": ok,
            "wheelhouse_root": str(wheelhouse or default_wheelhouse_root(root)),
            "bundle_count": len(bundles),
            "bundles": bundles,
        }
        return (0 if ok else 5), payload

    if ns.command == "install":
        if not ns.offline:
            raise DependencyStudioError(
                "Install is intentionally fail-closed. Pass --offline to install only from a verified local wheelhouse."
            )
        profiles = _profile_list(ns.profile, default=activation_profile_names(root))
        bundle = Path(ns.bundle).resolve() if ns.bundle else _latest_verified_bundle(
            root,
            profiles=profiles,
            wheelhouse_root=wheelhouse,
        )
        payload = install_bundle(
            root,
            bundle,
            python_executable=ns.python_executable,
            environments_root=ns.environment_root,
            offline=True,
            timeout_seconds=ns.timeout_seconds,
            dry_run=bool(ns.dry_run),
        )
        payload["command"] = "install"
        return (0 if payload.get("ok") else 6), payload

    if ns.command == "benchmark":
        payload = benchmark_dependency_layer(root, wheelhouse_root=wheelhouse)
        payload["command"] = "benchmark"
        return (0 if payload.get("ok") else 7), payload

    if ns.command == "gc":
        if ns.dry_run and ns.apply:
            raise DependencyStudioError("Choose either --dry-run or --apply, not both")
        payload = dependency_environment_gc(root, dry_run=not bool(ns.apply))
        payload["command"] = "gc"
        return 0, payload

    raise DependencyStudioError(f"Unsupported command: {ns.command}")


def _human(payload: dict[str, Any]) -> str:
    command = str(payload.get("command") or "dependency-studio")
    lines = [f"Jaźń Dependency Studio — {command}", f"Status: {'OK' if payload.get('ok') else 'BLOCKED'}"]
    if command == "audit":
        activation = payload.get("activation") or {}
        lines.extend([
            f"Runtime dependencies: {'ready' if activation.get('required_ready') else 'missing/incompatible'}",
            f"External imports: {payload.get('external_import_count')}",
            f"Declared distributions: {payload.get('declared_distribution_count')}",
            f"Unmapped imports: {len(payload.get('undeclared_or_unmapped_external_imports') or {})}",
            f"Wheelhouse: {payload.get('wheelhouse_root')}",
        ])
    elif command in {"download", "update"}:
        if payload.get("dry_run"):
            lines.append("Dry run — no network/download performed.")
            lines.append("Command: " + " ".join(str(item) for item in payload.get("pip_command") or []))
        else:
            lines.extend([
                f"Bundle: {payload.get('bundle_dir')}",
                f"State: {payload.get('state')}",
                f"Wheels: {(payload.get('verification') or {}).get('wheel_count')}",
            ])
    elif command == "verify":
        lines.append(f"Bundles: {payload.get('bundle_count', 1)}")
        if payload.get("errors"):
            lines.append(f"Errors: {len(payload.get('errors') or [])}")
    elif command == "install":
        lines.extend([
            f"Environment: {payload.get('environment_root')}",
            f"Python: {payload.get('python_executable')}",
            "Mode: offline / --no-index / verified wheelhouse",
        ])
    elif command == "benchmark":
        lines.extend([
            f"Dependency probe: {payload.get('activation_probe_seconds')} s",
            f"Wheelhouse verify: {payload.get('wheelhouse_verify_seconds')} s",
            f"Verified bundles: {payload.get('verified_bundle_count')}",
        ])
    elif command == "gc":
        lines.extend([
            f"Mode: {'dry-run' if payload.get('dry_run') else 'apply'}",
            f"Candidates: {len(payload.get('gc_candidates') or [])}",
            f"Removed: {len(payload.get('removed') or [])}",
        ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(list(argv) if argv is not None else None)
    try:
        exit_code, payload = execute(ns)
    except DependencyStudioError as exc:
        payload = {
            "ok": False,
            "command": ns.command,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        exit_code = 2
    if ns.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(_human(payload))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
