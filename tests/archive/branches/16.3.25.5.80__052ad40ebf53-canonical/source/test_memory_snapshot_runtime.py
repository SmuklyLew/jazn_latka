from __future__ import annotations

import hashlib
import sqlite3

import pytest

from latka_jazn.memory.memory_snapshot_runtime import (
    MemorySnapshotPolicy,
    SQLiteMemorySnapshotManager,
    SQLiteSnapshotSource,
)
from latka_jazn.memory.memory_sync_backend import InMemoryMemorySyncBackend
from latka_jazn.memory.memory_sync_contracts import MemorySyncContractError
from latka_jazn.memory.memory_sync_crypto import (
    MemorySnapshotEncryptedChunk,
    StaticMemoryKeyProvider,
)


class DeterministicSnapshotCrypto:
    """Test-only authenticated-shape codec; production uses libsodium provider."""

    def status(self):
        return {"ready": True, "algorithm": "test-only"}

    def encrypt_chunk(self, plaintext: bytes, *, aad: bytes, key_provider):
        version = key_provider.active_key_version()
        key = key_provider.key_for_version(version)
        nonce = hashlib.sha256(aad + plaintext).digest()[:24]
        tag = hashlib.sha256(key + aad + plaintext).digest()
        return MemorySnapshotEncryptedChunk(
            ciphertext=tag + plaintext,
            nonce=nonce,
            key_version=version,
            aad_sha256=hashlib.sha256(aad).hexdigest(),
        )

    def decrypt_chunk(self, ciphertext: bytes, *, nonce: bytes, key_version: int, aad: bytes, key_provider):
        del nonce
        key = key_provider.key_for_version(key_version)
        if len(ciphertext) < 32:
            raise MemorySyncContractError("test snapshot ciphertext truncated")
        tag, plaintext = ciphertext[:32], ciphertext[32:]
        if tag != hashlib.sha256(key + aad + plaintext).digest():
            raise MemorySyncContractError("test snapshot authentication failed")
        return plaintext


def _create_db(path, *, rows: int = 2500) -> None:
    with sqlite3.connect(path) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        con.executemany(
            "INSERT INTO items(payload) VALUES(?)",
            [(f"row-{idx}-" + ("x" * 120),) for idx in range(rows)],
        )
        con.commit()


def _manager(backend, *, key: bytes = b"s" * 32):
    return SQLiteMemorySnapshotManager(
        backend=backend,
        key_provider=StaticMemoryKeyProvider({1: key}, active_version=1),
        policy=MemorySnapshotPolicy(chunk_plaintext_bytes=64 * 1024, zlib_level=6),
        chunk_crypto=DeterministicSnapshotCrypto(),
    )


def test_online_backup_snapshot_restore_is_chunked_verified_and_exact(tmp_path) -> None:
    source = tmp_path / "active.sqlite3"
    _create_db(source)
    backend = InMemoryMemorySyncBackend()
    manager = _manager(backend)
    created = manager.create_snapshot(
        stream_id="stream-1",
        sources=(SQLiteSnapshotSource("sqlite/runtime_memory.sqlite3", source),),
        source_memory_generation="generation-7",
        base_remote_seq=42,
        event_chain_head_sha256="a" * 64,
    )
    assert created.object_count > 1
    assert created.manifest.base_remote_seq == 42
    assert created.manifest.source_memory_generation == "generation-7"
    latest = backend.latest_snapshot(stream_id="stream-1")
    assert latest is not None
    assert latest.manifest_sha256() == created.manifest_sha256

    restored = manager.restore_snapshot(created.manifest, destination_parent=tmp_path / "restore")
    assert restored.verified is True
    assert len(restored.restored_paths) == 1
    with sqlite3.connect(restored.restored_paths[0]) as con:
        assert int(con.execute("SELECT COUNT(*) FROM items").fetchone()[0]) == 2500
    expected_identity = created.manifest.database_identity["sqlite/runtime_memory.sqlite3"]
    assert expected_identity["sha256"] == hashlib.sha256(restored.restored_paths[0].read_bytes()).hexdigest()


def test_restore_rejects_corrupt_cloud_object_before_sqlite_promotion(tmp_path) -> None:
    source = tmp_path / "active.sqlite3"
    _create_db(source, rows=1000)
    backend = InMemoryMemorySyncBackend()
    manager = _manager(backend)
    created = manager.create_snapshot(
        stream_id="stream-1",
        sources=(SQLiteSnapshotSource("runtime.sqlite3", source),),
        source_memory_generation="g1",
        base_remote_seq=0,
    )
    first = created.manifest.chunks[0]
    backend._objects[first.object_id] = b"tampered"  # deterministic fault injection backend
    with pytest.raises(MemorySyncContractError, match="ciphertext hash mismatch"):
        manager.restore_snapshot(created.manifest, destination_parent=tmp_path / "restore")
    assert not any((tmp_path / "restore").glob("restore-*"))


def test_restore_with_wrong_key_fails_authentication(tmp_path) -> None:
    source = tmp_path / "active.sqlite3"
    _create_db(source, rows=1000)
    backend = InMemoryMemorySyncBackend()
    created = _manager(backend, key=b"a" * 32).create_snapshot(
        stream_id="stream-1",
        sources=(SQLiteSnapshotSource("runtime.sqlite3", source),),
        source_memory_generation="g1",
        base_remote_seq=0,
    )
    with pytest.raises(MemorySyncContractError, match="authentication failed"):
        _manager(backend, key=b"b" * 32).restore_snapshot(
            created.manifest, destination_parent=tmp_path / "restore"
        )


def test_promote_requires_verified_restore_and_empty_target(tmp_path) -> None:
    source = tmp_path / "active.sqlite3"
    _create_db(source, rows=100)
    backend = InMemoryMemorySyncBackend()
    manager = _manager(backend)
    created = manager.create_snapshot(
        stream_id="stream-1",
        sources=(SQLiteSnapshotSource("runtime.sqlite3", source),),
        source_memory_generation="g1",
        base_remote_seq=0,
    )
    restored = manager.restore_snapshot(created.manifest, destination_parent=tmp_path / "restore")
    existing = tmp_path / "active-memory"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="active memory root already exists"):
        manager.promote_verified_restore(restored, active_memory_root=existing)
    empty_target = tmp_path / "new-active-memory"
    promoted = manager.promote_verified_restore(restored, active_memory_root=empty_target)
    assert promoted == empty_target.resolve()
    assert (promoted / "runtime.sqlite3").is_file()


def test_production_snapshot_crypto_round_trip_when_dependency_available(tmp_path) -> None:
    pytest.importorskip("nacl")
    from latka_jazn.memory.memory_sync_crypto import PyNaClMemorySnapshotChunkCrypto

    source = tmp_path / "active.sqlite3"
    _create_db(source, rows=500)
    backend = InMemoryMemorySyncBackend()
    manager = SQLiteMemorySnapshotManager(
        backend=backend,
        key_provider=StaticMemoryKeyProvider({2: b"z" * 32}, active_version=2),
        policy=MemorySnapshotPolicy(chunk_plaintext_bytes=64 * 1024),
        chunk_crypto=PyNaClMemorySnapshotChunkCrypto(),
    )
    created = manager.create_snapshot(
        stream_id="secure-stream",
        sources=(SQLiteSnapshotSource("runtime.sqlite3", source),),
        source_memory_generation="secure-g1",
        base_remote_seq=7,
    )
    restored = manager.restore_snapshot(created.manifest, destination_parent=tmp_path / "secure-restore")
    assert restored.verified is True
