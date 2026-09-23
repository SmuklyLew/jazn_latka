from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.tools.version_consistency_audit import (
    _generated_metadata_errors,
    scan_forbidden_current_literals,
)
from latka_jazn.version import (
    DISTRIBUTION_VERSION,
    PACKAGE_RELEASE_NAME,
    PACKAGE_VERSION,
    PACKAGE_VERSION_FULL,
    contract_schema_version,
)


def _write_version(root: Path) -> None:
    version_file = root / "latka_jazn" / "version.py"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(
        f"DISTRIBUTION_VERSION = {DISTRIBUTION_VERSION!r}\n"
        f"PACKAGE_VERSION = {PACKAGE_VERSION!r}\n"
        f"PACKAGE_RELEASE_NAME = {PACKAGE_RELEASE_NAME!r}\n",
        encoding="utf-8",
    )


def test_generated_metadata_audit_uses_stable_contract_schema(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write_version(root)
    (root / "pyproject.toml").write_text(
        '[project]\ndynamic = ["version"]\n'
        '[tool.setuptools.dynamic]\n'
        'version = {attr = "latka_jazn.version.DISTRIBUTION_VERSION"}\n',
        encoding="utf-8",
    )
    (root / "PACKAGE_INTEGRITY_MANIFEST.json").write_text(
        json.dumps(
            {
                "version": PACKAGE_VERSION_FULL,
                "runtime_version": PACKAGE_VERSION_FULL,
                "package_version": PACKAGE_VERSION_FULL,
                "schema_version": contract_schema_version(
                    "package_integrity_manifest"
                ),
            }
        ),
        encoding="utf-8",
    )
    (root / "SOURCE_PROVENANCE.json").write_text(
        json.dumps(
            {
                "schema_version": contract_schema_version("source_provenance"),
                "runtime_version": PACKAGE_VERSION_FULL,
                "update_version": PACKAGE_VERSION_FULL,
                "version_source": "latka_jazn/version.py",
            }
        ),
        encoding="utf-8",
    )

    assert _generated_metadata_errors(root) == []


def test_current_literal_scan_exempts_release_docs_and_compatibility_labels(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _write_version(root)
    approved = (
        root / "docs" / "README.md",
        root / "docs" / "plans" / "release.md",
        root / "docs" / "project" / "evaluation.md",
        root / "latka_jazn" / "tools" / "memory_rebuild_app" / "__init__.py",
    )
    for path in approved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PACKAGE_VERSION_FULL + "\n", encoding="utf-8")

    unapproved = root / "latka_jazn" / "other.py"
    unapproved.write_text(PACKAGE_VERSION_FULL + "\n", encoding="utf-8")

    violations = scan_forbidden_current_literals(root)
    assert {item["path"] for item in violations} == {"latka_jazn/other.py"}
