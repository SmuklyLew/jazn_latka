from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import stat
import subprocess

from latka_jazn.core.source_provenance import read_source_provenance
from latka_jazn.tools.package_integrity import (
    build_package_integrity_manifest,
    verify_package_integrity_manifest,
    write_package_integrity_manifest,
)
from latka_jazn.tools.release_metadata_sync import (
    build_canonical_package_manifest,
    build_release_provenance_document,
)
from latka_jazn.tools.source_provenance import build_source_provenance_document
from latka_jazn.version import (
    DISTRIBUTION_VERSION,
    PACKAGE_RELEASE_NAME,
    PACKAGE_VERSION,
    PACKAGE_VERSION_FULL,
    contract_schema_version,
    release_version_marker,
    runtime_version_marker,
    schema_contract_metadata,
    schema_version,
    schema_version_compatibility,
)


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _remove_readonly_then_retry(func, path, _excinfo) -> None:
    """Clear a Windows read-only bit once, then let a real retry failure surface."""

    os.chmod(path, stat.S_IWRITE)
    func(path)


def _remove_git_metadata(root: Path) -> None:
    shutil.rmtree(root / ".git", onexc=_remove_readonly_then_retry)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "__init__.py").write_text("", encoding="utf-8")
    (root / "latka_jazn" / "version.py").write_text(
        f"DISTRIBUTION_VERSION = {DISTRIBUTION_VERSION!r}\n"
        f"PACKAGE_VERSION = {PACKAGE_VERSION!r}\n"
        f"PACKAGE_RELEASE_NAME = {PACKAGE_RELEASE_NAME!r}\n",
        encoding="utf-8",
    )
    (root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (root / "main.py").write_text("print('main')\n", encoding="utf-8")
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "branch", "-M", "master")
    _git(root, "remote", "add", "origin", "https://github.com/SmuklyLew/jazn_latka.git")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    return root


def _remove_git_metadata(root: Path) -> None:
    def _clear_readonly_and_retry(function, path, _excinfo) -> None:
        os.chmod(path, stat.S_IWRITE)
        function(path)

    shutil.rmtree(root / ".git", onexc=_clear_readonly_and_retry)


def test_contract_schema_versions_are_independent_from_release_identity() -> None:
    assert contract_schema_version("startup_contract") == "startup_contract/v1"
    assert contract_schema_version("source_provenance") == "source_provenance/v2"
    assert contract_schema_version("package_integrity_manifest") == "package_integrity_manifest/v2"
    assert PACKAGE_VERSION not in contract_schema_version("startup_contract")
    assert runtime_version_marker("startup_contract") == f"startup_contract/{PACKAGE_VERSION}"
    assert release_version_marker("startup_contract") == f"startup_contract/{PACKAGE_VERSION_FULL}"
    assert schema_version("startup_contract") == "startup_contract/v1"
    assert schema_version("startup_contract", version=PACKAGE_VERSION) == f"startup_contract/{PACKAGE_VERSION}"


def test_legacy_runtime_coupled_schema_has_explicit_migration_path() -> None:
    current = schema_version_compatibility("source_provenance", "source_provenance/v2")
    assert current["compatible"] is True
    assert current["migration_required"] is False

    legacy = schema_version_compatibility(
        "source_provenance",
        f"source_provenance/{PACKAGE_VERSION}",
    )
    assert legacy["compatible"] is True
    assert legacy["migration_required"] is True
    assert legacy["kind"] == "legacy_runtime_coupled_schema"
    assert legacy["current_schema_version"] == "source_provenance/v2"

    unsupported = schema_version_compatibility("source_provenance", "other_contract/v1")
    assert unsupported["compatible"] is False

    metadata = schema_contract_metadata("package_integrity_manifest")
    assert metadata["current_schema_version"] == "package_integrity_manifest/v2"
    assert metadata["legacy_runtime_coupled_schema"]["migration_target"] == "package_integrity_manifest/v2"


