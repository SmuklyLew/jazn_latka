from __future__ import annotations

import io
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from latka_jazn.packaging import memory_package_types as memory_types
from latka_jazn.packaging import memory_streaming_transport as streaming
from latka_jazn.packaging.memory_package_manifest import verify_memory_package_manifest
from tools.jazn_pack_generator_app import staging as staging_module
from tools.jazn_pack_generator_app.manifest import build_manifest
from tools.jazn_pack_generator_app.models import ContentMode, PackRequest
from tools.jazn_pack_generator_app.scanner import build_pack_plan


def _write_version(root: Path) -> None:
    package = root / "latka_jazn"
    package.mkdir(parents=True, exist_ok=True)
    (package / "version.py").write_text(
        'DISTRIBUTION_VERSION = "16.3.25.5.106"\n'
        'PACKAGE_VERSION = "16.3.25.5.106"\n'
        'PACKAGE_RELEASE_NAME = "memory-streaming-hardening-convergence"\n',
        encoding="utf-8",
    )


def _memory_request(root: Path, memory: Path, out: Path) -> PackRequest:
    return PackRequest(
        source_root=root,
        output_root=out,
        content=ContentMode.MEMORY,
        memory_root=memory,
    )


def test_memory_zip_resource_policy_rejects_high_compression_ratio() -> None:
    payload = b"0" * (2 * 1024 * 1024)
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        archive.writestr("memory/raw/bomb.bin", payload)

    buffer.seek(0)
    with zipfile.ZipFile(buffer, "r") as archive:
        with pytest.raises(
            streaming.MemoryStreamingTransportError,
            match="archive_compression_ratio_limit_exceeded",
        ):
            streaming._validate_archive_resources([archive])


def test_write_json_atomic_fsyncs_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fsync_calls: list[int] = []
    monkeypatch.setattr(memory_types.os, "fsync", lambda fd: fsync_calls.append(int(fd)))

    target = tmp_path / "state.json"
    memory_types.write_json_atomic(target, {"ok": True, "generation": 106})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "generation": 106,
        "ok": True,
    }
    assert fsync_calls
    assert not list(tmp_path.glob("state.json.tmp-*"))


def test_native_memory_v3_staging_uses_online_backup_for_live_wal_sqlite(
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime"
    memory = root / "memory"
    memory.mkdir(parents=True)
    _write_version(root)

    database = memory / "live.sqlite3"
    writer = sqlite3.connect(database)
    try:
        assert str(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower() == "wal"
        writer.execute("PRAGMA foreign_keys=ON")
        writer.execute(
            "CREATE TABLE parent(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        writer.execute("INSERT INTO parent(value) VALUES ('one')")
        writer.commit()
        writer.execute("INSERT INTO parent(value) VALUES ('two')")
        writer.commit()

        (memory / "note.txt").write_text("memory", encoding="utf-8")

        plan = build_pack_plan(
            _memory_request(root, memory, tmp_path / "out")
        )
        assert all(
            not item.archive_path.casefold().endswith(("-wal", "-shm"))
            for item in plan.entries
        )

        staging_root = tmp_path / "staging"
        staged = staging_module.materialize_source_staging(plan, staging_root)
        manifest_path = staging_root / "memory" / "MEMORY_PACKAGE_MANIFEST.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert staged.verification_metadata()["memory_native_v3"] is True
        assert staged.verification_metadata()["byte_exact_source_copy"] is False
        assert payload["schema_version"] == "jazn_memory_package_manifest/v3"
        assert payload["memory_format_version"] == 3
        assert len(payload["databases"]) == 1
        database_row = payload["databases"][0]
        assert database_row["path"] == "memory/live.sqlite3"
        assert database_row["snapshot_method"] == "sqlite_online_backup_api"

        staged_db = staging_root / "memory" / "live.sqlite3"
        with sqlite3.connect(staged_db) as check:
            rows = check.execute("SELECT value FROM parent ORDER BY id").fetchall()
        assert rows == [("one",), ("two",)]
        assert not (staging_root / "memory" / "live.sqlite3-wal").exists()
        assert not (staging_root / "memory" / "live.sqlite3-shm").exists()

        verification = verify_memory_package_manifest(
            staging_root,
            runtime_root=root,
            require_runtime_match=False,
        )
        assert verification["ok"] is True, verification

        sidecar = build_manifest(
            staged.plan,
            logical_filename="memory.zip",
            logical_sha256="a" * 64,
            logical_size_bytes=123,
            split_enabled=False,
            parts=[],
            verification=staged.verification_metadata(),
            source_sha256=staged.member_sha256,
        )
        assert sidecar["memory_manifest_schema"] == "jazn_memory_package_manifest/v3"
        assert sidecar["memory_format_version"] == 3
        assert sidecar["memory_transport_contract"] == "jazn_memory_package_transport/v1"
        assert sidecar["source"]["byte_exact"] is False
        assert sidecar["source"]["source_basis"] == "memory_native_v3"
    finally:
        writer.close()


def test_native_memory_v3_staging_segments_large_jsonl_without_source_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    memory = root / "memory"
    raw_dir = memory / "raw"
    raw_dir.mkdir(parents=True)
    _write_version(root)

    monkeypatch.setattr(
        staging_module,
        "_MEMORY_RAW_SEGMENT_TARGET_BYTES",
        1 * 1024 * 1024,
    )
    monkeypatch.setattr(
        staging_module,
        "_MEMORY_RAW_SEGMENT_MAX_BYTES",
        2 * 1024 * 1024,
    )

    raw = raw_dir / "events.jsonl"
    line = ('{"payload":"' + ("x" * 180) + '"}\n').encode("utf-8")
    with raw.open("wb") as handle:
        for _ in range(14_000):
            handle.write(line)
    assert raw.stat().st_size > 2 * 1024 * 1024

    plan = build_pack_plan(
        _memory_request(root, memory, tmp_path / "out")
    )
    staging_root = tmp_path / "staging"
    staged = staging_module.materialize_source_staging(plan, staging_root)
    payload = json.loads(
        (staging_root / "memory" / "MEMORY_PACKAGE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )

    assert len(payload["raw_segments"]) == 1
    descriptor = payload["raw_segments"][0]
    assert descriptor["source_path"] == "memory/raw/events.jsonl"
    assert len(descriptor["segments"]) >= 2
    assert not (staging_root / "memory" / "raw" / "events.jsonl").exists()

    packaged_paths = {
        item["path"]: item for item in payload["files"]
    }
    for segment in descriptor["segments"]:
        segment_path = str(segment["package_path"])
        assert packaged_paths[segment_path]["classification"] == "memory_raw_segment"
        assert (staging_root / Path(*segment_path.split("/"))).is_file()

    verification = verify_memory_package_manifest(
        staging_root,
        runtime_root=root,
        require_runtime_match=False,
    )
    assert verification["ok"] is True, verification
    assert staged.verification_metadata()["memory_native_v3"] is True
