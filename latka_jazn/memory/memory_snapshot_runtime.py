from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zlib

from latka_jazn.memory.memory_sync_backend import MemorySnapshotBackend, MemorySyncBackendError
from latka_jazn.memory.storage_limits import DEFAULT_SNAPSHOT_CHUNK_BYTES
from latka_jazn.memory.memory_sync_contracts import (
    MemorySnapshotChunk,
    MemorySnapshotManifest,
    MemorySyncContractError,
    b64encode,
    canonical_json_bytes,
)
from latka_jazn.memory.memory_sync_crypto import (
    MemoryKeyProvider,
    MemorySnapshotChunkCrypto,
    PyNaClMemorySnapshotChunkCrypto,
)
from latka_jazn.db.runtime_sqlite import connect_runtime_readonly


@dataclass(slots=True, frozen=True)
class SQLiteSnapshotSource:
    logical_path: str
    path: Path

    def __post_init__(self) -> None:
        if not self.logical_path.strip():
            raise MemorySyncContractError("snapshot logical_path is required")
        if Path(self.logical_path).is_absolute() or ".." in Path(self.logical_path).parts:
            raise MemorySyncContractError("snapshot logical_path must be a safe relative path")
        object.__setattr__(self, "path", Path(self.path).expanduser().resolve())


@dataclass(slots=True, frozen=True)
class MemorySnapshotPolicy:
    chunk_plaintext_bytes: int = DEFAULT_SNAPSHOT_CHUNK_BYTES
    zlib_level: int = 6
    integrity_check: bool = True

    def __post_init__(self) -> None:
        if not 64 * 1024 <= self.chunk_plaintext_bytes <= 128 * 1024 * 1024:
            raise MemorySyncContractError("snapshot chunk size must be between 64 KiB and 128 MiB")
        if not 0 <= self.zlib_level <= 9:
            raise MemorySyncContractError("zlib_level must be between 0 and 9")


@dataclass(slots=True, frozen=True)
class MemorySnapshotCreateResult:
    manifest: MemorySnapshotManifest
    manifest_sha256: str
    object_count: int
    uploaded_bytes: int


@dataclass(slots=True, frozen=True)
class MemorySnapshotRestoreResult:
    snapshot_id: str
    staging_root: Path
    restored_paths: tuple[Path, ...]
    integrity: Mapping[str, str]
    verified: bool


