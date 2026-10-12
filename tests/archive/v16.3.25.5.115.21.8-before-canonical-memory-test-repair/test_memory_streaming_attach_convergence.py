from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import errno
import hashlib
import inspect
import json
import uuid
import zipfile

import pytest

from latka_jazn.packaging.generator_v2_compat import normalize_generator_v2_compat
from latka_jazn.bootstrap import chatgpt_recovery
from latka_jazn.packaging.memory_package_manifest import verify_memory_package_manifest
from latka_jazn.packaging.memory_package_types import MEMORY_RUNTIME_COMPATIBILITY_CONTRACT
from latka_jazn.packaging import memory_package_attach as attach_module
from latka_jazn.packaging import memory_streaming_transport as streaming
from tools.jazn_pack_generator_app.constants import SYSTEM_BOOTSTRAP_REQUIRED_FILES
from tools.jazn_pack_generator_app.manifest import build_memory_attachment_contract
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry


def _entry(path: str, payload: bytes, *, classification: str = "memory_file") -> dict[str, object]:
    return {
        "kind": "file",
        "path": path,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "classification": classification,
    }


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path, payload in files.items():
            archive.writestr(path, payload)
    return buffer.getvalue()


def _write_split_generator_v2(
    root: Path,
    *,
    logical_name: str,
    files: dict[str, bytes],
) -> tuple[dict[str, object], dict[str, object]]:
    payload = _zip_bytes(files)
    midpoint = max(1, len(payload) // 2)
    chunks = (payload[:midpoint], payload[midpoint:])
    parts: list[dict[str, object]] = []
    for index, chunk in enumerate(chunks, start=1):
        filename = f"{logical_name}.{index:03d}"
        (root / filename).write_bytes(chunk)
        parts.append(
            {
                "part_no": index,
                "filename": filename,
                "size_bytes": len(chunk),
                "sha256": hashlib.sha256(chunk).hexdigest(),
            }
        )
    generator = {
        "schema_version": "jazn_pack_generator_package/v2",
        "package_version": "legacy-memory-test",
        "content": "memory",
        "archive": {
            "logical_filename": logical_name,
            "logical_size_bytes": len(payload),
            "logical_sha256": hashlib.sha256(payload).hexdigest(),
        },
        "split": {"parts": parts},
        "source": {
            "entries": [_entry(path, data) for path, data in files.items()],
        },
    }
    normalized = normalize_generator_v2_compat(generator)
    return generator, normalized


def test_generator_v2_normalization_is_metadata_only(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    payload = {
        "schema_version": "jazn_pack_generator_package/v2",
        "package_version": "legacy",
        "content": "memory",
        "archive": {
            "logical_filename": "memory.zip",
            "logical_size_bytes": 4,
            "logical_sha256": hashlib.sha256(b"data").hexdigest(),
        },
        "split": {
            "parts": [
                {
                    "part_no": 1,
                    "filename": "memory.zip.001",
                    "size_bytes": 4,
                    "sha256": hashlib.sha256(b"data").hexdigest(),
                }
            ]
        },
        "source": {"entries": []},
    }

    normalized = normalize_generator_v2_compat(payload)

    assert set(tmp_path.iterdir()) == before
    assert normalized["runtime_metadata_only_adapter"] is True
    assert normalized["profile"] == "memory"
    assert normalized["archive_format"] == "binary"
    assert normalized["outputs"][0]["filename"] == "memory.zip.001"


def test_split_zip_reader_opens_logical_zip_without_joined_file(tmp_path: Path) -> None:
    archive_bytes = _zip_bytes({"memory/raw/a.txt": b"abc"})
    split_at = len(archive_bytes) // 2
    first = tmp_path / "memory.zip.001"
    second = tmp_path / "memory.zip.002"
    first.write_bytes(archive_bytes[:split_at])
    second.write_bytes(archive_bytes[split_at:])

    with streaming.SplitZipReader([first, second]) as raw:
        with zipfile.ZipFile(raw, "r") as archive:
            assert archive.read("memory/raw/a.txt") == b"abc"

    assert not (tmp_path / "memory.zip").exists()


def test_streaming_attach_legacy_generator_v2_writes_one_candidate_tree(
    tmp_path: Path,
) -> None:
    raw = b'{"event":"one"}\n{"event":"two"}\n'
    raw_entry = _entry("memory/raw/events.jsonl", raw)
    manifest = {
        "schema_version": "jazn_memory_package_manifest/v1",
        "runtime_version": "legacy-memory-test",
        "file_count": 1,
        "files": [
            {
                "path": raw_entry["path"],
                "size_bytes": raw_entry["size_bytes"],
                "sha256": raw_entry["sha256"],
            }
        ],
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    files = {
        "memory/MEMORY_PACKAGE_MANIFEST.json": manifest_bytes,
        "memory/raw/events.jsonl": raw,
    }
    _generator, normalized = _write_split_generator_v2(
        tmp_path,
        logical_name="memory.zip",
        files=files,
    )
    target = tmp_path / "workspace" / "memory"

    result = streaming.stream_extract_verified_memory_package(
        tmp_path / "runtime",
        tmp_path,
        target_memory_root=target,
        base_zip_name="memory.zip",
        package_sidecar=normalized,
    )

    assert result["ok"] is True
    assert result["bytes_copied_for_transport_normalization"] == 0
    assert result["joined_zip_materialized"] is False
    assert result["runtime_repack_performed"] is False
    staging = Path(result["staging"])
    assert (staging / "memory" / "raw" / "events.jsonl").read_bytes() == raw
    assert not (tmp_path / "memory.zip").exists()
    assert not any(path.name == "canonical_parts" for path in tmp_path.rglob("*"))
    verified = verify_memory_package_manifest(staging)
    assert verified["ok"] is True, verified


def test_v3_raw_segments_stream_directly_to_logical_source(tmp_path: Path) -> None:
    segment_a = b'{"id":1}\n'
    segment_b = b'{"id":2}\n'
    logical = segment_a + segment_b
    source_path = "memory/raw/events.jsonl"
    segment_paths = (
        source_path + ".segments/segment-000001.jsonl",
        source_path + ".segments/segment-000002.jsonl",
    )
    descriptor = {
        "format": "jsonl_exact_line_segments/v1",
        "source_path": source_path,
        "source_size_bytes": len(logical),
        "source_sha256": hashlib.sha256(logical).hexdigest(),
        "source_line_count": 2,
        "segments": [
            {
                "package_path": segment_paths[0],
                "segment_index": 1,
                "line_count": 1,
                "size_bytes": len(segment_a),
                "sha256": hashlib.sha256(segment_a).hexdigest(),
                "first_line_number": 1,
                "last_line_number": 1,
            },
            {
                "package_path": segment_paths[1],
                "segment_index": 2,
                "line_count": 1,
                "size_bytes": len(segment_b),
                "sha256": hashlib.sha256(segment_b).hexdigest(),
                "first_line_number": 2,
                "last_line_number": 2,
            },
        ],
    }
    files_manifest = [
        {
            "path": segment_paths[0],
            "size_bytes": len(segment_a),
            "sha256": hashlib.sha256(segment_a).hexdigest(),
            "classification": "memory_raw_segment",
        },
        {
            "path": segment_paths[1],
            "size_bytes": len(segment_b),
            "sha256": hashlib.sha256(segment_b).hexdigest(),
            "classification": "memory_raw_segment",
        },
    ]
    manifest = {
        "schema_version": "jazn_memory_package_manifest/v3",
        "memory_format_version": 3,
        "snapshot_id": str(uuid.uuid4()),
        "created_at_utc": "2026-10-05T00:00:00+00:00",
        "generated_at_utc": "2026-10-05T00:00:00+00:00",
        "created_with_runtime": "legacy-memory-test",
        "compatibility": {
            "contract": MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
            "runtime_version_is_provenance_only": True,
            "memory_format_version": 3,
            "manifest_schema": "jazn_memory_package_manifest/v3",
        },
        "file_count": len(files_manifest),
        "files": files_manifest,
        "databases": [],
        "raw_segments": [descriptor],
        "package_member_limit_bytes": 1024 * 1024,
        "raw_segment_member_limit_bytes": 1024 * 1024,
        "sqlite_snapshot_member_limit_bytes": 1024 * 1024,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    package_files = {
        "memory/MEMORY_PACKAGE_MANIFEST.json": manifest_bytes,
        segment_paths[0]: segment_a,
        segment_paths[1]: segment_b,
    }
    _generator, normalized = _write_split_generator_v2(
        tmp_path,
        logical_name="memory-v3.zip",
        files=package_files,
    )
    normalized["memory_manifest_schema"] = "jazn_memory_package_manifest/v3"
    target = tmp_path / "workspace" / "memory"

    result = streaming.stream_extract_verified_memory_package(
        tmp_path / "runtime",
        tmp_path,
        target_memory_root=target,
        base_zip_name="memory-v3.zip",
        package_sidecar=normalized,
    )

    assert result["ok"] is True
    assert result["raw_segments_materialized"] is True
    staging = Path(result["staging"])
    assert (staging / source_path).read_bytes() == logical
    assert not (staging / segment_paths[0]).exists()
    assert not (staging / segment_paths[1]).exists()
    verified = verify_memory_package_manifest(
        staging,
        installed_raw_segments=True,
    )
    assert verified["ok"] is True, verified
    assert verified["materialized_raw_source_count"] == 1


def test_disk_preflight_fails_before_large_payload_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        streaming.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(
            total=32 * 1024 * 1024,
            used=31 * 1024 * 1024,
            free=1 * 1024 * 1024,
        ),
    )

    with pytest.raises(
        streaming.MemoryStreamingTransportError,
        match="insufficient_disk_space",
    ):
        streaming._disk_preflight(
            tmp_path,
            tmp_path / "staging",
            expected_payload_bytes=8 * 1024 * 1024,
        )


def test_atomic_install_refuses_cross_filesystem_copy_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    runtime_root.mkdir()
    source_memory = tmp_path / "incoming-memory"
    source_memory.mkdir()
    (source_memory / "payload.txt").write_text("memory", encoding="utf-8")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))

    target = workspace / "memory"
    original_replace = attach_module.os.replace

    def replace_with_exdev(src: str | Path, dst: str | Path) -> None:
        if Path(src).resolve() == source_memory.resolve() and Path(dst).resolve() == target.resolve():
            raise OSError(errno.EXDEV, "synthetic cross-filesystem move")
        original_replace(src, dst)

    monkeypatch.setattr(attach_module.os, "replace", replace_with_exdev)
    monkeypatch.setattr(
        attach_module.shutil,
        "copytree",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("copytree fallback must not be used")
        ),
    )

    with pytest.raises(OSError, match="copy fallback is disabled"):
        attach_module._install_memory_tree(
            runtime_root,
            workspace,
            source_memory,
            {},
        )

    assert source_memory.is_dir()
    assert not target.exists()


