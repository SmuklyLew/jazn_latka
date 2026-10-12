from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import json
import math
import random

from latka_jazn.memory.memory_sync_backend import MemorySyncBackend, MemorySyncBackendError
from latka_jazn.memory.memory_sync_contracts import (
    MemoryInboxStatus,
    MemorySyncBatch,
    MemorySyncContractError,
    MemorySyncMode,
    MemorySyncPlainEvent,
    MemorySyncReceiptStatus,
    parse_utc,
)
from latka_jazn.memory.memory_sync_crypto import MemoryCryptoProvider, MemoryKeyProvider
from latka_jazn.memory.memory_sync_materializer import MemorySyncEventMaterializer
from latka_jazn.memory.memory_tier_store import MemoryTierStore


@dataclass(slots=True, frozen=True)
class MemorySyncWorkerConfig:
    stream_id: str
    device_id: str
    mode: MemorySyncMode = MemorySyncMode.BACKUP
    push_batch_size: int = 50
    pull_batch_size: int = 100
    max_batch_wire_bytes: int = 2_000_000
    stale_claim_seconds: int = 300
    retry_base_seconds: float = 2.0
    retry_max_seconds: float = 300.0
    retry_jitter_fraction: float = 0.2

    def __post_init__(self) -> None:
        if not self.stream_id.strip() or not self.device_id.strip():
            raise MemorySyncContractError("stream_id and device_id are required")
        if min(self.push_batch_size, self.pull_batch_size, self.max_batch_wire_bytes, self.stale_claim_seconds) < 1:
            raise MemorySyncContractError("memory sync worker limits must be positive")
        if self.retry_base_seconds <= 0 or self.retry_max_seconds < self.retry_base_seconds:
            raise MemorySyncContractError("invalid retry backoff configuration")
        if not 0.0 <= self.retry_jitter_fraction <= 1.0:
            raise MemorySyncContractError("retry_jitter_fraction must be between 0 and 1")


@dataclass(slots=True, frozen=True)
class MemorySyncWorkerResult:
    push_claimed: int = 0
    push_accepted: int = 0
    push_replayed: int = 0
    push_failed: int = 0
    pull_received: int = 0
    pull_applied: int = 0
    pull_conflicts: int = 0
    stale_claims_requeued: int = 0
    cursor_before: int = 0
    cursor_after: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "push_claimed": self.push_claimed,
            "push_accepted": self.push_accepted,
            "push_replayed": self.push_replayed,
            "push_failed": self.push_failed,
            "pull_received": self.pull_received,
            "pull_applied": self.pull_applied,
            "pull_conflicts": self.pull_conflicts,
            "stale_claims_requeued": self.stale_claims_requeued,
            "cursor_before": self.cursor_before,
            "cursor_after": self.cursor_after,
            "error": self.error,
        }


def _cursor_remote_seq(store: MemoryTierStore, *, fallback: int) -> int:
    """Read one coherent sync-cursor snapshot without repeated Optional dereferences."""
    cursor = store.sync_cursor()
    return cursor.remote_seq if cursor is not None else int(fallback)


