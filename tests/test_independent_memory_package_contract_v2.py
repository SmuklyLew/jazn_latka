from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import uuid

import pytest

from latka_jazn.packaging import memory_package_contract as contract
from latka_jazn.cli import build_parser
from tools import jazn_pack_generator as generator


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_sqlite(path: Path, *, row: str = "alpha") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=7")
        connection.execute("PRAGMA application_id=1245791563")
        connection.execute("CREATE TABLE memory_records(id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        connection.execute("INSERT INTO memory_records(body) VALUES (?)", (row,))
        connection.commit()


def _write_v2_manifest(root: Path, *, created_with_runtime: str = "v15.1.0.3-old") -> Path:
    relative = "memory/sqlite/runtime_write_v1/runtime_memory.sqlite3"
    database = root / relative
    _create_sqlite(database)
    report = contract.inspect_sqlite_memory_file(database)
    payload = {
        "schema_version": contract.MEMORY_MANIFEST_SCHEMA_V2,
        "memory_format_version": contract.MEMORY_FORMAT_VERSION,
        "snapshot_id": str(uuid.uuid4()),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "created_with_runtime": created_with_runtime,
        "compatibility": {
            "contract": contract.MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
            "runtime_version_is_provenance_only": True,
            "memory_format_version": contract.MEMORY_FORMAT_VERSION,
            "manifest_schema": contract.MEMORY_MANIFEST_SCHEMA_V2,
        },
        "file_count": 1,
        "files": [
            {
                "path": relative,
                "size_bytes": report["size_bytes"],
                "sha256": report["sha256"],
                "classification": "memory_sqlite_snapshot",
            }
        ],
        "databases": [
            {
                "path": relative,
                "role": "runtime_memory",
                "snapshot_method": "sqlite_online_backup_api",
                "user_version": report["user_version"],
                "application_id": report["application_id"],
                "schema_sha256": report["schema_sha256"],
                "table_count": report["table_count"],
                "integrity_check": "ok",
                "foreign_key_error_count": 0,
                "size_bytes": report["size_bytes"],
                "sha256": report["sha256"],
            }
        ],
    }
    manifest = root / contract.MEMORY_PACKAGE_MANIFEST_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest


def test_v2_created_with_different_runtime_is_provenance_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_v2_manifest(tmp_path, created_with_runtime="v15.1.0.3-old")
    monkeypatch.setattr(contract, "read_runtime_version_from_version_py", lambda _root: "v15.4.2.1-current")

    report = contract.verify_memory_package_manifest(tmp_path, runtime_root=tmp_path)

    assert report["ok"] is True
    assert report["runtime_version_match"] is False
    assert {item["code"] for item in report["warnings"]} == {"memory_created_with_different_runtime"}
    assert not any(item["code"] == "memory_package_runtime_version_mismatch" for item in report["errors"])


def test_legacy_v1_runtime_mismatch_is_advisory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    memory_file = tmp_path / "memory" / "raw" / "history.txt"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("history", encoding="utf-8")
    manifest = tmp_path / contract.MEMORY_PACKAGE_MANIFEST_PATH
    manifest.write_text(
        json.dumps(
            {
                "schema_version": contract.MEMORY_MANIFEST_SCHEMA_V1,
                "runtime_version": "v15.1.0.3-old",
                "file_count": 1,
                "files": [
                    {
                        "path": "memory/raw/history.txt",
                        "size_bytes": memory_file.stat().st_size,
                        "sha256": _sha256(memory_file),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(contract, "read_runtime_version_from_version_py", lambda _root: "v15.4.2.1-current")

    report = contract.verify_memory_package_manifest(tmp_path, runtime_root=tmp_path)

    assert report["ok"] is True
    assert "legacy_memory_created_with_different_runtime" in {item["code"] for item in report["warnings"]}


def test_v2_rejects_unsupported_contract_and_sqlite_metadata_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _write_v2_manifest(tmp_path)
    monkeypatch.setattr(contract, "read_runtime_version_from_version_py", lambda _root: "v15.4.2.1-current")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["compatibility"]["contract"] = "jazn_memory_runtime/v999"
    payload["databases"][0]["user_version"] = 999
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    report = contract.verify_memory_package_manifest(tmp_path, runtime_root=tmp_path)
    codes = {item["code"] for item in report["errors"]}

    assert report["ok"] is False
    assert "memory_compatibility_contract_unsupported" in codes
    assert "memory_database_metadata_mismatch" in codes


def test_generator_v2_snapshots_live_wal_and_excludes_memory_backups(tmp_path: Path) -> None:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").write_text(
        'DISTRIBUTION_VERSION = "99"\nPACKAGE_VERSION = "v99"\nPACKAGE_RELEASE_NAME = "memory-test"\n',
        encoding="utf-8",
    )
    database = tmp_path / "memory" / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3"
    database.parent.mkdir(parents=True)
    source = sqlite3.connect(database)
    try:
        source.execute("PRAGMA journal_mode=WAL")
        source.execute("CREATE TABLE records(id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        source.execute("INSERT INTO records(body) VALUES ('before snapshot')")
        source.commit()
        backup = tmp_path / "memory" / "backups" / "old.sqlite3"
        _create_sqlite(backup, row="must not be packaged")

        plan = generator.build_plan(tmp_path, "memory", [])
        try:
            manifest_entry = next(item for item in plan.entries if item.relative == generator.MEMORY_PACKAGE_MANIFEST)
            payload = json.loads((manifest_entry.virtual_bytes or b"").decode("utf-8"))
            db_entry = next(item for item in plan.entries if item.relative.endswith("runtime_memory.sqlite3"))
            assert payload["schema_version"] == generator.MEMORY_MANIFEST_SCHEMA
            assert payload["memory_format_version"] == generator.MEMORY_FORMAT_VERSION
            assert "runtime_version" not in payload
            assert payload["created_with_runtime"] == "v99-memory-test"
            assert payload["compatibility"]["runtime_version_is_provenance_only"] is True
            assert db_entry.classification == "memory_sqlite_snapshot"
            assert "memory/backups/old.sqlite3" not in plan.paths

            source.execute("INSERT INTO records(body) VALUES ('after snapshot')")
            source.commit()
            assert db_entry.source is not None
            with sqlite3.connect(db_entry.source) as snapshot:
                rows = snapshot.execute("SELECT body FROM records ORDER BY id").fetchall()
            assert rows == [("before snapshot",)]
        finally:
            plan.cleanup()
    finally:
        source.close()


def test_combined_memory_manifest_remains_runtime_bootstrap_compatible(tmp_path: Path) -> None:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").write_text(
        'PACKAGE_VERSION = "v99"\nPACKAGE_RELEASE_NAME = "combined-test"\n', encoding="utf-8"
    )
    database = tmp_path / "memory" / "db.sqlite3"
    _create_sqlite(database)
    version = generator.read_version_info(tmp_path)
    plan = generator.build_memory_plan(
        tmp_path,
        version,
        ["memory/db.sqlite3"],
        [],
        "test",
        independent_contract=False,
    )
    try:
        manifest_entry = next(item for item in plan.entries if item.relative == generator.MEMORY_PACKAGE_MANIFEST)
        payload = json.loads((manifest_entry.virtual_bytes or b"").decode("utf-8"))
        assert payload["schema_version"] == "jazn_memory_package_manifest/v1"
        assert payload["runtime_version"] == version.full_version
        assert plan.manifest_builder.startswith("combined_memory_manifest_v1_compat")
    finally:
        plan.cleanup()


def test_memory_attach_is_canonical_cli_command() -> None:
    parsed = build_parser().parse_args(
        [
            "memory-attach",
            "--root",
            "active-v154",
            "--parts-dir",
            "memory-parts",
            "--zip-name",
            "memory.zip",
            "--no-crc",
        ]
    )
    assert parsed.command == "memory-attach"
    assert parsed.root == Path("active-v154")
    assert parsed.parts_dir == Path("memory-parts")
    assert parsed.zip_name == "memory.zip"
    assert parsed.no_crc is True


def test_memory_attach_blocks_live_daemon_before_touching_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(contract, "_runtime_installation_status", lambda _root: {"ok": True, "version": "v15.4.2.1"})
    monkeypatch.setattr(contract, "JaznConfig", lambda root: SimpleNamespace(root=Path(root)))
    monkeypatch.setattr(contract, "status_daemon", lambda _config: {"active_state": "active_trusted"})
    monkeypatch.setattr(contract, "infer_base_zip_name", lambda *_a, **_k: pytest.fail("package must not be inspected while daemon is active"))

    result = contract.attach_memory_package(tmp_path / "runtime", parts_dir=tmp_path / "parts")

    assert result.ok is False
    assert result.state == "runtime_active_attach_blocked"
    assert result.exit_code == 12


def test_memory_attach_transaction_replaces_memory_only_after_full_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    old_memory = runtime_root / "memory"
    old_memory.mkdir(parents=True)
    (old_memory / "old.txt").write_text("old", encoding="utf-8")
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()

    monkeypatch.setattr(contract, "_runtime_installation_status", lambda _root: {"ok": True, "version": "v15.4.2.1-current"})
    monkeypatch.setattr(contract, "JaznConfig", lambda root: SimpleNamespace(root=Path(root)))
    monkeypatch.setattr(contract, "status_daemon", lambda _config: {"active_state": "inactive"})
    monkeypatch.setattr(contract, "read_runtime_version_from_version_py", lambda _root: "v15.4.2.1-current")
    monkeypatch.setattr(contract, "infer_base_zip_name", lambda *_a, **_k: "memory.zip")
    monkeypatch.setattr(
        contract,
        "load_package_set_metadata",
        lambda *_a, **_k: {"source": "package.json", "profile": "memory", "archive_format": "independent"},
    )
    expected = [SimpleNamespace(filename="memory.zip", part_no=1, size_bytes=None, sha256=None)]
    monkeypatch.setattr(contract, "load_package_expectations", lambda *_a, **_k: (expected, None, "package.json"))

    def resolve(_parts, _expected, *, canonical_dir, skip_part_hash=False):
        canonical_dir.mkdir(parents=True, exist_ok=True)
        (canonical_dir / "memory.zip").write_bytes(b"placeholder")
        return {"ok": True, "parts_count": 1}

    monkeypatch.setattr(contract, "resolve_renamed_package_parts", resolve)
    monkeypatch.setattr(contract, "test_joined_zip", lambda *_a, **_k: {"ok": True})

    def extract(_archives, staging, **_kwargs):
        staging.mkdir(parents=True, exist_ok=True)
        _write_v2_manifest(staging, created_with_runtime="v15.1.0.3-old")
        return {"ok": True, "pending": False}

    monkeypatch.setattr(contract, "extract_independent_zip_set_resumable", extract)
    monkeypatch.setattr(contract, "verify_extracted_zip_set", lambda *_a, **_k: {"ok": True})

    result = contract.attach_memory_package(
        runtime_root,
        parts_dir=parts_dir,
        work_dir=runtime_root / "workspace_runtime" / "memory_attach" / "test-work",
        time_budget_seconds=None,
    )

    assert result.ok is True
    assert result.state == "memory_attached_inactive"
    assert not (runtime_root / "memory" / "old.txt").exists()
    assert (runtime_root / contract.MEMORY_PACKAGE_MANIFEST_PATH).is_file()
    assert (runtime_root / contract.ATTACH_MARKER_PATH).is_file()
    assert result.report["post_install_verification"]["ok"] is True
    assert result.report["post_install_verification"]["runtime_version_match"] is False
