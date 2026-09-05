from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from latka_jazn.packaging import memory_package_contract as memory_contract
from latka_jazn.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"
LEGACY_MEMORY_VERSION = "v" + ".".join(("15", "0", "3", "222")) + "-RUN HOTFIX"


def _load_generator():
    name = "jazn_pack_generator_memory_v101860111_contract_test"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_runtime_version(root: Path, full: str = "v15.4.2.1-current") -> None:
    (root / "latka_jazn").mkdir(parents=True, exist_ok=True)
    release = full.split("-", 1)[1] if "-" in full else ""
    (root / "latka_jazn" / "version.py").write_text(
        "DISTRIBUTION_VERSION = '15.4.2.1'\n"
        "PACKAGE_VERSION = 'v15.4.2.1'\n"
        f"PACKAGE_RELEASE_NAME = {release!r}\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_file(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha(path),
        "classification": "memory_file",
    }


def test_generator_v101860111_archives_memory_without_distribution_job(tmp_path: Path) -> None:
    generator = _load_generator()
    assert generator.GENERATOR_VERSION == "10.1.86.0.111"
    assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v1"
    assert generator.CONTENT_CHOICES == ("system", "memory", "system+memory")
    assert "dependency-bundle" in generator.config_report()["not_in_scope"]

    root = tmp_path / "runtime"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        'PACKAGE_VERSION = "16.3.25.5.23"\n'
        'PACKAGE_RELEASE_NAME = "package-generator-v10.1.86.0.111-clean-rewrite"\n',
        encoding="utf-8",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    memory = tmp_path / "memory-source"
    memory.mkdir()
    (memory / "data.jsonl").write_text('{"memory":true}\n', encoding="utf-8")
    plan = generator.plan_pack(
        generator.PackRequest(
            source_root=root,
            output_root=tmp_path / "packages",
            content=generator.ContentMode.MEMORY,
            memory_root=memory,
        )
    )
    assert {entry.archive_path for entry in plan.entries} == {"memory/data.jsonl"}


