from __future__ import annotations

from io import BytesIO
import hashlib
import importlib.util
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

from latka_jazn.cli import build_parser
from latka_jazn.packaging import memory_package_contract as memory_contract
from latka_jazn.packaging.memory_raw_segmentation import RawJsonlSegmenter


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"
LEGACY_MEMORY_VERSION = "v15.0.3.222-RUN HOTFIX"


def _load_generator():
    name = "jazn_pack_generator_v1601_contract_test"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_file(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha(path),
        "classification": "memory_file",
    }


def _write_runtime_version(root: Path) -> None:
    (root / "latka_jazn").mkdir(parents=True, exist_ok=True)
    (root / "latka_jazn" / "version.py").write_text(
        "DISTRIBUTION_VERSION = '16.0.1'\n"
        "PACKAGE_VERSION = 'v16.0.1'\n"
        "PACKAGE_RELEASE_NAME = 'single-canonical-runtime-workspace'\n",
        encoding="utf-8",
    )


def test_generator_memory_mode_is_archive_only_and_cloud_attach_stays_outside_generator(tmp_path: Path) -> None:
    generator = _load_generator()
    assert generator.GENERATOR_VERSION == "10.1.86.0.113"
    assert generator.CONTENT_CHOICES == ("system", "memory", "system+memory")
    assert not hasattr(generator, "sidecar_payload")
    assert "target-platform" in generator.config_report()["not_in_scope"]

    root = tmp_path / "runtime"
    _write_runtime_version(root)
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    memory = tmp_path / "memory-source"
    memory.mkdir()
    (memory / "item.json").write_text("{}", encoding="utf-8")
    plan = generator.plan_pack(
        generator.PackRequest(
            source_root=root,
            output_root=tmp_path / "out",
            content=generator.ContentMode.MEMORY,
            memory_root=memory,
        )
    )
    assert {entry.archive_path for entry in plan.entries} == {"memory/item.json"}


class _FakeR2Client:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = dict(objects)

    def list_objects_v2(self, *, Bucket: str, Prefix: str, **kwargs):
        del Bucket, kwargs
        return {
            "IsTruncated": False,
            "Contents": [
                {"Key": key, "Size": len(value)}
                for key, value in sorted(self.objects.items())
                if key.startswith(Prefix)
            ],
        }

    def get_object(self, *, Bucket: str, Key: str):
        del Bucket
        value = self.objects[Key]
        return {"Body": BytesIO(value), "ContentLength": len(value)}


def _r2_package_objects(*, prefix: str, profile: str = "memory", tamper_sha: bool = False) -> dict[str, bytes]:
    archive_name = "jazn_memory.zip"
    archive = b"memory-package-part"
    digest = "0" * 64 if tamper_sha else hashlib.sha256(archive).hexdigest()
    sidecar = json.dumps(
        {
            "schema_version": "jazn_package_set/v2",
            "package_name": archive_name,
            "profile": profile,
            "archive_format": "independent",
            "package_version": "memory-format-v3",
            "outputs": [
                {"part_no": 1, "filename": archive_name, "size_bytes": len(archive), "sha256": digest}
            ],
        }
    ).encode("utf-8")
    return {
        f"{prefix}/{archive_name}": archive,
        f"{prefix}/{archive_name}.package.json": sidecar,
    }


def test_memory_attach_sources_are_exclusive_and_r2_verifies_transport(tmp_path: Path) -> None:
    parser = build_parser()
    assert parser.parse_args(["memory-attach", "--parts-dir", "."]).parts_dir == Path(".")
    assert parser.parse_args(["memory-attach", "--r2-prefix", "snapshots/current"]).r2_prefix == "snapshots/current"
    with pytest.raises(SystemExit):
        parser.parse_args(["memory-attach"])
    with pytest.raises(SystemExit):
        parser.parse_args(["memory-attach", "--parts-dir", ".", "--r2-prefix", "snapshots/current"])

    prefix = "snapshots/current"
    result = memory_contract.materialize_r2_memory_package(
        tmp_path / "runtime",
        key_prefix=prefix,
        bucket="private-memory",
        endpoint_url="https://example.r2.cloudflarestorage.com",
        work_dir=tmp_path / "staging",
        client=_FakeR2Client(_r2_package_objects(prefix=prefix)),
    )
    assert result.source_kind == "cloudflare_r2_s3"
    assert (result.parts_dir / "jazn_memory.zip").read_bytes() == b"memory-package-part"
    assert result.report["direct_s3_transport"] is True
    assert result.report["worker_proxy_required"] is False

    with pytest.raises(memory_contract.MemoryPackageSourceError, match="profile=memory"):
        memory_contract.materialize_r2_memory_package(
            tmp_path / "runtime-b",
            key_prefix=prefix,
            bucket="private-memory",
            endpoint_url="https://example.r2.cloudflarestorage.com",
            work_dir=tmp_path / "staging-b",
            client=_FakeR2Client(_r2_package_objects(prefix=prefix, profile="system")),
        )
    with pytest.raises(memory_contract.MemoryPackageSourceError, match="SHA-256"):
        memory_contract.materialize_r2_memory_package(
            tmp_path / "runtime-c",
            key_prefix=prefix,
            bucket="private-memory",
            endpoint_url="https://example.r2.cloudflarestorage.com",
            work_dir=tmp_path / "staging-c",
            client=_FakeR2Client(_r2_package_objects(prefix=prefix, tamper_sha=True)),
        )