class CloudMemorySyncWorker:
    """Bounded local-first replication worker.

    The worker is deliberately synchronous and side-effect explicit: callers decide
    when to run ``sync_once`` (daemon timer, operator command, shutdown drain, test).
    No hidden background thread can outlive the runtime. Local memory commits never
    wait for this worker and a cloud outage cannot change local runtime readiness.
    """

    def __init__(
        self,
        *,
        store_path: str,
        backend: MemorySyncBackend,
        crypto: MemoryCryptoProvider,
        key_provider: MemoryKeyProvider,
        config: MemorySyncWorkerConfig,
        random_source: random.Random | None = None,
    ) -> None:
        self.store_path = store_path
        self.backend = backend
        self.crypto = crypto
        self.key_provider = key_provider
        self.config = config
        self._random = random_source or random.SystemRandom()

    def sync_once(self) -> MemorySyncWorkerResult:
        if self.config.mode is MemorySyncMode.OFF:
            return MemorySyncWorkerResult()
        with MemoryTierStore(self.store_path) as store:
            store.configure_sync_identity(stream_id=self.config.stream_id, device_id=self.config.device_id)
            stale = store.requeue_stale_outbox(stale_after_seconds=self.config.stale_claim_seconds)
            cursor = store.sync_cursor()
            before = cursor.remote_seq if cursor else 0
            result = self._push(store, stale_claims_requeued=stale, cursor_before=before)
            if result.error is not None:
                return result
            if self.config.mode is MemorySyncMode.PUSH_PULL:
                result = self._pull(store, result)
            cursor_after = store.sync_cursor()
            return MemorySyncWorkerResult(
                **{**result.to_dict(), "cursor_after": cursor_after.remote_seq if cursor_after else before}
            )

    def _push(
        self,
        store: MemoryTierStore,
        *,
        stale_claims_requeued: int,
        cursor_before: int,
    ) -> MemorySyncWorkerResult:
        rows = store.claim_outbox(limit=self.config.push_batch_size)
        if not rows:
            return MemorySyncWorkerResult(
                stale_claims_requeued=stale_claims_requeued,
                cursor_before=cursor_before,
                cursor_after=cursor_before,
            )
        events = []
        row_by_event_id: dict[str, dict[str, Any]] = {}
        try:
            for row in rows:
                event_id = str(row["event_id"])
                row_by_event_id[event_id] = row
                envelope = store.get_sync_envelope(event_id)
                if envelope is None:
                    reserved = store.reserve_sync_sequence(
                        stream_id=self.config.stream_id, device_id=self.config.device_id
                    )
                    payload = row.get("payload")
                    if not isinstance(payload, dict):
                        raise MemorySyncContractError("outbox payload must be an object")
                    plain = MemorySyncPlainEvent(
                        stream_id=self.config.stream_id,
                        event_id=event_id,
                        idempotency_key=str(row["idempotency_key"]),
                        device_id=self.config.device_id,
                        device_seq=reserved.device_seq,
                        event_type=str(row["event_type"]),
                        aggregate_id=str(row["aggregate_id"]),
                        aggregate_revision=self._aggregate_revision(payload),
                        payload=payload,
                        created_at_utc=parse_utc(str(row["created_at_utc"])),
                        parent_event_id=self._optional_string(payload.get("parent_event_id")),
                        turn_id=self._optional_string(payload.get("turn_id")),
                        thought_id=self._optional_string(payload.get("thought_id")),
                        previous_device_event_sha256=reserved.previous_device_event_sha256,
                    )
                    envelope = self.crypto.encrypt_event(plain, key_provider=self.key_provider)
                    store.save_sync_envelope(envelope)
                events.append(envelope)
            batch = MemorySyncBatch(
                events,
                max_events=self.config.push_batch_size,
                max_wire_bytes=self.config.max_batch_wire_bytes,
            )
            receipts = self.backend.push_events(batch)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            for row in rows:
                store.fail_outbox_with_backoff(
                    str(row["event_id"]),
                    error=message,
                    delay_seconds=self._retry_delay(int(row.get("attempts") or 1)),
                )
            store.record_sync_error(message)
            return MemorySyncWorkerResult(
                push_claimed=len(rows),
                push_failed=len(rows),
                stale_claims_requeued=stale_claims_requeued,
                cursor_before=cursor_before,
                cursor_after=cursor_before,
                error=message,
            )

        receipt_by_event = {receipt.event_id: receipt for receipt in receipts}
        accepted = replayed = failed = 0
        for event in events:
            row = row_by_event_id[event.event_id]
            receipt = receipt_by_event.get(event.event_id)
            if receipt is None:
                failed += 1
                store.fail_outbox_with_backoff(
                    event.event_id,
                    error="gateway_missing_receipt",
                    delay_seconds=self._retry_delay(int(row.get("attempts") or 1)),
                )
                continue
            if (
                receipt.stream_id != event.stream_id
                or receipt.idempotency_key != event.idempotency_key
                or receipt.ciphertext_sha256 != event.ciphertext_sha256
            ):
                failed += 1
                store.fail_outbox_with_backoff(
                    event.event_id,
                    error="gateway_receipt_binding_mismatch",
                    delay_seconds=self._retry_delay(int(row.get("attempts") or 1)),
                )
                continue
            if receipt.status is MemorySyncReceiptStatus.ACCEPTED:
                store.complete_outbox_with_receipt(receipt)
                accepted += 1
            elif receipt.status is MemorySyncReceiptStatus.ALREADY_EXISTS:
                store.complete_outbox_with_receipt(receipt)
                replayed += 1
            else:
                failed += 1
                store.fail_outbox_with_backoff(
                    event.event_id,
                    error=receipt.error_code or "gateway_rejected_event",
                    delay_seconds=self._retry_delay(int(row.get("attempts") or 1)),
                )
        return MemorySyncWorkerResult(
            push_claimed=len(rows),
            push_accepted=accepted,
            push_replayed=replayed,
            push_failed=failed,
            stale_claims_requeued=stale_claims_requeued,
            cursor_before=cursor_before,
            cursor_after=cursor_before,
            error=None if failed == 0 else "one_or_more_events_not_acknowledged",
        )

    def _pull(self, store: MemoryTierStore, prior: MemorySyncWorkerResult) -> MemorySyncWorkerResult:
        cursor = store.sync_cursor()
        before = cursor.remote_seq if cursor else 0
        try:
            remote = self.backend.pull_events(
                stream_id=self.config.stream_id,
                after_remote_seq=before,
                limit=self.config.pull_batch_size,
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            store.record_sync_error(message)
            return MemorySyncWorkerResult(
                **{**prior.to_dict(), "cursor_before": before, "cursor_after": before, "error": message}
            )
        received = 0
        for remote_seq, event in remote:
            status = store.store_inbox_event(remote_seq=remote_seq, event=event)
            if status is MemoryInboxStatus.CONFLICT:
                return MemorySyncWorkerResult(
                    **{
                        **prior.to_dict(),
                        "pull_received": received + 1,
                        "pull_conflicts": prior.pull_conflicts + 1,
                        "cursor_before": before,
                        "cursor_after": _cursor_remote_seq(store, fallback=before),
                        "error": "remote_event_identity_conflict",
                    }
                )
            received += 1

        applied = conflicts = 0
        materializer = MemorySyncEventMaterializer(store)
        for remote_seq, event in store.pending_inbox(limit=self.config.pull_batch_size):
            cursor_now = _cursor_remote_seq(store, fallback=0)
            if remote_seq != cursor_now + 1:
                break
            try:
                payload = self.crypto.decrypt_event(event, key_provider=self.key_provider)
                materializer.apply(event_type=event.event_type, payload=payload)
                store.mark_inbox_applied(remote_seq=remote_seq, event_id=event.event_id)
                applied += 1
            except Exception as exc:
                conflicts += 1
                store.mark_inbox_conflict(
                    remote_seq=remote_seq,
                    event_id=event.event_id,
                    conflict_type="materialization_failed",
                    details={"error_type": type(exc).__name__, "error": str(exc)[:1000]},
                )
                break
        after = _cursor_remote_seq(store, fallback=before)
        return MemorySyncWorkerResult(
            push_claimed=prior.push_claimed,
            push_accepted=prior.push_accepted,
            push_replayed=prior.push_replayed,
            push_failed=prior.push_failed,
            pull_received=received,
            pull_applied=applied,
            pull_conflicts=conflicts,
            stale_claims_requeued=prior.stale_claims_requeued,
            cursor_before=before,
            cursor_after=after,
            error="pull_materialization_conflict" if conflicts else None,
        )

    @staticmethod
    def _aggregate_revision(payload: dict[str, Any]) -> int:
        for key in ("aggregate_revision", "revision"):
            value = payload.get(key)
            if value is not None:
                try:
                    return max(1, int(value))
                except (TypeError, ValueError):
                    pass
        long_term = payload.get("long_term_record")
        if isinstance(long_term, dict) and long_term.get("revision") is not None:
            try:
                return max(1, int(long_term["revision"]))
            except (TypeError, ValueError):
                pass
        return 1

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _retry_delay(self, attempts: int) -> float:
        exponent = max(0, min(int(attempts) - 1, 16))
        base = min(self.config.retry_max_seconds, self.config.retry_base_seconds * math.pow(2.0, exponent))
        jitter = base * self.config.retry_jitter_fraction
        return max(1.0, base + self._random.uniform(-jitter, jitter))


__all__ = ["CloudMemorySyncWorker", "MemorySyncWorkerConfig", "MemorySyncWorkerResult"]
