from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import json
import random

import pytest

from latka_jazn.memory.memory_sync_backend import InMemoryMemorySyncBackend, MemorySyncBackendError
from latka_jazn.memory.memory_sync_contracts import MemorySyncEvent, MemorySyncMode, MemorySyncPlainEvent, canonical_json_bytes
from latka_jazn.memory.memory_sync_crypto import StaticMemoryKeyProvider
from latka_jazn.memory.memory_sync_worker import CloudMemorySyncWorker, MemorySyncWorkerConfig
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import (
    MemoryKind,
    MemoryTier,
    MemoryTruthStatus,
    ShortTermMemoryPolicy,
    SourceEvidence,
    WorkingMemoryRecord,
    deterministic_memory_id,
)

BASE = datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc)


class DeterministicTestCrypto:
    """Non-secret deterministic test codec for protocol/transaction tests only."""

    def status(self) -> dict[str, object]:
        return {"ready": True, "algorithm": "test-only"}

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
            nonce_b64=base64.b64encode(b"test-nonce").decode("ascii"),
            aad_sha256=hashlib.sha256(aad).hexdigest(),
            created_at_utc=plain.created_at_utc,
            parent_event_id=plain.parent_event_id,
            turn_id=plain.turn_id,
            thought_id=plain.thought_id,
            previous_device_event_sha256=plain.previous_device_event_sha256,
        )

    def decrypt_event(self, event, *, key_provider):
        key_provider.key_for_version(event.key_version)
        value = json.loads(event.ciphertext_bytes().decode("utf-8"))
        assert isinstance(value, dict)
        return value


class LostAckBackend(InMemoryMemorySyncBackend):
    """Commits the first push remotely, then simulates a lost HTTP response."""

    def __init__(self) -> None:
        super().__init__()
        self.lose_first_ack = True

    def push_events(self, batch):
        receipts = super().push_events(batch)
        if self.lose_first_ack:
            self.lose_first_ack = False
            raise MemorySyncBackendError("simulated_ack_lost_after_remote_commit")
        return receipts


def _evidence(source_id: str) -> SourceEvidence:
    return SourceEvidence(
        source_type="runtime_turn",
        source_id=source_id,
        source_sha256="a" * 64,
        conversation_id="session-1",
        node_ids=(source_id,),
        exact_excerpt_sha256="b" * 64,
        timestamp_status="exact",
    )


def _record_pair(content: str = "Pamięć synchronizowana"):
    evidence = _evidence("turn-1")
    working_id = deterministic_memory_id(
        tier=MemoryTier.WORKING,
        kind=MemoryKind.CONVERSATION_CONTEXT,
        content=content,
        domain="development",
        mode="runtime_turn",
        evidence=(evidence,),
    )
    working = WorkingMemoryRecord(
        memory_id=working_id,
        tier=MemoryTier.WORKING,
        kind=MemoryKind.CONVERSATION_CONTEXT,
        content=content,
        content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        domain="development",
        mode="runtime_turn",
        truth_status=MemoryTruthStatus.SOURCE_RECORDED,
        confidence=0.9,
        importance=0.8,
        created_at_utc=BASE,
        updated_at_utc=BASE,
        evidence=(evidence,),
        session_id="session-1",
        turn_id="turn-1",
        active_goal="local-first",
    )
    short = ShortTermMemoryPolicy().create(
        kind=MemoryKind.EPISODIC,
        content=content,
        domain="development",
        mode="runtime_turn",
        truth_status=MemoryTruthStatus.SOURCE_RECORDED,
        confidence=0.9,
        importance=0.8,
        evidence=(evidence,),
        created_at_utc=BASE,
    )
    return working, short


def _stage_runtime_event(store: MemoryTierStore, content: str = "Pamięć synchronizowana") -> tuple[str, str]:
    working, short = _record_pair(content)
    with store.transaction():
        store.write_record(working)
        store.write_record(short)
        event_id = store.write_outbox(
            event_type="memory.runtime_turn_staged",
            aggregate_id=short.memory_id,
            payload={
                "working_memory_id": working.memory_id,
                "short_term_memory_id": short.memory_id,
                "session_id": working.session_id,
                "turn_id": working.turn_id,
                "automatic_l3": False,
                "record_payload_version": 1,
                "records": [working.to_dict(), short.to_dict()],
            },
            idempotency_key=f"runtime-turn:{short.memory_id}",
            available_at_utc=BASE,
        )
    return event_id, short.memory_id


def _worker(path, backend, *, mode=MemorySyncMode.BACKUP, device="device-a"):
    return CloudMemorySyncWorker(
        store_path=str(path),
        backend=backend,
        crypto=DeterministicTestCrypto(),
        key_provider=StaticMemoryKeyProvider({1: b"k" * 32}, active_version=1),
        config=MemorySyncWorkerConfig(
            stream_id="stream-1",
            device_id=device,
            mode=mode,
            retry_base_seconds=0.25,
            retry_max_seconds=1.0,
            retry_jitter_fraction=0.0,
        ),
        random_source=random.Random(7),
    )


def test_schema_exposes_sync_ledgers_without_changing_local_store_truth(tmp_path) -> None:
    with MemoryTierStore(tmp_path / "memory.sqlite3") as store:
        stats = store.stats()
        assert stats["memory_sync_state"] == 0
        assert stats["memory_sync_envelopes"] == 0
        assert stats["memory_sync_receipts"] == 0
        assert stats["memory_sync_inbox"] == 0
        assert stats["memory_sync_conflicts"] == 0
        assert store.validate()["ok"] is True


