from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import json

from latka_jazn.memory.memory_sync_contracts import (
    MemoryInboxStatus,
    MemorySyncContractError,
    MemorySyncCursor,
    MemorySyncEvent,
    MemorySyncMode,
    MemorySyncReceipt,
    MemorySyncReceiptStatus,
    MemorySyncStatus,
    canonical_json_bytes,
    parse_utc,
    utc_iso,
)
from latka_jazn.memory.memory_tier_store_contracts import MemoryTierStoreMixinHost


@dataclass(slots=True, frozen=True)
class ReservedSyncSequence:
    stream_id: str
    device_id: str
    device_seq: int
    previous_device_event_sha256: str | None


class MemorySyncStoreMixin(MemoryTierStoreMixinHost):
    """Transactional local ledger for cloud synchronization.

    All methods preserve the local-first boundary: domain writes and outbox staging are
    authoritative locally; cloud receipts only describe replication. The mixin never
    performs network I/O and never treats cloud readiness as local memory readiness.
    """

    def configure_sync_identity(self, *, stream_id: str, device_id: str) -> None:
        if not stream_id.strip() or not device_id.strip():
            raise MemorySyncContractError("stream_id and device_id are required")
        with self.transaction():
            existing = self.con.execute(
                "SELECT stream_id,device_id FROM memory_sync_state WHERE state_id=1"
            ).fetchone()
            if existing is not None:
                if str(existing["stream_id"]) != stream_id or str(existing["device_id"]) != device_id:
                    raise MemorySyncContractError(
                        "memory sync identity is immutable for an initialized store; use an explicit migration/restore"
                    )
                return
            self.con.execute(
                """INSERT INTO memory_sync_state(
                   state_id,stream_id,device_id,next_device_seq,local_cursor,updated_at_utc)
                   VALUES(1,?,?,1,0,?)""",
                (stream_id, device_id, utc_iso(datetime.now(timezone.utc))),
            )

    def sync_identity(self) -> tuple[str, str] | None:
        row = self.con.execute(
            "SELECT stream_id,device_id FROM memory_sync_state WHERE state_id=1"
        ).fetchone()
        if row is None:
            return None
        return str(row["stream_id"]), str(row["device_id"])

    def reserve_sync_sequence(self, *, stream_id: str, device_id: str) -> ReservedSyncSequence:
        with self.transaction():
            row = self.con.execute("SELECT * FROM memory_sync_state WHERE state_id=1").fetchone()
            if row is None:
                self.con.execute(
                    """INSERT INTO memory_sync_state(
                       state_id,stream_id,device_id,next_device_seq,local_cursor,updated_at_utc)
                       VALUES(1,?,?,2,0,?)""",
                    (stream_id, device_id, utc_iso(datetime.now(timezone.utc))),
                )
                return ReservedSyncSequence(stream_id, device_id, 1, None)
            if str(row["stream_id"]) != stream_id or str(row["device_id"]) != device_id:
                raise MemorySyncContractError("sync stream/device does not match initialized memory store")
            seq = int(row["next_device_seq"])
            previous = str(row["device_chain_head_sha256"]) if row["device_chain_head_sha256"] else None
            self.con.execute(
                "UPDATE memory_sync_state SET next_device_seq=?,updated_at_utc=? WHERE state_id=1",
                (seq + 1, utc_iso(datetime.now(timezone.utc))),
            )
            return ReservedSyncSequence(stream_id, device_id, seq, previous)

    def save_sync_envelope(self, event: MemorySyncEvent) -> None:
        envelope_json = json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        envelope_sha256 = hashlib.sha256(envelope_json.encode("utf-8")).hexdigest()
        with self.transaction():
            existing = self.con.execute(
                "SELECT envelope_sha256,envelope_json FROM memory_sync_envelopes WHERE event_id=?",
                (event.event_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["envelope_sha256"]) != envelope_sha256:
                    raise MemorySyncContractError("event_id already has a different encrypted envelope")
                return
            state = self.con.execute("SELECT stream_id,device_id FROM memory_sync_state WHERE state_id=1").fetchone()
            if state is None:
                raise MemorySyncContractError("sync identity must be initialized before saving an envelope")
            if str(state["stream_id"]) != event.stream_id or str(state["device_id"]) != event.device_id:
                raise MemorySyncContractError("encrypted envelope identity does not match memory store")
            self.con.execute(
                """INSERT INTO memory_sync_envelopes(
                   event_id,stream_id,device_id,device_seq,idempotency_key,ciphertext_sha256,
                   envelope_sha256,envelope_json,created_at_utc)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    event.event_id, event.stream_id, event.device_id, event.device_seq,
                    event.idempotency_key, event.ciphertext_sha256, envelope_sha256,
                    envelope_json, utc_iso(event.created_at_utc),
                ),
            )
            self.con.execute(
                """UPDATE memory_sync_state SET device_chain_head_sha256=?,updated_at_utc=?
                   WHERE state_id=1""",
                (envelope_sha256, utc_iso(datetime.now(timezone.utc))),
            )

    def get_sync_envelope(self, event_id: str) -> MemorySyncEvent | None:
        row = self.con.execute(
            "SELECT envelope_json FROM memory_sync_envelopes WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row["envelope_json"]))
        if not isinstance(value, dict):
            raise MemorySyncContractError("stored sync envelope is not an object")
        return MemorySyncEvent.from_dict(value)

    def complete_outbox_with_receipt(self, receipt: MemorySyncReceipt) -> None:
        if receipt.status not in {MemorySyncReceiptStatus.ACCEPTED, MemorySyncReceiptStatus.ALREADY_EXISTS}:
            raise MemorySyncContractError("rejected receipt cannot complete an outbox event")
        with self.transaction():
            envelope = self.con.execute(
                """SELECT idempotency_key,ciphertext_sha256 FROM memory_sync_envelopes
                   WHERE event_id=?""", (receipt.event_id,),
            ).fetchone()
            if envelope is None:
                raise MemorySyncContractError("receipt references an event without a local encrypted envelope")
            if str(envelope["idempotency_key"]) != receipt.idempotency_key:
                raise MemorySyncContractError("receipt idempotency_key does not match local envelope")
            if str(envelope["ciphertext_sha256"]) != receipt.ciphertext_sha256:
                raise MemorySyncContractError("receipt ciphertext hash does not match local envelope")
            self.con.execute(
                """INSERT INTO memory_sync_receipts(
                   event_id,stream_id,idempotency_key,status,remote_seq,ciphertext_sha256,
                   received_at_utc,receipt_sha256,error_code,receipt_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(event_id) DO UPDATE SET
                   status=excluded.status,remote_seq=excluded.remote_seq,
                   received_at_utc=excluded.received_at_utc,receipt_sha256=excluded.receipt_sha256,
                   error_code=excluded.error_code,receipt_json=excluded.receipt_json""",
                (
                    receipt.event_id, receipt.stream_id, receipt.idempotency_key,
                    receipt.status.value, receipt.remote_seq, receipt.ciphertext_sha256,
                    utc_iso(receipt.received_at_utc), receipt.receipt_sha256, receipt.error_code,
                    json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ),
            )
            cursor = self.con.execute(
                """UPDATE memory_outbox SET status='processed',processed_at_utc=?,last_error=NULL
                   WHERE event_id=? AND status IN ('pending','processing','failed')""",
                (utc_iso(datetime.now(timezone.utc)), receipt.event_id),
            )
            if cursor.rowcount != 1:
                existing = self.con.execute(
                    "SELECT status FROM memory_outbox WHERE event_id=?", (receipt.event_id,)
                ).fetchone()
                if existing is None:
                    raise MemorySyncContractError("receipt did not match an outbox event")
                if str(existing["status"]) != "processed":
                    raise MemorySyncContractError("receipt could not complete the outbox event")
            self.con.execute(
                """UPDATE memory_sync_state SET last_push_at_utc=?,last_error=NULL,updated_at_utc=?
                   WHERE state_id=1""",
                (
                    utc_iso(datetime.now(timezone.utc)),
                    utc_iso(datetime.now(timezone.utc)),
                ),
            )

    def store_inbox_event(self, *, remote_seq: int, event: MemorySyncEvent) -> MemoryInboxStatus:
        if remote_seq < 1:
            raise MemorySyncContractError("remote_seq must be positive")
        event_json = json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.transaction():
            identity = self.con.execute("SELECT stream_id FROM memory_sync_state WHERE state_id=1").fetchone()
            if identity is None or str(identity["stream_id"]) != event.stream_id:
                raise MemorySyncContractError("inbox event belongs to another memory stream")
            by_seq = self.con.execute(
                "SELECT event_id,ciphertext_sha256,status FROM memory_sync_inbox WHERE remote_seq=?",
                (remote_seq,),
            ).fetchone()
            if by_seq is not None:
                if str(by_seq["event_id"]) != event.event_id or str(by_seq["ciphertext_sha256"]) != event.ciphertext_sha256:
                    self._record_conflict_in_transaction(
                        conflict_type="remote_seq_collision",
                        event_id=event.event_id,
                        remote_seq=remote_seq,
                        details={"existing_event_id": str(by_seq["event_id"])},
                    )
                    return MemoryInboxStatus.CONFLICT
                return MemoryInboxStatus(str(by_seq["status"]))
            by_event = self.con.execute(
                "SELECT remote_seq,ciphertext_sha256,status FROM memory_sync_inbox WHERE event_id=?",
                (event.event_id,),
            ).fetchone()
            if by_event is not None:
                if int(by_event["remote_seq"]) != remote_seq or str(by_event["ciphertext_sha256"]) != event.ciphertext_sha256:
                    self._record_conflict_in_transaction(
                        conflict_type="event_identity_collision",
                        event_id=event.event_id,
                        remote_seq=remote_seq,
                        details={"existing_remote_seq": int(by_event["remote_seq"])},
                    )
                    return MemoryInboxStatus.CONFLICT
                return MemoryInboxStatus(str(by_event["status"]))
            self.con.execute(
                """INSERT INTO memory_sync_inbox(
                   remote_seq,event_id,stream_id,ciphertext_sha256,event_json,status,received_at_utc)
                   VALUES(?,?,?,?,?,'pending',?)""",
                (
                    remote_seq, event.event_id, event.stream_id, event.ciphertext_sha256,
                    event_json, utc_iso(datetime.now(timezone.utc)),
                ),
            )
            return MemoryInboxStatus.PENDING

    def pending_inbox(self, *, limit: int = 100) -> list[tuple[int, MemorySyncEvent]]:
        rows = self.con.execute(
            """SELECT remote_seq,event_json FROM memory_sync_inbox
               WHERE status='pending' ORDER BY remote_seq LIMIT ?""",
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
        result: list[tuple[int, MemorySyncEvent]] = []
        for row in rows:
            value = json.loads(str(row["event_json"]))
            if not isinstance(value, dict):
                raise MemorySyncContractError("stored inbox event is not an object")
            result.append((int(row["remote_seq"]), MemorySyncEvent.from_dict(value)))
        return result

    def mark_inbox_applied(self, *, remote_seq: int, event_id: str) -> None:
        with self.transaction():
            state = self.con.execute(
                "SELECT local_cursor FROM memory_sync_state WHERE state_id=1"
            ).fetchone()
            if state is None:
                raise MemorySyncContractError("sync state is not initialized")
            cursor = int(state["local_cursor"])
            if remote_seq != cursor + 1:
                raise MemorySyncContractError(
                    f"cannot advance memory sync cursor from {cursor} to non-contiguous {remote_seq}"
                )
            row = self.con.execute(
                "SELECT status,event_id FROM memory_sync_inbox WHERE remote_seq=?", (remote_seq,)
            ).fetchone()
            if row is None or str(row["event_id"]) != event_id:
                raise MemorySyncContractError("inbox event identity mismatch")
            if str(row["status"]) != MemoryInboxStatus.PENDING.value:
                raise MemorySyncContractError("only pending inbox events can be applied")
            now = utc_iso(datetime.now(timezone.utc))
            self.con.execute(
                "UPDATE memory_sync_inbox SET status='applied',applied_at_utc=? WHERE remote_seq=?",
                (now, remote_seq),
            )
            self.con.execute(
                """UPDATE memory_sync_state SET local_cursor=?,last_pull_at_utc=?,last_error=NULL,updated_at_utc=?
                   WHERE state_id=1""",
                (remote_seq, now, now),
            )

    def mark_inbox_conflict(self, *, remote_seq: int, event_id: str, conflict_type: str, details: dict[str, Any]) -> None:
        with self.transaction():
            self.con.execute(
                "UPDATE memory_sync_inbox SET status='conflict',last_error=? WHERE remote_seq=? AND event_id=?",
                (conflict_type, remote_seq, event_id),
            )
            self._record_conflict_in_transaction(
                conflict_type=conflict_type, event_id=event_id, remote_seq=remote_seq, details=details
            )

    def requeue_stale_outbox(self, *, stale_after_seconds: int = 300) -> int:
        threshold = datetime.now(timezone.utc) - timedelta(seconds=max(30, int(stale_after_seconds)))
        with self.transaction():
            cursor = self.con.execute(
                """UPDATE memory_outbox
                   SET status='failed',last_error='stale_processing_claim_requeued'
                   WHERE status='processing' AND claimed_at_utc IS NOT NULL AND claimed_at_utc<?""",
                (utc_iso(threshold),),
            )
            return max(0, int(cursor.rowcount))

    def fail_outbox_with_backoff(self, event_id: str, *, error: str, delay_seconds: float) -> None:
        available = datetime.now(timezone.utc) + timedelta(seconds=max(1.0, float(delay_seconds)))
        with self.transaction():
            cursor = self.con.execute(
                """UPDATE memory_outbox SET status='failed',last_error=?,available_at_utc=?
                   WHERE event_id=?""",
                (error[:4000], utc_iso(available), event_id),
            )
            if cursor.rowcount != 1:
                raise MemorySyncContractError("cannot fail unknown outbox event")
            self.con.execute(
                "UPDATE memory_sync_state SET last_error=?,updated_at_utc=? WHERE state_id=1",
                (error[:4000], utc_iso(datetime.now(timezone.utc))),
            )

    def record_sync_error(self, error: str) -> None:
        with self.transaction():
            self.con.execute(
                "UPDATE memory_sync_state SET last_error=?,updated_at_utc=? WHERE state_id=1",
                (error[:4000], utc_iso(datetime.now(timezone.utc))),
            )

    def sync_cursor(self) -> MemorySyncCursor | None:
        row = self.con.execute(
            "SELECT stream_id,local_cursor,updated_at_utc FROM memory_sync_state WHERE state_id=1"
        ).fetchone()
        if row is None:
            return None
        return MemorySyncCursor(
            stream_id=str(row["stream_id"]),
            remote_seq=int(row["local_cursor"]),
            updated_at_utc=parse_utc(str(row["updated_at_utc"])),
        )

    def sync_status(self, *, configured: bool, mode: MemorySyncMode, backend_ready: bool, crypto_ready: bool) -> MemorySyncStatus:
        state = self.con.execute("SELECT * FROM memory_sync_state WHERE state_id=1").fetchone()
        counts = {
            "outbox_pending": int(self.con.execute("SELECT COUNT(*) FROM memory_outbox WHERE status IN ('pending','processing')").fetchone()[0]),
            "outbox_failed": int(self.con.execute("SELECT COUNT(*) FROM memory_outbox WHERE status='failed'").fetchone()[0]),
            "inbox_pending": int(self.con.execute("SELECT COUNT(*) FROM memory_sync_inbox WHERE status='pending'").fetchone()[0]),
            "conflict_count": int(self.con.execute("SELECT COUNT(*) FROM memory_sync_conflicts WHERE resolved_at_utc IS NULL").fetchone()[0]),
        }
        return MemorySyncStatus(
            configured=configured,
            mode=mode,
            stream_id=str(state["stream_id"]) if state else None,
            device_id=str(state["device_id"]) if state else None,
            backend_ready=backend_ready,
            crypto_ready=crypto_ready,
            local_cursor=int(state["local_cursor"]) if state else 0,
            last_push_at_utc=parse_utc(str(state["last_push_at_utc"])) if state and state["last_push_at_utc"] else None,
            last_pull_at_utc=parse_utc(str(state["last_pull_at_utc"])) if state and state["last_pull_at_utc"] else None,
            last_error=str(state["last_error"]) if state and state["last_error"] else None,
            **counts,
        )

    def _record_conflict_in_transaction(
        self,
        *,
        conflict_type: str,
        event_id: str,
        remote_seq: int | None,
        details: dict[str, Any],
    ) -> str:
        self._require_transaction()
        material = canonical_json_bytes(
            {"conflict_type": conflict_type, "event_id": event_id, "remote_seq": remote_seq, "details": details}
        )
        conflict_id = hashlib.sha256(material).hexdigest()
        self.con.execute(
            """INSERT OR IGNORE INTO memory_sync_conflicts(
               conflict_id,conflict_type,event_id,remote_seq,details_json,created_at_utc)
               VALUES(?,?,?,?,?,?)""",
            (
                conflict_id, conflict_type, event_id, remote_seq,
                json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                utc_iso(datetime.now(timezone.utc)),
            ),
        )
        return conflict_id


__all__ = ["MemorySyncStoreMixin", "ReservedSyncSequence"]
