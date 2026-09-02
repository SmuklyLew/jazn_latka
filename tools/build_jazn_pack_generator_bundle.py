from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import zlib
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "jazn_pack_generator.py"
BEGIN = "# BEGIN AUTO-GENERATED CANONICAL PACKAGE BUNDLE"
END = "# END AUTO-GENERATED CANONICAL PACKAGE BUNDLE"
SOURCES = {
    "latka_jazn.memory.storage_limits": "latka_jazn/memory/storage_limits.py",
    "latka_jazn.packaging.memory_raw_segmentation": "latka_jazn/packaging/memory_raw_segmentation.py",
    "latka_jazn.tools.safe_paths": "latka_jazn/tools/safe_paths.py",
    "latka_jazn.packaging.package_profiles": "latka_jazn/packaging/package_profiles.py",
    "latka_jazn.packaging.package_plan": "latka_jazn/packaging/package_plan.py",
    "latka_jazn.packaging.package_set_contract": "latka_jazn/packaging/package_set_contract.py",
    "latka_jazn.archive.resource_policy": "latka_jazn/archive/resource_policy.py",
    "latka_jazn.archive.service": "latka_jazn/archive/service.py",
    "latka_jazn.archive.hardened_service": "latka_jazn/archive/hardened_service.py",
    "latka_jazn.version": "latka_jazn/version.py",
    "latka_jazn.archive.capabilities": "latka_jazn/archive/capabilities.py",
    "latka_jazn.archive": "latka_jazn/archive/__init__.py",
    "tools._jazn_pack_generator_core": "tools/pack_generator_sources/_jazn_pack_generator_core.py",
    "tools._jazn_pack_generator_memory_v2": "tools/pack_generator_sources/_jazn_pack_generator_memory_v2.py",
    "tools._jazn_pack_generator_v1601_policy": "tools/pack_generator_sources/_jazn_pack_generator_v1601_policy.py",
    "tools._jazn_pack_generator_v1638_archive_io": "tools/pack_generator_sources/_jazn_pack_generator_v1638_archive_io.py",
    "tools._jazn_pack_generator_v16311_profiles": "tools/pack_generator_sources/_jazn_pack_generator_v16311_profiles.py",
}


def payload(source: bytes) -> str:
    return base64.b85encode(zlib.compress(source, 9)).decode("ascii")


