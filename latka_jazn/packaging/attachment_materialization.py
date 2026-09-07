from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import os
from pathlib import Path
import uuid
from typing import Any


CHUNK_SIZE = 8 * 1024 * 1024


class AttachmentMaterializationState(str, Enum):
    UNKNOWN = "unknown"
    MISSING = "missing"
    MATERIALIZING = "materializing"
    INCOMPLETE = "incomplete"
    SIZE_MISMATCH = "size_mismatch"
    HASH_MISMATCH = "hash_mismatch"
    READY = "ready"


@dataclass(frozen=True)
class FileIdentity:
    size_bytes: int
    mtime_ns: int
    device: int | None
    inode: int | None

    @classmethod
    def from_path(cls, path: Path) -> "FileIdentity":
        stat_result = Path(path).stat()
        return cls(
            size_bytes=int(stat_result.st_size),
            mtime_ns=int(stat_result.st_mtime_ns),
            device=int(stat_result.st_dev) if hasattr(stat_result, "st_dev") else None,
            inode=int(stat_result.st_ino) if hasattr(stat_result, "st_ino") else None,
        )


@dataclass(frozen=True)
class AttachmentMaterializationReport:
    state: AttachmentMaterializationState
    path: str
    expected_size_bytes: int | None
    expected_sha256: str | None
    observed_size_bytes: int | None
    observed_sha256: str | None
    identity_before: FileIdentity | None
    identity_after: FileIdentity | None
    stable_during_read: bool
    reason_code: str

    @property
    def ok(self) -> bool:
        return self.state is AttachmentMaterializationState.READY

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["ok"] = self.ok
        return payload


class AttachmentMaterializationError(ValueError):
    def __init__(self, report: AttachmentMaterializationReport) -> None:
        self.report = report
        super().__init__(f"attachment_materialization_{report.state.value}:{report.reason_code}")


def _normalize_expected_sha256(value: str | None) -> str | None:
    digest = str(value or "").strip().lower()
    if not digest:
        return None
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("expected_sha256_must_be_64_hex_chars")
    return digest


def _state_for_size(actual: int, expected: int) -> tuple[AttachmentMaterializationState, str]:
    if actual < expected:
        return AttachmentMaterializationState.INCOMPLETE, "observed_size_below_expected"
    return AttachmentMaterializationState.SIZE_MISMATCH, "observed_size_above_expected"


def probe_attachment_materialization(
    path: Path,
    *,
    expected_size_bytes: int | None = None,
    expected_sha256: str | None = None,
    chunk_size: int = CHUNK_SIZE,
) -> AttachmentMaterializationReport:
    """Read one attachment once and report whether that exact read was stable.

    The probe never infers that a missing or truncated file is permanently bad.
    A changed stat identity across the read is classified as ``materializing``;
    callers may retry later according to their own bounded host policy.  A
    stable file is accepted only after expected size and SHA-256 checks pass.
    """

    source = Path(path).expanduser().resolve()
    expected_sha = _normalize_expected_sha256(expected_sha256)
    if expected_size_bytes is not None and int(expected_size_bytes) < 0:
        raise ValueError("expected_size_bytes_must_be_non_negative")

    try:
        before = FileIdentity.from_path(source)
    except FileNotFoundError:
        return AttachmentMaterializationReport(
            state=AttachmentMaterializationState.MISSING,
            path=str(source),
            expected_size_bytes=expected_size_bytes,
            expected_sha256=expected_sha,
            observed_size_bytes=None,
            observed_sha256=None,
            identity_before=None,
            identity_after=None,
            stable_during_read=False,
            reason_code="source_missing",
        )

    digest = hashlib.sha256()
    bytes_read = 0
    try:
        with source.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                bytes_read += len(chunk)
                digest.update(chunk)
        after = FileIdentity.from_path(source)
    except FileNotFoundError:
        return AttachmentMaterializationReport(
            state=AttachmentMaterializationState.MATERIALIZING,
            path=str(source),
            expected_size_bytes=expected_size_bytes,
            expected_sha256=expected_sha,
            observed_size_bytes=bytes_read,
            observed_sha256=digest.hexdigest(),
            identity_before=before,
            identity_after=None,
            stable_during_read=False,
            reason_code="source_disappeared_during_read",
        )

    observed_sha = digest.hexdigest()
    stable = before == after and bytes_read == after.size_bytes
    if not stable:
        return AttachmentMaterializationReport(
            state=AttachmentMaterializationState.MATERIALIZING,
            path=str(source),
            expected_size_bytes=expected_size_bytes,
            expected_sha256=expected_sha,
            observed_size_bytes=bytes_read,
            observed_sha256=observed_sha,
            identity_before=before,
            identity_after=after,
            stable_during_read=False,
            reason_code="source_changed_during_read",
        )

    if expected_size_bytes is not None and bytes_read != int(expected_size_bytes):
        state, reason = _state_for_size(bytes_read, int(expected_size_bytes))
        return AttachmentMaterializationReport(
            state=state,
            path=str(source),
            expected_size_bytes=int(expected_size_bytes),
            expected_sha256=expected_sha,
            observed_size_bytes=bytes_read,
            observed_sha256=observed_sha,
            identity_before=before,
            identity_after=after,
            stable_during_read=True,
            reason_code=reason,
        )

    if expected_sha is not None and observed_sha != expected_sha:
        return AttachmentMaterializationReport(
            state=AttachmentMaterializationState.HASH_MISMATCH,
            path=str(source),
            expected_size_bytes=expected_size_bytes,
            expected_sha256=expected_sha,
            observed_size_bytes=bytes_read,
            observed_sha256=observed_sha,
            identity_before=before,
            identity_after=after,
            stable_during_read=True,
            reason_code="sha256_mismatch",
        )

    return AttachmentMaterializationReport(
        state=AttachmentMaterializationState.READY,
        path=str(source),
        expected_size_bytes=expected_size_bytes,
        expected_sha256=expected_sha,
        observed_size_bytes=bytes_read,
        observed_sha256=observed_sha,
        identity_before=before,
        identity_after=after,
        stable_during_read=True,
        reason_code="attachment_ready",
    )