class SQLiteMemorySnapshotManager:
    """Verified encrypted snapshot/restore for local SQLite memory databases.

    Active databases are copied with SQLite's Online Backup API into a temporary
    staging root. Only closed, integrity-checked backup files are chunked, compressed,
    authenticated, encrypted, and uploaded as immutable objects. Restore always
    targets a fresh staging root and never overwrites the active memory root in place.
    """

    def __init__(
        self,
        *,
        backend: MemorySnapshotBackend,
        key_provider: MemoryKeyProvider,
        policy: MemorySnapshotPolicy | None = None,
        chunk_crypto: MemorySnapshotChunkCrypto | None = None,
    ) -> None:
        self.backend = backend
        self.key_provider = key_provider
        self.policy = policy or MemorySnapshotPolicy()
        self.chunk_crypto = chunk_crypto or PyNaClMemorySnapshotChunkCrypto()

    def create_snapshot(
        self,
        *,
        stream_id: str,
        sources: tuple[SQLiteSnapshotSource, ...],
        source_memory_generation: str,
        base_remote_seq: int,
        event_chain_head_sha256: str | None = None,
        created_at_utc: datetime | None = None,
    ) -> MemorySnapshotCreateResult:
        if not stream_id.strip() or not source_memory_generation.strip():
            raise MemorySyncContractError("stream_id and source_memory_generation are required")
        if not sources:
            raise MemorySyncContractError("at least one SQLite snapshot source is required")
        when = (created_at_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        identity_seed = canonical_json_bytes(
            {
                "stream_id": stream_id,
                "source_memory_generation": source_memory_generation,
                "base_remote_seq": base_remote_seq,
                "created_at_utc": when.isoformat(),
                "logical_paths": sorted(source.logical_path for source in sources),
            }
        )
        snapshot_id = hashlib.sha256(identity_seed).hexdigest()
        with tempfile.TemporaryDirectory(prefix="jazn-memory-snapshot-") as temp_dir:
            staging_root = Path(temp_dir).resolve()
            prepared: list[tuple[SQLiteSnapshotSource, Path, dict[str, Any]]] = []
            for source in sorted(sources, key=lambda item: item.logical_path):
                if not source.path.is_file():
                    raise FileNotFoundError(source.path)
                staged = staging_root / source.logical_path
                staged.parent.mkdir(parents=True, exist_ok=True)
                self._online_backup(source.path, staged)
                identity = self._verify_sqlite_file(staged)
                prepared.append((source, staged, identity))

            chunks: list[MemorySnapshotChunk] = []
            database_identity: dict[str, Any] = {}
            uploaded_bytes = 0
            for source, staged, identity in prepared:
                database_identity[source.logical_path] = identity
                with staged.open("rb") as handle:
                    chunk_index = 0
                    while True:
                        plaintext = handle.read(self.policy.chunk_plaintext_bytes)
                        if not plaintext:
                            break
                        compressed = zlib.compress(plaintext, self.policy.zlib_level)
                        encrypted, nonce, key_version, aad_sha256 = self._encrypt_snapshot_chunk(
                            snapshot_id=snapshot_id,
                            stream_id=stream_id,
                            logical_path=source.logical_path,
                            chunk_index=chunk_index,
                            plaintext=plaintext,
                            compressed=compressed,
                        )
                        ciphertext_sha256 = hashlib.sha256(encrypted).hexdigest()
                        object_id = f"sha256/{ciphertext_sha256[:2]}/{ciphertext_sha256}"
                        self.backend.put_object(object_id=object_id, data=encrypted)
                        chunks.append(
                            MemorySnapshotChunk(
                                object_id=object_id,
                                logical_path=source.logical_path,
                                chunk_index=chunk_index,
                                ciphertext_sha256=ciphertext_sha256,
                                plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
                                compressed_size=len(compressed),
                                plaintext_size=len(plaintext),
                                key_version=key_version,
                                nonce_b64=b64encode(nonce),
                                codec="zlib",
                                aad_sha256=aad_sha256,
                            )
                        )
                        uploaded_bytes += len(encrypted)
                        chunk_index += 1
                if chunk_index == 0:
                    raise MemorySyncContractError(f"snapshot source is empty: {source.logical_path}")

            manifest = MemorySnapshotManifest(
                snapshot_id=snapshot_id,
                stream_id=stream_id,
                created_at_utc=when,
                source_memory_generation=source_memory_generation,
                base_remote_seq=base_remote_seq,
                event_chain_head_sha256=event_chain_head_sha256,
                chunks=tuple(chunks),
                database_identity=database_identity,
            )
            self.backend.commit_snapshot(manifest)
            return MemorySnapshotCreateResult(
                manifest=manifest,
                manifest_sha256=manifest.manifest_sha256(),
                object_count=len(chunks),
                uploaded_bytes=uploaded_bytes,
            )

    def restore_snapshot(
        self,
        manifest: MemorySnapshotManifest,
        *,
        destination_parent: str | Path,
    ) -> MemorySnapshotRestoreResult:
        parent = Path(destination_parent).expanduser().resolve()
        parent.mkdir(parents=True, exist_ok=True)
        staging_root = parent / f"restore-{manifest.snapshot_id[:16]}"
        if staging_root.exists():
            raise FileExistsError(f"restore staging root already exists: {staging_root}")
        staging_root.mkdir(parents=True)
        try:
            grouped: dict[str, list[MemorySnapshotChunk]] = {}
            for chunk in manifest.chunks:
                grouped.setdefault(chunk.logical_path, []).append(chunk)
            restored: list[Path] = []
            integrity: dict[str, str] = {}
            for logical_path, chunks in sorted(grouped.items()):
                safe = Path(logical_path)
                if safe.is_absolute() or ".." in safe.parts:
                    raise MemorySyncContractError("snapshot manifest contains unsafe logical path")
                target = (staging_root / safe).resolve()
                target.relative_to(staging_root)
                target.parent.mkdir(parents=True, exist_ok=True)
                expected_index = 0
                with target.open("xb") as handle:
                    for chunk in sorted(chunks, key=lambda item: item.chunk_index):
                        if chunk.chunk_index != expected_index:
                            raise MemorySyncContractError(
                                f"snapshot chunk sequence gap for {logical_path}: expected {expected_index}, got {chunk.chunk_index}"
                            )
                        encrypted = self.backend.get_object(object_id=chunk.object_id)
                        if hashlib.sha256(encrypted).hexdigest() != chunk.ciphertext_sha256:
                            raise MemorySyncContractError("snapshot object ciphertext hash mismatch")
                        plaintext = self._decrypt_snapshot_chunk(
                            manifest=manifest,
                            chunk=chunk,
                            encrypted=encrypted,
                        )
                        if hashlib.sha256(plaintext).hexdigest() != chunk.plaintext_sha256:
                            raise MemorySyncContractError("snapshot plaintext hash mismatch")
                        if len(plaintext) != chunk.plaintext_size:
                            raise MemorySyncContractError("snapshot plaintext size mismatch")
                        handle.write(plaintext)
                        expected_index += 1
                identity = self._verify_sqlite_file(target)
                expected_identity = manifest.database_identity.get(logical_path)
                if not isinstance(expected_identity, Mapping):
                    raise MemorySyncContractError(f"snapshot identity missing for {logical_path}")
                if identity.get("sha256") != expected_identity.get("sha256"):
                    raise MemorySyncContractError(f"restored SQLite SHA mismatch for {logical_path}")
                integrity[logical_path] = str(identity.get("integrity_check") or "")
                restored.append(target)
            return MemorySnapshotRestoreResult(
                snapshot_id=manifest.snapshot_id,
                staging_root=staging_root,
                restored_paths=tuple(restored),
                integrity=integrity,
                verified=all(value == "ok" for value in integrity.values()),
            )
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise

    @staticmethod
    def promote_verified_restore(result: MemorySnapshotRestoreResult, *, active_memory_root: str | Path) -> Path:
        if not result.verified:
            raise MemorySyncContractError("unverified restore cannot be promoted")
        active = Path(active_memory_root).expanduser().resolve()
        if active.exists():
            raise FileExistsError(
                "active memory root already exists; caller must explicitly move it to a backup generation before promotion"
            )
        os.replace(result.staging_root, active)
        return active

    @staticmethod
    def _online_backup(source: Path, destination: Path) -> None:
        with closing(connect_runtime_readonly(source, timeout_ms=30_000)) as src, closing(
            sqlite3.connect(destination)
        ) as dst:
            src.backup(dst, pages=1024, sleep=0.01)
            dst.commit()

    def _verify_sqlite_file(self, path: Path) -> dict[str, Any]:
        with closing(connect_runtime_readonly(path, timeout_ms=30_000)) as con:
            quick = str(con.execute("PRAGMA quick_check").fetchone()[0])
            integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0]) if self.policy.integrity_check else quick
            foreign_keys = list(con.execute("PRAGMA foreign_key_check"))
            page_count = int(con.execute("PRAGMA page_count").fetchone()[0])
            page_size = int(con.execute("PRAGMA page_size").fetchone()[0])
            user_version = int(con.execute("PRAGMA user_version").fetchone()[0])
        if quick != "ok" or integrity != "ok" or foreign_keys:
            raise MemorySyncContractError(f"SQLite snapshot verification failed for {path.name}")
        digest = hashlib.sha256()
        size_bytes = 0
        with path.open("rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
                size_bytes += len(block)
        return {
            "sha256": digest.hexdigest(),
            "size_bytes": size_bytes,
            "quick_check": quick,
            "integrity_check": integrity,
            "foreign_key_error_count": len(foreign_keys),
            "page_count": page_count,
            "page_size": page_size,
            "user_version": user_version,
        }

    def _snapshot_chunk_aad(
        self,
        *,
        snapshot_id: str,
        stream_id: str,
        logical_path: str,
        chunk_index: int,
        plaintext_sha256: str,
        plaintext_size: int,
        codec: str,
        key_version: int,
    ) -> bytes:
        return canonical_json_bytes(
            {
                "schema_version": "jazn_memory_snapshot_chunk/v1",
                "snapshot_id": snapshot_id,
                "stream_id": stream_id,
                "logical_path": logical_path,
                "chunk_index": chunk_index,
                "plaintext_sha256": plaintext_sha256,
                "plaintext_size": plaintext_size,
                "codec": codec,
                "key_version": key_version,
            }
        )

    def _encrypt_snapshot_chunk(
        self,
        *,
        snapshot_id: str,
        stream_id: str,
        logical_path: str,
        chunk_index: int,
        plaintext: bytes,
        compressed: bytes,
    ) -> tuple[bytes, bytes, int, str]:
        key_version = self.key_provider.active_key_version()
        aad = self._snapshot_chunk_aad(
            snapshot_id=snapshot_id,
            stream_id=stream_id,
            logical_path=logical_path,
            chunk_index=chunk_index,
            plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
            plaintext_size=len(plaintext),
            codec="zlib",
            key_version=key_version,
        )
        encrypted = self.chunk_crypto.encrypt_chunk(
            compressed, aad=aad, key_provider=self.key_provider
        )
        if encrypted.key_version != key_version:
            raise MemorySyncContractError("snapshot crypto provider changed key version during encryption")
        if encrypted.aad_sha256 != hashlib.sha256(aad).hexdigest():
            raise MemorySyncContractError("snapshot crypto provider returned an invalid AAD binding")
        return encrypted.ciphertext, encrypted.nonce, encrypted.key_version, encrypted.aad_sha256

    def _decrypt_snapshot_chunk(
        self,
        *,
        manifest: MemorySnapshotManifest,
        chunk: MemorySnapshotChunk,
        encrypted: bytes,
    ) -> bytes:
        try:
            nonce = base64.b64decode(chunk.nonce_b64.encode("ascii"), validate=True)
        except Exception as exc:
            raise MemorySyncContractError("snapshot nonce is invalid base64") from exc
        aad = self._snapshot_chunk_aad(
            snapshot_id=manifest.snapshot_id,
            stream_id=manifest.stream_id,
            logical_path=chunk.logical_path,
            chunk_index=chunk.chunk_index,
            plaintext_sha256=chunk.plaintext_sha256,
            plaintext_size=chunk.plaintext_size,
            codec=chunk.codec,
            key_version=chunk.key_version,
        )
        if chunk.aad_sha256 and hashlib.sha256(aad).hexdigest() != chunk.aad_sha256:
            raise MemorySyncContractError("snapshot chunk AAD hash mismatch")
        compressed = self.chunk_crypto.decrypt_chunk(
            encrypted,
            nonce=nonce,
            key_version=chunk.key_version,
            aad=aad,
            key_provider=self.key_provider,
        )
        if len(compressed) != chunk.compressed_size:
            raise MemorySyncContractError("snapshot compressed size mismatch")
        try:
            return zlib.decompress(compressed)
        except zlib.error as exc:
            raise MemorySyncContractError("snapshot compressed chunk is corrupt") from exc


__all__ = [
    "MemorySnapshotCreateResult",
    "MemorySnapshotPolicy",
    "MemorySnapshotRestoreResult",
    "SQLiteMemorySnapshotManager",
    "SQLiteSnapshotSource",
]