def manifest() -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for module, relative in SOURCES.items():
        raw = (ROOT / relative).read_bytes()
        rows[module] = {"source_path": relative, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return rows


def generated_map() -> str:
    lines = ["_BUNDLED_MODULES = {"]
    for module, relative in SOURCES.items():
        raw = (ROOT / relative).read_bytes()
        lines.append(f"    {module!r}: {payload(raw)!r},")
    lines.append("}")
    return "\n".join(lines)


def overlay() -> str:
    mf = json.dumps(manifest(), ensure_ascii=False, sort_keys=True)
    return f"""{BEGIN}\n_CANONICAL_PACKAGE_BUNDLE_MANIFEST = {mf}\n\n# Load current canonical package-policy modules from the same immutable bundle.\nfor _canonical_module_name in (\n    "latka_jazn.tools.safe_paths",\n    "latka_jazn.packaging.package_profiles",\n    "latka_jazn.packaging.package_plan",\n    "latka_jazn.packaging.package_set_contract",\n):\n    if _canonical_module_name not in _bundle_sys.modules:\n        _load_bundled_module(_canonical_module_name)\n\n_canonical_plan = _bundle_sys.modules["latka_jazn.packaging.package_plan"]\n_canonical_contract = _bundle_sys.modules["latka_jazn.packaging.package_set_contract"]\n\ndef _canonical_generator_discover(root, profile):\n    candidates = _canonical_plan.discover_filesystem_candidates(root)\n    selected, _excluded = _canonical_plan.select_candidate_paths(root, candidates, profile=profile)\n    return selected, f"canonical-package-plan:{{profile}}"\n\ndef _canonical_discover_system(root):\n    return _canonical_generator_discover(root, "system")\n\ndef _canonical_discover_memory(root):\n    return _canonical_generator_discover(root, "memory")\n\ndef _canonical_filter_candidates(candidates, *, profile, base_excludes, custom_excludes, manual_excludes_enabled):\n    return _canonical_plan.select_candidate_paths(\n        _impl._core.Path(_impl._core.Path.cwd()).resolve() if False else _canonical_generator_active_root(),\n        candidates, profile=profile, base_excludes=base_excludes, custom_excludes=custom_excludes,\n        manual_excludes_enabled=manual_excludes_enabled,\n    )\n\n_CANONICAL_GENERATOR_ROOT = None\ndef _canonical_generator_active_root():\n    if _CANONICAL_GENERATOR_ROOT is None:\n        raise _impl.PackError("canonical package-plan root was not initialized")\n    return _CANONICAL_GENERATOR_ROOT\n\ndef _canonical_build_plan(root, profile, custom_excludes, **kwargs):\n    global _CANONICAL_GENERATOR_ROOT\n    previous = _CANONICAL_GENERATOR_ROOT\n    _CANONICAL_GENERATOR_ROOT = root\n    try:\n        return _canonical_original_build_plan(root, profile, custom_excludes, **kwargs)\n    finally:\n        _CANONICAL_GENERATOR_ROOT = previous\n\n_core_for_canonical = getattr(_impl, "_core", None)\nif _core_for_canonical is not None:\n    _core_for_canonical.discover_candidates = _canonical_discover_system\n    _core_for_canonical.discover_memory_candidates = _canonical_discover_memory\n    _core_for_canonical.filter_candidates = _canonical_filter_candidates\n    _core_for_canonical.PACKAGE_SET_SCHEMA = _canonical_contract.CURRENT_SCHEMA\n_impl.PACKAGE_SET_SCHEMA = _canonical_contract.CURRENT_SCHEMA\n_canonical_original_build_plan = _impl.build_plan\n_impl.build_plan = _canonical_build_plan\nglobals()["build_plan"] = _canonical_build_plan\nPACKAGE_SET_SCHEMA = _canonical_contract.CURRENT_SCHEMA\n{END}\n"""


def render(original: str) -> str:
    map_pattern = re.compile(r"_BUNDLED_MODULES = \{.*?\n\}\n\n\ndef _ensure_package", re.S)
    if not map_pattern.search(original):
        raise RuntimeError("cannot locate bundled module map")
    text = map_pattern.sub(generated_map() + "\n\n\ndef _ensure_package", original, count=1)
    block_pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
    text = block_pattern.sub("", text)
    marker = "\n_v87_install_overrides()\n"
    if marker not in text:
        raise RuntimeError("cannot locate v8.7 override installation marker")
    text = text.replace(marker, marker + overlay(), 1)
    return text


def execute(*, check: bool) -> int:
    current = GENERATOR.read_text(encoding="utf-8")
    wanted = render(current)
    load_targets = set(re.findall(r'_load_bundled_module\("([^"]+)"(?:,\s*package=True)?\)', wanted))
    missing_targets = sorted(load_targets - set(SOURCES))
    if missing_targets:
        print("Pack Generator bundle is semantically incomplete; missing canonical sources: " + ", ".join(missing_targets))
        return 1
    if check:
        if current != wanted:
            print("Pack Generator bundle is stale. Run build_jazn_pack_generator_bundle.py --write.")
            return 1
        print("Pack Generator bundle matches all canonical source SHA-256 values.")
        return 0
    GENERATOR.write_text(wanted, encoding="utf-8", newline="\n")
    print(json.dumps(manifest(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    ns = parser.parse_args(list(argv) if argv is not None else None)
    return execute(check=bool(ns.check))


if __name__ == "__main__":
    raise SystemExit(main())