def materialize_verified_attachment_copy(
    source: Path,
    target: Path,
    *,
    expected_size_bytes: int | None,
    expected_sha256: str | None,
    chunk_size: int = CHUNK_SIZE,
) -> dict[str, Any]:
    """Freeze an attachment into a private canonical file and verify the copy.

    A hard link is intentionally not used: a host can still mutate the source
    inode after a successful hash.  Bytes are copied into a unique temporary
    file, hashed while copying, fsynced, compared with source identity before
    and after the read, then atomically moved into place.  The final canonical
    copy is re-probed before success is returned.
    """

    source = Path(source).expanduser().resolve()
    target = Path(target).expanduser().resolve()
    expected_sha = _normalize_expected_sha256(expected_sha256)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        before = FileIdentity.from_path(source)
    except FileNotFoundError:
        report = probe_attachment_materialization(
            source,
            expected_size_bytes=expected_size_bytes,
            expected_sha256=expected_sha,
            chunk_size=chunk_size,
        )
        raise AttachmentMaterializationError(report)

    tmp = target.with_name(f".{target.name}.materializing-{uuid.uuid4().hex}.tmp")
    digest = hashlib.sha256()
    bytes_copied = 0
    try:
        with source.open("rb") as source_handle, tmp.open("xb") as target_handle:
            while True:
                chunk = source_handle.read(chunk_size)
                if not chunk:
                    break
                target_handle.write(chunk)
                digest.update(chunk)
                bytes_copied += len(chunk)
            target_handle.flush()
            os.fsync(target_handle.fileno())

        try:
            after = FileIdentity.from_path(source)
        except FileNotFoundError:
            report = AttachmentMaterializationReport(
                state=AttachmentMaterializationState.MATERIALIZING,
                path=str(source),
                expected_size_bytes=expected_size_bytes,
                expected_sha256=expected_sha,
                observed_size_bytes=bytes_copied,
                observed_sha256=digest.hexdigest(),
                identity_before=before,
                identity_after=None,
                stable_during_read=False,
                reason_code="source_disappeared_during_copy",
            )
            raise AttachmentMaterializationError(report)

        stable = before == after and bytes_copied == after.size_bytes
        observed_sha = digest.hexdigest()
        if not stable:
            report = AttachmentMaterializationReport(
                state=AttachmentMaterializationState.MATERIALIZING,
                path=str(source),
                expected_size_bytes=expected_size_bytes,
                expected_sha256=expected_sha,
                observed_size_bytes=bytes_copied,
                observed_sha256=observed_sha,
                identity_before=before,
                identity_after=after,
                stable_during_read=False,
                reason_code="source_changed_during_copy",
            )
            raise AttachmentMaterializationError(report)

        if expected_size_bytes is not None and bytes_copied != int(expected_size_bytes):
            state, reason = _state_for_size(bytes_copied, int(expected_size_bytes))
            report = AttachmentMaterializationReport(
                state=state,
                path=str(source),
                expected_size_bytes=int(expected_size_bytes),
                expected_sha256=expected_sha,
                observed_size_bytes=bytes_copied,
                observed_sha256=observed_sha,
                identity_before=before,
                identity_after=after,
                stable_during_read=True,
                reason_code=reason,
            )
            raise AttachmentMaterializationError(report)

        if expected_sha is not None and observed_sha != expected_sha:
            report = AttachmentMaterializationReport(
                state=AttachmentMaterializationState.HASH_MISMATCH,
                path=str(source),
                expected_size_bytes=expected_size_bytes,
                expected_sha256=expected_sha,
                observed_size_bytes=bytes_copied,
                observed_sha256=observed_sha,
                identity_before=before,
                identity_after=after,
                stable_during_read=True,
                reason_code="sha256_mismatch",
            )
            raise AttachmentMaterializationError(report)

        os.replace(tmp, target)
        final_report = probe_attachment_materialization(
            target,
            expected_size_bytes=expected_size_bytes if expected_size_bytes is not None else bytes_copied,
            expected_sha256=expected_sha if expected_sha is not None else observed_sha,
            chunk_size=chunk_size,
        )
        if not final_report.ok:
            raise AttachmentMaterializationError(final_report)
        return {
            "ok": True,
            "state": AttachmentMaterializationState.READY.value,
            "source_path": str(source),
            "canonical_path": str(target),
            "size_bytes": bytes_copied,
            "sha256": observed_sha,
            "source_identity_before": asdict(before),
            "source_identity_after": asdict(after),
            "canonical_report": final_report.to_dict(),
            "materialization": "verified_atomic_copy",
        }
    finally:
        tmp.unlink(missing_ok=True)
