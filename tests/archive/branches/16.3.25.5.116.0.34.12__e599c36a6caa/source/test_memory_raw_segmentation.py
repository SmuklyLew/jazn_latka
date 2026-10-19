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


def test_clean_pack_generator_archives_raw_jsonl_without_owning_segmentation(tmp_path) -> None:
    import importlib.util
    import sys

    root = tmp_path / "runtime"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        'PACKAGE_VERSION = "16.3.25.5.23"\n'
        'PACKAGE_RELEASE_NAME = "package-generator-v10.1.86.0.111-clean-rewrite"\n',
        encoding="utf-8",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    memory = tmp_path / "memory"
    source = memory / "raw" / "legacy_events.jsonl"
    raw = _write_jsonl(source, rows=120, payload_chars=600)
    generator_path = Path(__file__).resolve().parents[1] / "tools" / "jazn_pack_generator.py"
    name = "jazn_pack_generator_memory_plain_archiver_test"
    spec = importlib.util.spec_from_file_location(name, generator_path)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    sys.modules[name] = generator
    spec.loader.exec_module(generator)
    assert not hasattr(generator, "MEMORY_RAW_SEGMENT_TARGET_BYTES")
    plan = generator.plan_pack(
        generator.PackRequest(
            source_root=root,
            output_root=tmp_path / "out",
            content=generator.ContentMode.MEMORY,
            memory_root=memory,
        )
    )
    entries = {entry.archive_path: entry for entry in plan.entries}
    assert entries["memory/raw/legacy_events.jsonl"].source.read_bytes() == raw