def _system_pack_plan(tmp_path: Path) -> PackPlan:
    source_root = tmp_path / "system-source"
    source_root.mkdir(exist_ok=True)
    entries = tuple(
        SourceEntry(
            source=source_root / name,
            archive_path=name,
            size_bytes=1,
            is_dir=False,
        )
        for name in SYSTEM_BOOTSTRAP_REQUIRED_FILES
    )
    return PackPlan(
        request=PackRequest(
            source_root=source_root,
            output_root=tmp_path / "out",
            content=ContentMode.SYSTEM,
        ),
        package_version="16.3.25.5.105-test",
        package_basename="test.zip",
        entries=entries,
        excluded=(),
        source_total_size_bytes=len(entries),
    )


def test_generator_contract_declares_low_amplification_runtime_attach(
    tmp_path: Path,
) -> None:
    contract = build_memory_attachment_contract(_system_pack_plan(tmp_path))

    assert contract["runtime_attach_transport_strategy"] == (
        "verified_streaming_single_candidate"
    )
    assert contract["runtime_attach_transport_copy_required"] is False
    assert contract["runtime_attach_joined_zip_required"] is False
    assert contract["runtime_attach_repack_required"] is False
    assert contract["runtime_attach_staging_same_filesystem_required"] is True
    assert contract["runtime_attach_cross_filesystem_copy_fallback"] is False
    assert contract["runtime_attach_disk_preflight_required"] is True
    assert contract["runtime_attach_v3_raw_segments_stream_to_logical_source"] is True
    assert contract["legacy_transport_repack_supported"] is True


def test_runtime_converge_source_does_not_reintroduce_transport_repack_or_compat_copy() -> None:
    source = inspect.getsource(chatgpt_recovery._auto_attach_memory_before_daemon)

    assert "repack_legacy_memory_package(" not in source
    assert "materialize_generator_v2_compat(" not in source
    assert "normalize_generator_v2_compat(" in source
    assert "runtime_repack_performed" in source