def test_provenance_reader_accepts_legacy_schema_as_migration_and_rejects_foreign_schema(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    payload = build_source_provenance_document(root)
    payload["schema_version"] = f"source_provenance/{PACKAGE_VERSION}"
    (root / "SOURCE_PROVENANCE.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_package_integrity_manifest(root)
    _remove_git_metadata(root)

    legacy = read_source_provenance(root, profile="system_smoke")
    assert legacy.status == "verified_export_without_git_history"
    assert legacy.schema_compatible is True
    assert legacy.schema_migration_required is True
    assert legacy.schema_compatibility_kind == "legacy_runtime_coupled_schema"

    provenance_path = root / "SOURCE_PROVENANCE.json"
    foreign_payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    foreign_payload["schema_version"] = "foreign_provenance/v1"
    provenance_path.write_text(
        json.dumps(foreign_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_package_integrity_manifest(root)

    foreign = read_source_provenance(root, profile="system_smoke")
    assert foreign.status == "invalid"
    assert foreign.schema_compatible is False
    assert foreign.schema_migration_required is False
    assert foreign.schema_compatibility_kind == "unsupported_schema"
    assert any("unsupported source provenance schema" in item for item in foreign.limitations)


def test_manifest_verifier_accepts_legacy_schema_as_migration_and_rejects_foreign_schema(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    build_source_provenance_document(root, write=True)
    manifest = write_package_integrity_manifest(root)
    manifest_path = root / "PACKAGE_INTEGRITY_MANIFEST.json"

    manifest["schema_version"] = f"package_integrity_manifest/{PACKAGE_VERSION}"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    legacy = verify_package_integrity_manifest(root)
    assert legacy["ok"] is True
    assert legacy["manifest_schema_compatibility"]["compatible"] is True
    assert legacy["manifest_schema_compatibility"]["migration_required"] is True
    assert legacy["manifest_schema_compatibility"]["kind"] == "legacy_runtime_coupled_schema"

    manifest["schema_version"] = "foreign_package_manifest/v1"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    foreign = verify_package_integrity_manifest(root)
    assert foreign["ok"] is False
    assert foreign["manifest_schema_compatibility"]["compatible"] is False
    assert "unsupported_manifest_schema" in {item["code"] for item in foreign["errors"]}


def test_checkout_provenance_separates_schema_release_source_and_legacy_aliases(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    payload = build_source_provenance_document(root)
    head = _git(root, "rev-parse", "HEAD")

    assert payload["schema_version"] == "source_provenance/v2"
    assert payload["schema_contract"]["current_schema_version"] == "source_provenance/v2"
    assert payload["runtime_version"] == PACKAGE_VERSION_FULL
    assert payload["release_version"] == PACKAGE_VERSION_FULL
    assert payload["source_version"] == PACKAGE_VERSION_FULL
    assert payload["source_commit"] == head
    assert payload["base_merge_commit"] == payload["source_commit"]
    assert payload["base_version"] == payload["source_version"]
    assert payload["update_version"] == payload["release_version"]
    assert payload["legacy_aliases"]["base_merge_commit"] == "source_commit"


def test_release_metadata_adds_real_lineage_without_repurposing_legacy_fields(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    head = _git(root, "rev-parse", "HEAD")

    provenance = build_release_provenance_document(root, base_branch="master")
    assert provenance["schema_version"] == "source_provenance/v2"
    assert provenance["source_commit"] == head
    assert provenance["source_version"] == PACKAGE_VERSION_FULL
    assert provenance["release_version"] == PACKAGE_VERSION_FULL
    assert provenance["lineage"]["base_branch"] == "master"
    assert provenance["lineage"]["base_commit"] == head
    assert provenance["lineage"]["base_version"] == PACKAGE_VERSION_FULL
    assert provenance["lineage"]["relationship"] == "merge_base_to_immutable_source_commit"
    assert provenance["base_merge_commit"] == provenance["source_commit"]
    assert provenance["base_version"] == provenance["source_version"]
    assert provenance["update_version"] == provenance["release_version"]

    provenance_bytes = (
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest = build_canonical_package_manifest(
        root,
        source_commit=head,
        overrides={"SOURCE_PROVENANCE.json": provenance_bytes},
        generated_at_utc=provenance["generated_at_utc"],
    )
    assert manifest["schema_version"] == "package_integrity_manifest/v2"
    assert manifest["schema_contract"]["current_schema_version"] == "package_integrity_manifest/v2"
    assert manifest["release_version"] == PACKAGE_VERSION_FULL
    assert manifest["artifact_identity"]["runtime_version"] == PACKAGE_VERSION_FULL
    assert manifest["artifact_identity"]["package_version"] == PACKAGE_VERSION_FULL
    assert manifest["legacy_aliases"]["version"] == "release_version"


def test_generic_manifest_builder_uses_stable_contract_schema(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    provenance = build_source_provenance_document(root, write=True)
    assert provenance["schema_version"] == "source_provenance/v2"

    manifest = build_package_integrity_manifest(root)
    assert manifest["schema_version"] == "package_integrity_manifest/v2"
    assert manifest["schema_contract"]["current_schema_version"] == "package_integrity_manifest/v2"
    assert manifest["runtime_version"] == PACKAGE_VERSION_FULL
    assert manifest["release_version"] == PACKAGE_VERSION_FULL
    assert PACKAGE_VERSION not in manifest["schema_version"]