def test_generator_keeps_sqlite_as_one_zip_member_before_optional_outer_transport_split(tmp_path: Path) -> None:
    generator = _load_generator()
    root = tmp_path / "runtime"
    _write_runtime_version(root)
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    db = tmp_path / "memory-source" / "runtime_memory.sqlite3"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE item(id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO item(value) VALUES (?)", ("x" * 4096,))
    plan = generator.plan_pack(
        generator.PackRequest(
            source_root=root,
            output_root=tmp_path / "out",
            content=generator.ContentMode.MEMORY,
            memory_root=db.parent,
        )
    )
    assert "memory/runtime_memory.sqlite3" in {entry.archive_path for entry in plan.entries}


def _write_legacy_package_set(parts_dir: Path) -> bytes:
    source = parts_dir / "source"
    raw = source / "memory" / "raw" / "events.jsonl"
    raw.parent.mkdir(parents=True)
    line = (json.dumps({"event": "x" * 900}) + "\n").encode("utf-8")
    raw_bytes = line * ((1024 * 1024 // len(line)) + 256)
    raw.write_bytes(raw_bytes)

    database = source / "memory" / "sqlite" / "runtime.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=9")
        connection.execute("CREATE TABLE item(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO item(value) VALUES ('legacy')")

    legacy_manifest = source / "memory" / "MEMORY_PACKAGE_MANIFEST.json"
    legacy_manifest.write_text(
        json.dumps(
            {
                "schema_version": "jazn_memory_package_manifest/v1",
                "runtime_version": LEGACY_MEMORY_VERSION,
                "generated_at_utc": "2026-08-01T00:00:00+00:00",
                "file_count": 2,
                "files": [_manifest_file(raw, source), _manifest_file(database, source)],
            }
        ),
        encoding="utf-8",
    )

    archive_name = "legacy_memory.zip"
    archive_path = parts_dir / archive_name
    members = [raw, database, legacy_manifest]
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for member in members:
            archive.write(member, member.relative_to(source).as_posix())

    entries = [_manifest_file(member, source) for member in members]
    sidecar = {
        "schema_version": "jazn_package_set/v2",
        "package_name": archive_name,
        "profile": "memory",
        "archive_format": "independent",
        "package_version": LEGACY_MEMORY_VERSION,
        "logical_zip_sha256": None,
        "outputs": [
            {
                "part_no": 1,
                "filename": archive_name,
                "size_bytes": archive_path.stat().st_size,
                "sha256": _sha(archive_path),
                "is_complete_zip": True,
            }
        ],
        "entries": entries,
    }
    (parts_dir / f"{archive_name}.package.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return raw_bytes


def test_legacy_repack_streams_jsonl_and_snapshots_sqlite_to_v3(tmp_path: Path) -> None:
    parts = tmp_path / "legacy"
    parts.mkdir()
    original_raw = _write_legacy_package_set(parts)
    output = tmp_path / "v3"
    report = memory_contract.repack_legacy_memory_package(
        parts,
        output_dir=output,
        raw_target_bytes=1024 * 1024,
        raw_max_bytes=2 * 1024 * 1024,
        sqlite_max_bytes=8 * 1024 * 1024,
    )
    assert report["ok"] is True
    sidecar = report["package_sidecar"]
    assert sidecar["profile"] == "memory"
    assert sidecar["archive_format"] == "independent"
    assert sidecar["cloud_attach_compatible"] is True
    assert sidecar["memory_manifest_schema"] == "jazn_memory_package_manifest/v3"

    package_root = tmp_path / "extracted"
    package_root.mkdir()
    for item in sidecar["outputs"]:
        with zipfile.ZipFile(output / item["filename"], "r") as archive:
            archive.extractall(package_root)

    runtime = tmp_path / "runtime"
    _write_runtime_version(runtime)
    verified = memory_contract.verify_memory_package_manifest(package_root, runtime_root=runtime)
    assert verified["ok"] is True, verified["errors"]
    manifest = json.loads((package_root / "memory" / "MEMORY_PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "jazn_memory_package_manifest/v3"
    descriptor = manifest["raw_segments"][0]
    assert descriptor["source_sha256"] == hashlib.sha256(original_raw).hexdigest()
    assert len(descriptor["segments"]) >= 2
    assert manifest["databases"][0]["snapshot_method"] == "sqlite_online_backup_api"
    restored = RawJsonlSegmenter.materialize_descriptor(package_root, descriptor)
    assert restored.read_bytes() == original_raw
    with sqlite3.connect(package_root / "memory" / "sqlite" / "runtime.sqlite3") as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT value FROM item").fetchone()[0] == "legacy"

    ns = build_parser().parse_args(["memory-repack-legacy", "--parts-dir", ".", "--output-dir", "./out", "--dry-run"])
    assert ns.command == "memory-repack-legacy" and ns.dry_run is True
    with pytest.raises(SystemExit):
        build_parser().parse_args(["memory-repack-leg", "--parts-dir", ".", "--output-dir", "./out"])
