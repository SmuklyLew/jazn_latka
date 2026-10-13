"""Independent artifact pins, never self-certification by database metadata.

Pins must come from an operator-reviewed external reference. This service does
not discover or trust a pin stored beside a database. Verification establishes
an exact artifact binding and (when declared) one pinned parent edge; it does
not establish the historical correctness of a rebuild or authorize activation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import time
from typing import Any

from latka_jazn.memory.database_identity import inspect_memory_database
from .p1_memory_inspection import _has_symlink
from .p1_memory_provenance import _read_meta


@dataclass(frozen=True)
class PinnedMemoryArtifact:
    path: Path
    expected_sha256: str


def _stamp(stat: os.stat_result) -> tuple[int, int, int, int, int]:
    # On Windows Python 3.12+, stat(path).st_ctime_ns describes creation time,
    # while fstat(fd).st_ctime_ns may describe metadata change time (CPython
    # python/cpython#157671). Compare birthtime across the two APIs instead.
    # Do not discard ctime: compare it separately *within* each API below.
    creation_or_change_ns = (
        stat.st_birthtime_ns if os.name == "nt" else stat.st_ctime_ns
    )
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, creation_or_change_ns


def _same_source_stamp(before: os.stat_result, after: os.stat_result) -> bool:
    # Keep metadata-change protection on Windows, without equating path stat's
    # birthtime with fstat's change time. No special-case for known hashes.
    return (
        _stamp(before) == _stamp(after)
        and (os.name != "nt" or before.st_ctime_ns == after.st_ctime_ns)
    )


def _stable_digest(path: Path, *, max_bytes: int, deadline: float) -> str:
    if _has_symlink(path) or any(
        getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)
    ):
        raise ValueError("unsafe_artifact_path")
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("artifact_not_frozen")
    before = path.stat()
    if not path.is_file() or before.st_size > max_bytes:
        raise ValueError("artifact_size_limit")
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        fd_before = os.fstat(stream.fileno())
        if _stamp(fd_before) != _stamp(before):
            raise ValueError("artifact_changed")
        while chunk := stream.read(1024 * 1024):
            count += len(chunk)
            if count > max_bytes or time.monotonic() > deadline:
                raise ValueError("artifact_resource_limit")
            digest.update(chunk)
        if not _same_source_stamp(fd_before, os.fstat(stream.fileno())):
            raise ValueError("artifact_changed")
    if not _same_source_stamp(before, path.stat()) or _has_symlink(path):
        raise ValueError("artifact_changed")
    return digest.hexdigest()


def verify_provenance_chain(
    snapshot: Path, *, reference: PinnedMemoryArtifact | None = None,
    parent: PinnedMemoryArtifact | None = None,
    max_bytes: int = 8 * 1024**3, timeout_seconds: float = 90,
) -> dict[str, Any]:
    """Inspect immutable snapshots only; return codes, never hashes or paths."""
    result: dict[str, Any] = {
        "state": "unverified", "issue": "independent_reference_missing",
        "artifact_verified": False, "parent_chain_verified": False,
        "scope": "pinned_artifact_and_single_parent_edge",
        "historical_rebuild_verified": False, "activation_authorized": False,
    }
    if reference is None:
        return result
    if max_bytes < 1 or timeout_seconds <= 0:
        return {**result, "state": "blocked", "issue": "invalid_resource_limit"}
    deadline = time.monotonic() + timeout_seconds
    try:
        for pin in (reference, parent):
            if pin is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", pin.expected_sha256):
                return {**result, "state": "conflict", "issue": "invalid_reference_digest"}
        observed = _stable_digest(reference.path, max_bytes=max_bytes, deadline=deadline)
        if observed != reference.expected_sha256.lower():
            return {**result, "state": "conflict", "issue": "reference_pin_mismatch"}
        selected = _stable_digest(snapshot, max_bytes=max_bytes, deadline=deadline)
        if selected != observed:
            return {**result, "state": "different", "issue": "artifact_differs_from_reference"}
        info = inspect_memory_database(snapshot)
        if info.get("kind") != "native_unified" or info.get("compatible") is not True:
            return {**result, "state": "incompatible", "issue": "native_schema_unverified"}
        metadata = _read_meta(snapshot)
        fields = metadata["fields"]
        # alpha/beta are the real canonical rebuild producer's generation names.
        if fields.get("memory_generation") not in {"alpha", "beta"}:
            return {**result, "state": "conflict", "issue": "invalid_generation"}
        if not fields.get("restore_run_id") or not re.fullmatch(
            r"[0-9a-fA-F]{64}", fields.get("source_union_sha256", "")
        ):
            return {**result, "state": "unverified", "issue": "rebuild_claims_incomplete"}
        parent_sha = fields.get("parent_database_sha256")
        result["artifact_verified"] = True
        if parent_sha:
            if not re.fullmatch(r"[0-9a-fA-F]{64}", parent_sha):
                return {**result, "state": "conflict", "issue": "invalid_parent_digest"}
            if parent is None:
                return {**result, "issue": "independent_parent_missing"}
            actual_parent = _stable_digest(parent.path, max_bytes=max_bytes, deadline=deadline)
            if actual_parent != parent.expected_sha256.lower() or actual_parent != parent_sha.lower():
                return {**result, "state": "conflict", "issue": "parent_pin_mismatch"}
            parent_info = inspect_memory_database(parent.path)
            if parent_info.get("compatible") is not True or parent_info.get("kind") != "native_unified":
                return {**result, "state": "incompatible", "issue": "parent_schema_unverified"}
            if _stable_digest(parent.path, max_bytes=max_bytes, deadline=deadline) != actual_parent:
                return {**result, "state": "blocked", "issue": "artifact_changed"}
            result["parent_chain_verified"] = True
        elif fields["memory_generation"] != "alpha":
            return {**result, "issue": "parent_claim_missing"}
        if _stable_digest(snapshot, max_bytes=max_bytes, deadline=deadline) != selected:
            return {**result, "state": "blocked", "issue": "artifact_changed"}
        return {**result, "state": "verified", "issue": "pinned_artifact_verified"}
    except (OSError, ValueError, RuntimeError):
        return {**result, "state": "blocked", "issue": "artifact_read_or_stability_failed"}