def test_backup_push_is_idempotent_and_receipt_completes_outbox(tmp_path) -> None:
    path = tmp_path / "source.sqlite3"
    backend = InMemoryMemorySyncBackend()
    with MemoryTierStore(path) as store:
        event_id, _ = _stage_runtime_event(store)
    result = _worker(path, backend).sync_once()
    assert result.push_claimed == 1
    assert result.push_accepted == 1
    assert result.push_failed == 0
    with MemoryTierStore(path) as store:
        row = store.con.execute("SELECT status FROM memory_outbox WHERE event_id=?", (event_id,)).fetchone()
        assert str(row["status"]) == "processed"
        assert store.stats()["memory_sync_receipts"] == 1
        assert store.stats()["memory_sync_envelopes"] == 1
    assert backend.status(stream_id="stream-1").remote_seq == 1


def test_lost_ack_reuses_exact_envelope_and_remote_accepts_retry_as_duplicate(tmp_path) -> None:
    path = tmp_path / "source.sqlite3"
    backend = LostAckBackend()
    with MemoryTierStore(path) as store:
        event_id, _ = _stage_runtime_event(store)
    first = _worker(path, backend).sync_once()
    assert first.push_failed == 1
    assert backend.status(stream_id="stream-1").remote_seq == 1
    with MemoryTierStore(path) as store:
        envelope_before = store.get_sync_envelope(event_id)
        assert envelope_before is not None
        before_hash = envelope_before.ciphertext_sha256
        store.con.execute(
            "UPDATE memory_outbox SET available_at_utc=? WHERE event_id=?",
            (BASE.isoformat(), event_id),
        )
    second = _worker(path, backend).sync_once()
    assert second.push_replayed == 1
    assert second.push_failed == 0
    assert backend.status(stream_id="stream-1").remote_seq == 1
    with MemoryTierStore(path) as store:
        envelope_after = store.get_sync_envelope(event_id)
        assert envelope_after is not None
        assert envelope_after.ciphertext_sha256 == before_hash
        assert store.con.execute("SELECT status FROM memory_outbox WHERE event_id=?", (event_id,)).fetchone()[0] == "processed"


def test_push_pull_materializes_remote_records_through_domain_store_without_echo_outbox(tmp_path) -> None:
    backend = InMemoryMemorySyncBackend()
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "target.sqlite3"
    with MemoryTierStore(source) as store:
        _, short_id = _stage_runtime_event(store, "Odtwarzalna pamięć")
    assert _worker(source, backend).sync_once().push_accepted == 1

    result = _worker(target, backend, mode=MemorySyncMode.PUSH_PULL, device="device-b").sync_once()
    assert result.pull_received == 1
    assert result.pull_applied == 1
    assert result.pull_conflicts == 0
    assert result.cursor_after == 1
    with MemoryTierStore(target) as store:
        assert store.get_record(short_id) is not None
        assert store.stats()["memory_records"] == 2
        assert store.stats()["memory_outbox"] == 0
        assert store.stats()["memory_sync_inbox"] == 1
        assert store.sync_cursor() is not None
        assert store.sync_cursor().remote_seq == 1


def test_same_remote_sequence_with_different_event_is_explicit_conflict(tmp_path) -> None:
    backend = InMemoryMemorySyncBackend()
    source = tmp_path / "source.sqlite3"
    with MemoryTierStore(source) as store:
        _stage_runtime_event(store)
    assert _worker(source, backend).sync_once().push_accepted == 1
    remote_seq, event = backend.pull_events(stream_id="stream-1", after_remote_seq=0)[0]

    target = tmp_path / "target.sqlite3"
    with MemoryTierStore(target) as store:
        store.configure_sync_identity(stream_id="stream-1", device_id="device-b")
        assert store.store_inbox_event(remote_seq=remote_seq, event=event).value == "pending"
        altered_plain = MemorySyncPlainEvent(
            stream_id=event.stream_id,
            event_id="different-event",
            idempotency_key="different-key",
            device_id=event.device_id,
            device_seq=event.device_seq + 1,
            event_type=event.event_type,
            aggregate_id=event.aggregate_id,
            aggregate_revision=event.aggregate_revision,
            payload={"different": True},
            created_at_utc=event.created_at_utc,
        )
        altered = DeterministicTestCrypto().encrypt_event(
            altered_plain, key_provider=StaticMemoryKeyProvider({1: b"k" * 32}, active_version=1)
        )
        status = store.store_inbox_event(remote_seq=remote_seq, event=altered)
        assert status.value == "conflict"
        assert store.stats()["memory_sync_conflicts"] == 1


def test_real_xchacha_event_round_trip_when_optional_dependency_available() -> None:
    pytest.importorskip("nacl")
    from latka_jazn.memory.memory_sync_crypto import PyNaClXChaCha20Poly1305Provider

    provider = PyNaClXChaCha20Poly1305Provider()
    keyring = StaticMemoryKeyProvider({3: b"x" * 32}, active_version=3)
    plain = MemorySyncPlainEvent(
        stream_id="stream",
        event_id="event",
        idempotency_key="idem",
        device_id="device",
        device_seq=1,
        event_type="memory.test",
        aggregate_id="aggregate",
        aggregate_revision=1,
        payload={"private": "zażółć gęślą jaźń"},
        created_at_utc=BASE,
    )
    event = provider.encrypt_event(plain, key_provider=keyring)
    assert "zażółć" not in event.ciphertext_b64
    assert provider.decrypt_event(event, key_provider=keyring) == dict(plain.payload)
