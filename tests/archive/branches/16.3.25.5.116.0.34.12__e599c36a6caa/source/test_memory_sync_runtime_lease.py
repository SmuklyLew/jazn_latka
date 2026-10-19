from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import json

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_sync_backend import InMemoryMemorySyncBackend
from latka_jazn.memory.memory_sync_contracts import MemorySyncEvent, MemorySyncMode, canonical_json_bytes
from latka_jazn.memory.memory_sync_crypto import StaticMemoryKeyProvider
from latka_jazn.memory.memory_sync_runtime import MemorySyncRuntime
from latka_jazn.memory.memory_tier_store import MemoryTierStore


class _DeterministicCrypto:
    def status(self):
        return {"ready": True}

    def encrypt_event(self, plain, *, key_provider):
        key_version = key_provider.active_key_version()
        ciphertext = canonical_json_bytes(plain.payload)
        aad = canonical_json_bytes(plain.aad(key_version=key_version))
        return MemorySyncEvent(
            stream_id=plain.stream_id,
            event_id=plain.event_id,
            idempotency_key=plain.idempotency_key,
            device_id=plain.device_id,
            device_seq=plain.device_seq,
            event_type=plain.event_type,
            aggregate_id=plain.aggregate_id,
            aggregate_revision=plain.aggregate_revision,
            payload_codec="json",
            ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
            ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            key_version=key_version,
            nonce_b64=base64.b64encode(b"nonce").decode("ascii"),
            aad_sha256=hashlib.sha256(aad).hexdigest(),
            created_at_utc=plain.created_at_utc,
            parent_event_id=plain.parent_event_id,
            turn_id=plain.turn_id,
            thought_id=plain.thought_id,
            previous_device_event_sha256=plain.previous_device_event_sha256,
        )

    def decrypt_event(self, event, *, key_provider):
        key_provider.key_for_version(event.key_version)
        value = json.loads(event.ciphertext_bytes())
        assert isinstance(value, dict)
        return value


class _LeaseRecordingBackend(InMemoryMemorySyncBackend):
    def __init__(self) -> None:
        super().__init__()
        self.acquired: list[tuple[str, str, str, int]] = []

    def acquire_writer_lease(self, *, stream_id, device_id, lease_token, ttl_seconds=120):
        self.acquired.append((stream_id, device_id, lease_token, ttl_seconds))
        return super().acquire_writer_lease(
            stream_id=stream_id, device_id=device_id, lease_token=lease_token, ttl_seconds=ttl_seconds
        )


def _runtime(tmp_path, monkeypatch, *, mode="push_pull"):
    cfg = JaznConfig(root=tmp_path)
    cfg.memory_sync_mode = mode
    cfg.memory_sync_endpoint = "https://memory.invalid"
    cfg.memory_sync_stream_id = "stream-a"
    cfg.memory_sync_device_id = "device-a"
    cfg.memory_sync_bearer_token_env = "TEST_MEMORY_BEARER"
    cfg.memory_sync_writer_lease_enabled = True
    cfg.memory_sync_writer_lease_token_env = "TEST_MEMORY_LEASE"
    cfg.memory_sync_writer_lease_ttl_seconds = 177
    monkeypatch.setenv("TEST_MEMORY_BEARER", "bearer-secret")
    monkeypatch.setenv("TEST_MEMORY_LEASE", "l" * 48)
    runtime = MemorySyncRuntime(cfg)
    backend = _LeaseRecordingBackend()
    runtime.build_backend = lambda: backend  # type: ignore[method-assign]
    runtime.build_key_provider = lambda: StaticMemoryKeyProvider({1: b"k" * 32}, active_version=1)  # type: ignore[method-assign]
    runtime.build_event_crypto = lambda: _DeterministicCrypto()  # type: ignore[method-assign]
    return runtime, backend


def test_push_pull_requires_writer_lease_secret_by_default(tmp_path, monkeypatch) -> None:
    cfg = JaznConfig(root=tmp_path)
    cfg.memory_sync_mode = "push_pull"
    cfg.memory_sync_endpoint = "https://memory.invalid"
    cfg.memory_sync_stream_id = "stream-a"
    cfg.memory_sync_device_id = "device-a"
    cfg.memory_sync_bearer_token_env = "TEST_MEMORY_BEARER"
    cfg.memory_sync_writer_lease_enabled = True
    cfg.memory_sync_writer_lease_token_env = "TEST_MEMORY_LEASE"
    monkeypatch.setenv("TEST_MEMORY_BEARER", "bearer-secret")
    monkeypatch.delenv("TEST_MEMORY_LEASE", raising=False)
    runtime = MemorySyncRuntime(cfg)
    assert "secret_env:TEST_MEMORY_LEASE" in runtime.runtime.missing_requirements()
    public = runtime.runtime.public_dict()
    assert public["writer_lease_required"] is True
    assert public["writer_lease_token_present"] is False


def test_push_pull_acquires_writer_lease_before_worker(tmp_path, monkeypatch) -> None:
    runtime, backend = _runtime(tmp_path, monkeypatch)
    with MemoryTierStore(runtime.store_path):
        pass
    result = runtime.sync_once()
    assert result.error is None
    assert backend.acquired == [("stream-a", "device-a", "l" * 48, 177)]


def test_backup_mode_does_not_require_writer_lease(tmp_path, monkeypatch) -> None:
    runtime, backend = _runtime(tmp_path, monkeypatch, mode="backup")
    monkeypatch.delenv("TEST_MEMORY_LEASE", raising=False)
    # The runtime config was constructed while the secret existed; requirement is mode-dependent at use time.
    assert runtime.runtime.writer_lease_required is False
    with MemoryTierStore(runtime.store_path):
        pass
    runtime.sync_once()
    assert backend.acquired == []
