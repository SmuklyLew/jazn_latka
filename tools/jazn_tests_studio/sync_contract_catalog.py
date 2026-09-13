#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    root_for_import = Path(__file__).resolve().parents[2]
    if str(root_for_import) not in sys.path:
        sys.path.insert(0, str(root_for_import))

from latka_jazn.version import PACKAGE_VERSION
from tools.jazn_tests_studio.migrate_stable_test_contracts import build_contract_catalog


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "tests").is_dir():
            return candidate
    raise SystemExit("repository root not found")


def build_current_catalog(root: Path) -> dict[str, object]:
    """Build the catalog from the active test AST using the canonical generator.

    `migrate_stable_test_contracts` owns the stable-purpose extraction logic.  A
    normal release must not rerun the historical migration itself; it only
    reuses its deterministic catalog builder and stamps the current package
    version into the metadata envelope.
    """

    catalog = dict(build_contract_catalog(root))
    catalog["system_version"] = PACKAGE_VERSION
    return catalog


def serialize_catalog(catalog: dict[str, object]) -> str:
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"


def catalog_path(root: Path) -> Path:
    return root / "tools" / "jazn_tests_studio" / "test_contracts.json"


def write_catalog(root: Path) -> tuple[Path, bool]:
    path = catalog_path(root)
    expected = serialize_catalog(build_current_catalog(root))
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    changed = current != expected
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8")
    return path, changed


def check_catalog(root: Path) -> tuple[bool, str]:
    path = catalog_path(root)
    if not path.is_file():
        return False, f"missing contract catalog: {path}"
    expected = serialize_catalog(build_current_catalog(root))
    current = path.read_text(encoding="utf-8")
    if current == expected:
        return True, "test contract catalog is synchronized"
    return (
        False,
        "test contract catalog is stale; run "
        "python -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --write",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize Jaźń Test Studio contracts with active purpose-based test definitions."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = repo_root()
    if args.write:
        path, changed = write_catalog(root)
        print(
            json.dumps(
                {
                    "ok": True,
                    "changed": changed,
                    "path": str(path.relative_to(root)),
                    "system_version": PACKAGE_VERSION,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    ok, message = check_catalog(root)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
