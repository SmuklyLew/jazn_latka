from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from typing import Any, Sequence

from latka_jazn.python_runtime import (
    PythonRuntimeContractError,
    build_runtime_bundle,
    detect_host_target,
    load_runtime_set,
    materialize_runtime_bundle,
    runtime_target,
    select_runtime_artifact,
    vendor_verified_dependencies,
    verify_runtime_bundle,
    verify_runtime_set,
    write_runtime_set,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="JaznPythonRuntimeStudio",
        description="Build, verify, select and materialize private Jaźń Python runtime bundles.",
        allow_abbrev=False,
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("detect-host", allow_abbrev=False)

    child = sub.add_parser("build", allow_abbrev=False)
    child.add_argument("--project-root", type=Path, default=Path.cwd())
    child.add_argument("--runtime-root", type=Path, required=True)
    child.add_argument("--output", type=Path, required=True)
    child.add_argument("--target", required=True)
    child.add_argument("--python-version", required=True)
    child.add_argument("--libc-family")
    child.add_argument("--provider", required=True)
    child.add_argument("--source-reference")
    child.add_argument("--interpreter", required=True)
    child.add_argument("--packages", default="packages")
    child.add_argument("--dependency-bundle", type=Path)
    child.add_argument("--builder-python")
    child.add_argument("--replace-packages", action="store_true")
    child.add_argument("--dry-run-vendor", action="store_true")

    child = sub.add_parser("verify", allow_abbrev=False)
    child.add_argument("--bundle", type=Path, required=True)

    child = sub.add_parser("build-set", allow_abbrev=False)
    child.add_argument("--output-dir", type=Path, required=True)
    child.add_argument("--bundle", action="append", type=Path, required=True)
    child.add_argument("--copy-bundles", action="store_true")

    child = sub.add_parser("verify-set", allow_abbrev=False)
    child.add_argument("--set", dest="set_path", type=Path, required=True)

    child = sub.add_parser("select", allow_abbrev=False)
    child.add_argument("--set", dest="set_path", type=Path, required=True)
    child.add_argument("--python-version")
    child.add_argument("--materialize-root", type=Path)

    return parser


def execute(ns: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if ns.command == "detect-host":
        return 0, {"ok": True, "command": ns.command, "host": detect_host_target().to_dict()}

    if ns.command == "build":
        target = runtime_target(
            ns.target,
            ns.python_version,
            libc_family=ns.libc_family,
        )
        vendor: dict[str, Any] | None = None
        if ns.dependency_bundle:
            vendor = vendor_verified_dependencies(
                ns.project_root,
                ns.runtime_root,
                ns.dependency_bundle,
                target=target,
                packages_relative_path=ns.packages,
                builder_python=ns.builder_python,
                replace=bool(ns.replace_packages),
                dry_run=bool(ns.dry_run_vendor),
            )
            if ns.dry_run_vendor:
                return 0, {"ok": True, "command": ns.command, "vendor_plan": vendor}
        payload = build_runtime_bundle(
            ns.runtime_root,
            ns.output,
            target=target,
            provider=ns.provider,
            source_reference=ns.source_reference,
            interpreter_relative_path=ns.interpreter,
            packages_relative_path=ns.packages,
        )
        payload["command"] = ns.command
        payload["vendored_dependencies"] = vendor
        return 0, payload

    if ns.command == "verify":
        payload = verify_runtime_bundle(ns.bundle)
        payload["command"] = ns.command
        return (0 if payload.get("ok") else 3), payload

    if ns.command == "build-set":
        destination = Path(ns.output_dir).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        bundles: list[Path] = []
        for raw in ns.bundle:
            source = Path(raw).resolve()
            if ns.copy_bundles:
                target = destination / source.name
                if source != target:
                    shutil.copy2(source, target)
                bundles.append(target)
            else:
                if source.parent != destination:
                    raise PythonRuntimeContractError(
                        "build-set without --copy-bundles requires every bundle to already be in --output-dir"
                    )
                bundles.append(source)
        payload = write_runtime_set(destination, bundles)
        payload["command"] = ns.command
        return 0, payload

    if ns.command == "verify-set":
        set_path = Path(ns.set_path).resolve()
        runtime_set = load_runtime_set(set_path)
        payload = verify_runtime_set(set_path.parent, runtime_set, verify_bundles=True)
        payload["command"] = ns.command
        return (0 if payload.get("ok") else 4), payload

    if ns.command == "select":
        set_path = Path(ns.set_path).resolve()
        runtime_set = load_runtime_set(set_path)
        verification = verify_runtime_set(set_path.parent, runtime_set, verify_bundles=True)
        if verification.get("ok") is not True:
            return 4, {"ok": False, "command": ns.command, "verification": verification}
        selected = select_runtime_artifact(
            runtime_set,
            requested_python=ns.python_version,
        )
        payload: dict[str, Any] = {"ok": True, "command": ns.command, "selected": selected}
        if ns.materialize_root:
            bundle = set_path.parent / str(selected["filename"])
            payload["materialization"] = materialize_runtime_bundle(bundle, ns.materialize_root)
        return 0, payload

    raise PythonRuntimeContractError(f"unsupported_command:{ns.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(list(argv) if argv is not None else None)
    try:
        exit_code, payload = execute(ns)
    except (PythonRuntimeContractError, OSError, ValueError) as exc:
        exit_code = 2
        payload = {
            "ok": False,
            "command": getattr(ns, "command", None),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    if ns.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(f"Jaźń Python Runtime Studio — {payload.get('command')}")
        print(f"Status: {'OK' if payload.get('ok') else 'BLOCKED'}")
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
