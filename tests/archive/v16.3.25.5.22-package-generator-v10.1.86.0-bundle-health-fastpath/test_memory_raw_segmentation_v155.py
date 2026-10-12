from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from latka_jazn.packaging.memory_raw_segmentation import (
    RawJsonlSegmenter,
    RawMemorySegmentationError,
    RawMemorySegmentationPolicy,
)


def _write_jsonl(path: Path, rows: int, payload_chars: int = 120) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"".join(
        (json.dumps({"i": idx, "value": "x" * payload_chars}, separators=(",", ":")) + "\n").encode("utf-8")
        for idx in range(rows)
    )
    path.write_bytes(raw)
    return raw


def test_segmenter_preserves_exact_bytes_and_bounded_members(tmp_path) -> None:
    source = tmp_path / "source" / "history.jsonl"
    raw = _write_jsonl(source, rows=80, payload_chars=140)
    staging = tmp_path / "staging"
    policy = RawMemorySegmentationPolicy(target_segment_bytes=1024 * 1024, max_segment_bytes=1024 * 1024)
    # Production policy requires >=1 MiB, so construct an equivalent test policy by
    # creating the object without bypassing segmenter logic only for small fixture sizes.
    object.__setattr__(policy, "target_segment_bytes", 4096)
    object.__setattr__(policy, "max_segment_bytes", 8192)
    result = RawJsonlSegmenter(policy).segment(
        source,
        source_relative="memory/raw/history.jsonl",
        staging_root=staging,
    )
    assert len(result.segments) > 1
    assert result.source_size_bytes == len(raw)
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert all(segment.size_bytes <= 8192 for segment in result.segments)
    report = RawJsonlSegmenter.verify_descriptor(staging, result.to_dict())
    assert report["ok"] is True
    assert report["source_sha256"] == hashlib.sha256(raw).hexdigest()

    target = RawJsonlSegmenter.materialize_descriptor(staging, result.to_dict(), remove_segments=True)
    assert target.read_bytes() == raw
    assert not any((staging / "memory/raw/history.jsonl.segments").glob("segment-*.jsonl"))


def test_segmenter_fails_closed_on_single_line_above_member_limit(tmp_path) -> None:
    source = tmp_path / "huge-line.jsonl"
    source.write_bytes(b"{" + b"x" * 9000 + b"}\n")
    policy = RawMemorySegmentationPolicy(target_segment_bytes=1024 * 1024, max_segment_bytes=1024 * 1024)
    object.__setattr__(policy, "target_segment_bytes", 4096)
    object.__setattr__(policy, "max_segment_bytes", 8192)
    with pytest.raises(RawMemorySegmentationError, match="single JSONL line exceeds"):
        RawJsonlSegmenter(policy).segment(
            source,
            source_relative="memory/raw/huge-line.jsonl",
            staging_root=tmp_path / "staging",
        )


def test_segment_descriptor_detects_tampered_segment(tmp_path) -> None:
    source = tmp_path / "source.jsonl"
    _write_jsonl(source, rows=50, payload_chars=180)
    policy = RawMemorySegmentationPolicy(target_segment_bytes=1024 * 1024, max_segment_bytes=1024 * 1024)
    object.__setattr__(policy, "target_segment_bytes", 4096)
    object.__setattr__(policy, "max_segment_bytes", 8192)
    result = RawJsonlSegmenter(policy).segment(
        source,
        source_relative="memory/raw/source.jsonl",
        staging_root=tmp_path / "staging",
    )
    first = tmp_path / "staging" / result.segments[0].package_path
    with first.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(RawMemorySegmentationError, match="SHA-256 mismatch"):
        RawJsonlSegmenter.verify_descriptor(tmp_path / "staging", result.to_dict())


def test_memory_generator_v3_segments_oversized_jsonl_before_zip(tmp_path, monkeypatch) -> None:
    import importlib.util
    import sys

    root = tmp_path / "runtime"
    source = root / "memory" / "raw" / "legacy_events.jsonl"
    # ~3 MiB exact-line fixture: large enough to exercise production lower bound.
    raw = _write_jsonl(source, rows=5500, payload_chars=600)
    generator_path = Path(__file__).resolve().parents[1] / "tools" / "jazn_pack_generator.py"
    name = "jazn_pack_generator_memory_v3_segmentation_test"
    spec = importlib.util.spec_from_file_location(name, generator_path)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    sys.modules[name] = generator
    spec.loader.exec_module(generator)
    monkeypatch.setattr(generator, "MEMORY_RAW_SEGMENT_TARGET_BYTES", 1024 * 1024)
    monkeypatch.setattr(generator, "MEMORY_RAW_SEGMENT_MAX_BYTES", 2 * 1024 * 1024)
    version = generator.VersionInfo(
        version_file=Path("latka_jazn/version.py"),
        package_version="v15.5",
        release_name="memory-v3-test",
        full_version="v15.5-memory-v3-test",
        filename_version="15.5-memory-v3-test",
    )
    plan = generator.build_memory_plan(
        root,
        version,
        [source.relative_to(root).as_posix()],
        [],
        "test",
    )
    try:
        paths = set(plan.paths)
        assert source.relative_to(root).as_posix() not in paths
        segment_paths = sorted(path for path in paths if ".jsonl.segments/segment-" in path)
        assert len(segment_paths) >= 2
        entries = {entry.relative: entry for entry in plan.entries}
        assert all(entries[path].size_bytes <= 2 * 1024 * 1024 for path in segment_paths)
        manifest_entry = entries[generator.MEMORY_PACKAGE_MANIFEST]
        payload = json.loads(manifest_entry.virtual_bytes)
        assert payload["schema_version"] == "jazn_memory_package_manifest/v3"
        assert payload["memory_format_version"] == 3
        assert payload["raw_segments"][0]["source_sha256"] == hashlib.sha256(raw).hexdigest()

        extracted = tmp_path / "extracted"
        for entry in plan.entries:
            target = extracted / entry.relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if entry.virtual_bytes is not None:
                target.write_bytes(entry.virtual_bytes)
            else:
                assert entry.source is not None
                target.write_bytes(entry.source.read_bytes())
        from latka_jazn.packaging.memory_package_manifest import verify_memory_package_manifest

        report = verify_memory_package_manifest(extracted, runtime_root=extracted)
        # Runtime version file is intentionally absent in this transport-only fixture;
        # manifest verification itself remains valid because runtime version is provenance.
        assert report["ok"] is True
        reconstructed = RawJsonlSegmenter.materialize_descriptor(
            extracted, payload["raw_segments"][0], remove_segments=True
        )
        assert reconstructed.read_bytes() == raw
    finally:
        plan.cleanup()