def test_legacy_v1_runtime_mismatch_is_advisory_for_standalone_and_strict_for_combined(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _write_runtime_version(runtime, "v15.4.2.1-current")
    package = tmp_path / "package"
    memory = package / "memory"
    memory.mkdir(parents=True)
    data = memory / "legacy.jsonl"
    data.write_text('{"legacy":true}\n', encoding="utf-8")
    payload = {
        "schema_version": "jazn_memory_package_manifest/v1",
        "runtime_version": LEGACY_MEMORY_VERSION,
        "generated_at_utc": "2026-07-21T00:00:00+00:00",
        "file_count": 1,
        "files": [_manifest_file(data, package)],
    }
    (memory / "MEMORY_PACKAGE_MANIFEST.json").write_text(json.dumps(payload), encoding="utf-8")

    standalone = memory_contract.verify_memory_package_manifest(package, runtime_root=runtime, require_runtime_match=False)
    strict = memory_contract.verify_memory_package_manifest(package, runtime_root=runtime, require_runtime_match=True)
    assert standalone["ok"] is True
    assert standalone["runtime_version_match"] is False
    assert {row["code"] for row in standalone["warnings"]} == {"legacy_memory_created_with_different_runtime"}
    assert strict["ok"] is False
    assert "memory_package_runtime_version_mismatch" in {row["code"] for row in strict["errors"]}


def test_v2_created_with_older_runtime_is_provenance_not_rejection(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _write_runtime_version(runtime, "v15.4.2.1-current")
    package = tmp_path / "package"
    memory = package / "memory"
    memory.mkdir(parents=True)
    data = memory / "structured.jsonl"
    data.write_text('{"message":"hello"}\n', encoding="utf-8")
    payload = {
        "schema_version": "jazn_memory_package_manifest/v2",
        "memory_format_version": 2,
        "snapshot_id": "bda222ef-95c9-44fc-8fe2-63f0c4294d2a",
        "created_at_utc": "2026-08-14T00:00:00+00:00",
        "created_with_runtime": LEGACY_MEMORY_VERSION,
        "compatibility": {
            "contract": "jazn_memory_runtime/v1",
            "runtime_version_is_provenance_only": True,
            "legacy_structural_recovery_allowed": True,
        },
        "file_count": 1,
        "files": [_manifest_file(data, package)],
        "databases": [],
    }
    (memory / "MEMORY_PACKAGE_MANIFEST.json").write_text(json.dumps(payload), encoding="utf-8")
    report = memory_contract.verify_memory_package_manifest(package, runtime_root=runtime)
    assert report["ok"] is True
    assert report["runtime_version_match"] is False
    assert report["runtime_version_is_provenance_only"] is True
    assert "memory_created_with_different_runtime" in {row["code"] for row in report["warnings"]}


def test_memory_package_selection_ignores_system_sidecar_when_both_are_present(tmp_path: Path) -> None:
    parts = tmp_path / "parts"
    parts.mkdir()
    for name, profile in (("system.zip", "system"), ("memory.zip", "memory")):
        archive = parts / name
        archive.write_bytes(b"dummy")
        (parts / f"{name}.package.json").write_text(
            json.dumps(
                {
                    "schema_version": "jazn_package_set/v2",
                    "package_name": name,
                    "profile": profile,
                    "archive_format": "independent",
                    "package_version": "v1",
                    "outputs": [{"part_no": 1, "filename": name, "size_bytes": 5, "sha256": _sha(archive)}],
                }
            ),
            encoding="utf-8",
        )
    assert memory_contract._infer_memory_base_zip_name(parts) == "memory.zip"


def test_cli_exposes_exact_memory_attach_command_and_rejects_abbreviation() -> None:
    parser = build_parser()
    ns = parser.parse_args(["memory-attach", "--parts-dir", "."])
    assert ns.command == "memory-attach"
    with pytest.raises(SystemExit):
        parser.parse_args(["memory-att", "--parts-dir", "."])


def test_v2_rejects_sqlite_omitted_from_database_metadata(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _write_runtime_version(runtime)
    package = tmp_path / "package"
    db = package / "memory" / "sqlite" / "legacy.sqlite3"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE item(id INTEGER PRIMARY KEY)")
    payload = {
        "schema_version": "jazn_memory_package_manifest/v2",
        "memory_format_version": 2,
        "snapshot_id": "bda222ef-95c9-44fc-8fe2-63f0c4294d2a",
        "created_at_utc": "2026-08-14T00:00:00+00:00",
        "created_with_runtime": "v15.4.2.1-current",
        "compatibility": {"contract": "jazn_memory_runtime/v1", "runtime_version_is_provenance_only": True},
        "file_count": 1,
        "files": [_manifest_file(db, package)],
        "databases": [],
    }
    (package / "memory" / "MEMORY_PACKAGE_MANIFEST.json").write_text(json.dumps(payload), encoding="utf-8")
    report = memory_contract.verify_memory_package_manifest(package, runtime_root=runtime)
    assert report["ok"] is False
    assert "memory_database_metadata_missing" in {row["code"] for row in report["errors"]}


def test_v2_rejects_unzoned_snapshot_timestamp(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _write_runtime_version(runtime)
    package = tmp_path / "package"
    memory = package / "memory"
    memory.mkdir(parents=True)
    data = memory / "data.json"
    data.write_text("{}", encoding="utf-8")
    payload = {
        "schema_version": "jazn_memory_package_manifest/v2",
        "memory_format_version": 2,
        "snapshot_id": "bda222ef-95c9-44fc-8fe2-63f0c4294d2a",
        "created_at_utc": "2026-08-14T00:00:00",
        "created_with_runtime": "v15.4.2.1-current",
        "compatibility": {"contract": "jazn_memory_runtime/v1", "runtime_version_is_provenance_only": True},
        "file_count": 1,
        "files": [_manifest_file(data, package)],
        "databases": [],
    }
    (memory / "MEMORY_PACKAGE_MANIFEST.json").write_text(json.dumps(payload), encoding="utf-8")
    report = memory_contract.verify_memory_package_manifest(package, runtime_root=runtime)
    assert report["ok"] is False
    assert "memory_snapshot_timestamp_invalid" in {row["code"] for row in report["errors"]}


def test_memory_attach_fail_closed_keeps_exception_details(tmp_path: Path) -> None:
    result = memory_contract.attach_memory_package(tmp_path / "missing", parts_dir=tmp_path / "parts")
    assert result.ok is False
    assert result.state in {"runtime_not_verified", "memory_attach_blocked"}
    if result.state == "memory_attach_blocked":
        assert result.report["error"]["type"]
