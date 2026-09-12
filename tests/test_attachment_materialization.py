from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from latka_jazn.packaging.attachment_materialization import (
    AttachmentMaterializationError,
    AttachmentMaterializationState,
    materialize_verified_attachment_copy,
    probe_attachment_materialization,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_probe_reports_ready_only_after_size_and_sha_match(tmp_path: Path) -> None:
    payload = b"complete-package-part"
    source = tmp_path / "package.zip.001"
    source.write_bytes(payload)

    report = probe_attachment_materialization(
        source,
        expected_size_bytes=len(payload),
        expected_sha256=_sha(payload),
        chunk_size=3,
    )

    assert report.ok is True
    assert report.state is AttachmentMaterializationState.READY
    assert report.stable_during_read is True
    assert report.observed_size_bytes == len(payload)
    assert report.observed_sha256 == _sha(payload)


def test_probe_reports_stable_truncated_source_as_incomplete(tmp_path: Path) -> None:
    source = tmp_path / "package.zip.004"
    source.write_bytes(b"partial")

    report = probe_attachment_materialization(
        source,
        expected_size_bytes=32,
        expected_sha256=_sha(b"x" * 32),
    )

    assert report.ok is False
    assert report.state is AttachmentMaterializationState.INCOMPLETE
    assert report.reason_code == "observed_size_below_expected"


def test_probe_reports_hash_mismatch_after_size_matches(tmp_path: Path) -> None:
    source = tmp_path / "package.zip.002"
    source.write_bytes(b"same-size-wrong")

    report = probe_attachment_materialization(
        source,
        expected_size_bytes=len(b"same-size-wrong"),
        expected_sha256=_sha(b"same-size-good!"),
    )

    assert report.ok is False
    assert report.state is AttachmentMaterializationState.HASH_MISMATCH


def test_verified_copy_freezes_source_into_independent_canonical_file(tmp_path: Path) -> None:
    payload = b"verified-volume" * 64
    source = tmp_path / "package(1).006"
    source.write_bytes(payload)
    target = tmp_path / "canonical" / "package.006"

    report = materialize_verified_attachment_copy(
        source,
        target,
        expected_size_bytes=len(payload),
        expected_sha256=_sha(payload),
        chunk_size=17,
    )

    assert report["ok"] is True
    assert report["materialization"] == "verified_atomic_copy"
    assert target.read_bytes() == payload
    source.write_bytes(b"later-host-rewrite")
    assert target.read_bytes() == payload
    assert report["sha256"] == _sha(payload)


def test_verified_copy_rejects_incomplete_source_without_publishing_target(tmp_path: Path) -> None:
    source = tmp_path / "package.zip.004"
    source.write_bytes(b"partial")
    target = tmp_path / "canonical" / "package.zip.004"

    with pytest.raises(AttachmentMaterializationError) as exc_info:
        materialize_verified_attachment_copy(
            source,
            target,
            expected_size_bytes=100,
            expected_sha256=_sha(b"x" * 100),
        )

    assert exc_info.value.report.state is AttachmentMaterializationState.INCOMPLETE
    assert not target.exists()
    assert not list(target.parent.glob("*.tmp"))


def test_verified_copy_rejects_wrong_digest_without_publishing_target(tmp_path: Path) -> None:
    payload = b"right-length-wrong-content"
    source = tmp_path / "package.zip.003"
    source.write_bytes(payload)
    target = tmp_path / "canonical" / "package.zip.003"

    with pytest.raises(AttachmentMaterializationError) as exc_info:
        materialize_verified_attachment_copy(
            source,
            target,
            expected_size_bytes=len(payload),
            expected_sha256=_sha(b"different-content-same-ish"),
        )

    assert exc_info.value.report.state is AttachmentMaterializationState.HASH_MISMATCH
    assert not target.exists()


def test_missing_source_is_explicit_not_filesystem_unavailable(tmp_path: Path) -> None:
    report = probe_attachment_materialization(
        tmp_path / "missing.zip.001",
        expected_size_bytes=10,
        expected_sha256=_sha(b"0123456789"),
    )

    assert report.state is AttachmentMaterializationState.MISSING
    assert report.reason_code == "source_missing"
    assert report.identity_before is None
