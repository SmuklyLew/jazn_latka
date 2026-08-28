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
    name = "jazn_pack_generator_memory_v2_contract_test"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _version(generator, full: str = "v15.4.2.1-current"):
    return generator.VersionInfo(
        version_file=Path("latka_jazn/version.py"),
        package_version="v15.4.2.1",
        release_name="current",
        full_version=full,
        filename_version="15.4.2.1-current",
    )


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


def test_generator_keeps_v86_public_identity_and_uses_v3_memory_contract() -> None:
    generator = _load_generator()
    assert generator.GENERATOR_VERSION == "8.6"
    assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.6"
    assert generator.MEMORY_MANIFEST_SCHEMA == "jazn_memory_package_manifest/v3"
    assert generator.MEMORY_FORMAT_VERSION == 3


def test_memory_plan_snapshots_live_wal_sqlite_and_records_current_identity(tmp_path: Path) -> None:
    generator = _load_generator()
    root = tmp_path / "runtime"
    db = root / "memory" / "sqlite" / "runtime_write_v2" / "runtime_memory.sqlite3"
    db.parent.mkdir(parents=True)
    source = sqlite3.connect(db)
    source.execute("PRAGMA journal_mode=WAL")
    source.execute("PRAGMA user_version=7")
    source.execute("PRAGMA application_id=424242")
    source.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    source.execute(
        "CREATE TABLE jazn_database_identity("
        "singleton INTEGER PRIMARY KEY, database_uuid TEXT, schema_identity TEXT, "
        "schema_version_number INTEGER, created_by_runtime TEXT, created_at_utc TEXT, trust_state TEXT)"
    )
    source.execute(
        "INSERT INTO jazn_database_identity VALUES(1,?,?,?,?,?,?)",
        ("db-uuid", "runtime_memory_v2", 7, "v15.4.2.1-current", "2026-08-14T00:00:00+00:00", "verified"),
    )
    source.execute("INSERT INTO items(value) VALUES('committed-in-wal')")
    source.commit()
    assert (Path(str(db) + "-wal")).exists()

    plan = generator.build_memory_plan(
        root,
        _version(generator),
        [db.relative_to(root).as_posix()],
        [],
        "test",
    )
    try:
        manifest_entry = next(item for item in plan.entries if item.relative == generator.MEMORY_PACKAGE_MANIFEST)
        assert manifest_entry.virtual_bytes is not None
        payload = json.loads(manifest_entry.virtual_bytes)
        assert payload["schema_version"] == "jazn_memory_package_manifest/v3"
        assert payload["memory_format_version"] == 3
        assert payload["created_with_runtime"] == "v15.4.2.1-current"
        assert payload["compatibility"]["runtime_version_is_provenance_only"] is True
        database = payload["databases"][0]
        assert database["snapshot_method"] in {"sqlite_backup_api", "sqlite_online_backup_api"}
        assert database["user_version"] == 7
        assert database["application_id"] == 424242
        snapshot_entry = next(item for item in plan.entries if item.relative == db.relative_to(root).as_posix())
        assert snapshot_entry.source is not None and snapshot_entry.source != db
        with sqlite3.connect(snapshot_entry.source) as snap:
            assert snap.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert snap.execute("SELECT value FROM items").fetchone()[0] == "committed-in-wal"
    finally:
        plan.cleanup()
        source.close()


def test_memory_sidecar_has_independent_version_axis(tmp_path: Path) -> None:
    generator = _load_generator()
    plan = generator.PackPlan(
        root=tmp_path,
        profile="memory",
        version=_version(generator, "v15.4.2.1-current"),
        entries=[],
        manifest_builder="memory_manifest_v2+sqlite_backup_api",
    )
    payload = generator.sidecar_payload(
        "memory.zip",
        plan,
        "independent",
        1024,
        6,
        [],
        None,
        {"ok": True},
    )
    assert payload["package_version"] == "memory-format-v3"
    assert payload["created_with_runtime"] == "v15.4.2.1-current"
    assert payload["runtime_version_is_provenance_only"] is True
    assert payload["memory_compatibility_contract"] == "jazn_memory_runtime/v1"


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
