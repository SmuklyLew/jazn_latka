"""Describe canonical argparse forms and invoke the existing studio commands.

Runs in the selected external Python, so the desktop binary never becomes a
frozen copy of the memory/test/package engines. No private data is in schemas.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import importlib
import json
import sys
from typing import Any

MODULES = {
    "memory": ("latka_jazn.tools.memory_rebuild_app.cli", "build_parser"),
    "rebuild": ("latka_jazn.tools.memory_rebuild_app.cli", "build_parser"),
    "tests": ("tools.jazn_tests_studio.app", "build_parser"),
    "packages": ("tools.jazn_pack_generator", "_parser"),
    "dependencies": ("latka_jazn.tools.dependency_studio", "build_parser"),
    "python": ("latka_jazn.tools.python_runtime_studio", "build_parser"),
}


def commands(parser: argparse.ArgumentParser, path: list[str] | None = None,
             inherited: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    path, inherited = path or [], inherited or []
    fields: list[dict[str, Any]] = []
    children = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            children.extend(action.choices.items())
            continue
        if action.dest in {"help", "version", "ui", "text_ui", "no_splash", "root"} or action.help == argparse.SUPPRESS:
            continue
        fields.append({"id": str(len(inherited) + len(fields)), "dest": action.dest,
            "options": action.option_strings, "required": action.required,
            "help": action.help or action.dest, "nargs": action.nargs,
            "choices": [str(v) for v in action.choices] if action.choices else [],
            "flag": action.nargs == 0, "append": isinstance(action, argparse._AppendAction),
            "depth": len(path)})
    accumulated = inherited + fields
    if children:
        result = []
        for name, child in children:
            if name not in {"studio", "window", "tui"}:
                result.extend(commands(child, path + [name], accumulated))
        return result
    return [{"path": path, "description": parser.description or " ".join(path), "fields": accumulated}]


def argv_for(command: dict[str, Any], values: dict[str, Any]) -> list[str]:
    known = {f["id"] for f in command["fields"]}
    if set(values) - known:
        raise ValueError("Unknown command fields")
    output = []
    for depth in range(len(command["path"]) + 1):
        if depth:
            output.append(command["path"][depth - 1])
        for field in command["fields"]:
            if field["depth"] != depth:
                continue
            value = values.get(field["id"])
            if value is None or value == "" or value is False:
                if field["required"] and field["nargs"] not in ("?", "*"):
                    raise ValueError("Required field: " + field["dest"])
                continue
            option = field["options"][0] if field["options"] else None
            if field["flag"]:
                if value is not True or not option:
                    raise ValueError("Invalid flag")
                output.append(option)
                continue
            entries = value if isinstance(value, list) else [value]
            if not entries or any(not isinstance(v, str) or "\0" in v or len(v) > 8192 for v in entries):
                raise ValueError("Invalid argument values")
            if field["append"]:
                for entry in entries:
                    if option:
                        output.append(option)
                    output.append(entry)
            else:
                if option:
                    output.append(option)
                output.extend(entries)
    return output


def preview_fingerprint(spec: dict[str, Any]) -> str:
    """Hash exact operator inputs without retaining private arguments in UI evidence."""
    encoded = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 65536:
        raise ValueError("Operation preview input limit")
    return sha256(encoded).hexdigest()


def preview_command(command: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Validate the original command shape; this never executes a domain operation."""
    if not isinstance(spec, dict) or set(spec) != {"path", "values"}:
        raise ValueError("Invalid preview shape")
    if spec["path"] != command["path"] or not isinstance(spec["values"], dict):
        raise ValueError("Preview selection mismatch")
    argv = argv_for(command, spec["values"])
    return {"schema": "jazn_studio_command_preview/v1", "path": list(command["path"]),
            "fingerprint": preview_fingerprint(spec), "argument_count": len(argv),
            "requires_confirmation": True, "execution_performed": False,
            "displays_raw_arguments": False}


def profile(operation: str, data: dict[str, Any]) -> dict[str, Any]:
    from pathlib import Path
    from latka_jazn.tools.configuration_studio import (
        SETTINGS, ENUMS, inspect_system, preview_profile_changes, profile_snapshot,
        restore_previous_profile, save_profile, validate_values, validated_launch_values, profile_file,
    )
    root = Path.cwd()
    if operation == "profile-env":
        return validated_launch_values(root)
    if operation == "profile-paths":
        return {"schema": "jazn_config_path_map/v1", "rows": inspect_system(root),
                "read_only": True, "runtime_ready": False}
    if operation == "profile-validate":
        values = validate_values(root, data["values"])
        return {"schema": "jazn_config_validation/v1", "count": len(values),
                "saved": False, "runtime_activated": False}
    if operation == "profile-preview":
        return preview_profile_changes(root, data["values"], expected_sha256=data.get("digest"))
    if operation == "profile-save":
        save_profile(root, data["values"], expected_sha256=data.get("digest"))
    if operation == "profile-restore":
        restore_previous_profile(root, expected_sha256=data.get("digest"))
    values, digest = profile_snapshot(root)
    return {"schema": "jazn_config_snapshot/v1", "values": values, "digest": digest,
            "profile_path": str(profile_file(root)),
            "fields": [{"key": s.key, "title": s.title, "hint": s.hint,
                        "kind": s.kind, "section": s.section,
                        "choices": sorted(ENUMS.get(s.kind, []))} for s in SETTINGS],
            "future_launch_only": True, "runtime_activated": False}


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("mode", choices=["schema", "preview", "execute", "profile-read", "profile-save", "profile-env", "profile-paths", "profile-preview", "profile-validate", "profile-restore", "version-inspect"])
    parser.add_argument("key", nargs="?", choices=sorted(MODULES))
    args = parser.parse_args()
    if args.mode.startswith("profile-"):
        raw = sys.stdin.buffer.read(32769) if args.mode in {"profile-save", "profile-preview", "profile-validate", "profile-restore"} else b"{}"
        if len(raw) > 32768:
            raise ValueError("Profile input limit")
        print(json.dumps(profile(args.mode, json.loads(raw)), ensure_ascii=False))
        return 0
    if args.mode == "version-inspect":
        from pathlib import Path
        from tools.jazn_version_rebuild import read_version
        item = read_version(Path.cwd())
        print(json.dumps({
            "schema": "jazn_version_readonly_inspection/v1",
            "package": item.package, "name": item.name, "version": item.version,
            "full": item.full, "read_only": True, "execution_performed": False,
        }, ensure_ascii=False))
        return 0
    if not args.key:
        parser.error("Studio key is required")
    name, factory = MODULES[args.key]
    module = importlib.import_module(name)
    canonical = getattr(module, factory)()
    schema = commands(canonical)
    if args.mode == "schema":
        print(json.dumps(schema, ensure_ascii=False))
        return 0
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError("Operation input limit")
    spec = json.loads(raw)
    if not isinstance(spec, dict) or not isinstance(spec.get("path"), list):
        raise ValueError("Invalid operation payload")
    selected = next(c for c in schema if c["path"] == spec["path"])
    if args.mode == "preview":
        report = preview_command(selected, spec)
        canonical.parse_args(argv_for(selected, spec["values"]))  # Original validation only.
        print(json.dumps(report, ensure_ascii=False))
        return 0
    argv = argv_for(selected, spec["values"])
    canonical.parse_args(argv)  # Original types/required/mutual-exclusion rules.
    return int(module.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
