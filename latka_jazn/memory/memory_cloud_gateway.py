from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol, Sequence
import hashlib
import importlib
import json
import secrets
from urllib import parse as urlparse

from latka_jazn.memory.memory_sync_contracts import (
    MemorySnapshotManifest,
    MemorySyncBatch,
    MemorySyncContractError,
    MemorySyncEvent,
    MemorySyncReceipt,
    MemorySyncReceiptStatus,
    canonical_json_bytes,
    parse_utc,
)


POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jazn_memory_streams(
  stream_id TEXT PRIMARY KEY,
  next_remote_seq BIGINT NOT NULL DEFAULT 1 CHECK(next_remote_seq >= 1),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS jazn_memory_events(
  stream_id TEXT NOT NULL REFERENCES jazn_memory_streams(stream_id) ON DELETE CASCADE,
  remote_seq BIGINT NOT NULL CHECK(remote_seq >= 1),
  event_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  ciphertext_sha256 TEXT NOT NULL,
  event_json JSONB NOT NULL,
  received_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(stream_id, remote_seq),
  UNIQUE(stream_id, event_id),
  UNIQUE(stream_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_jazn_memory_events_pull
  ON jazn_memory_events(stream_id, remote_seq);
CREATE TABLE IF NOT EXISTS jazn_memory_snapshots(
  stream_id TEXT NOT NULL REFERENCES jazn_memory_streams(stream_id) ON DELETE CASCADE,
  snapshot_id TEXT NOT NULL,
  base_remote_seq BIGINT NOT NULL CHECK(base_remote_seq >= 0),
  manifest_sha256 TEXT NOT NULL,
  manifest_json JSONB NOT NULL,
  committed_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(stream_id, snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_jazn_memory_snapshots_latest
  ON jazn_memory_snapshots(stream_id, committed_at_utc DESC, snapshot_id DESC);
CREATE TABLE IF NOT EXISTS jazn_memory_writer_leases(
  stream_id TEXT PRIMARY KEY REFERENCES jazn_memory_streams(stream_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL,
  lease_token_sha256 TEXT NOT NULL,
  lease_expires_at_utc TIMESTAMPTZ NOT NULL,
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class MemoryCloudRepositoryError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class MemoryCloudStreamStatus:
    stream_id: str
    remote_seq: int
    latest_snapshot_id: str | None


@dataclass(slots=True, frozen=True)
class MemoryWriterLeaseState:
    stream_id: str
    device_id: str
    expires_at_utc: datetime

    @property
    def active(self) -> bool:
        return self.expires_at_utc > datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "device_id": self.device_id,
            "expires_at_utc": self.expires_at_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "active": self.active,
        }


class MemoryCloudRepository(Protocol):
    def ensure_schema(self) -> None: ...
    def status(self, stream_id: str) -> MemoryCloudStreamStatus: ...
    def ingest(self, batch: MemorySyncBatch) -> Sequence[MemorySyncReceipt]: ...
    def pull(self, *, stream_id: str, after_remote_seq: int, limit: int) -> Sequence[tuple[int, MemorySyncEvent]]: ...
    def commit_snapshot(self, manifest: MemorySnapshotManifest) -> None: ...
    def latest_snapshot(self, stream_id: str) -> MemorySnapshotManifest | None: ...
    def acquire_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str, ttl_seconds: int
    ) -> MemoryWriterLeaseState: ...
    def renew_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str, ttl_seconds: int
    ) -> MemoryWriterLeaseState: ...
    def release_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str
    ) -> bool: ...
    def validate_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str
    ) -> bool: ...


class PostgresMemoryCloudRepository:
    """Transactional encrypted-memory event repository backed by PostgreSQL.

    The repository stores encrypted wire events only. Remote sequence allocation and
    event insertion occur under one stream-row lock, which makes retry/idempotency
    behavior deterministic without distributed transactions. ``connection_factory``
    is injectable for tests and deployments; the default lazily imports psycopg so
    local Jaźń does not acquire a PostgreSQL dependency when cloud sync is disabled.
    """

    def __init__(
        self,
        dsn: str,
        *,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        if not dsn.strip() and connection_factory is None:
            raise MemoryCloudRepositoryError("PostgreSQL DSN is required")
        self.dsn = dsn.strip()
        self._factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if self._factory is not None:
            con = self._factory()
        else:
            try:
                psycopg: Any = importlib.import_module("psycopg")
            except Exception as exc:  # pragma: no cover - optional server dependency
                raise MemoryCloudRepositoryError(
                    "psycopg is required for PostgreSQL memory gateway; install latka-jazn[memory-cloud-server]"
                ) from exc
            con = psycopg.connect(self.dsn)
        try:
            yield con
        finally:
            con.close()

    def ensure_schema(self) -> None:
        statements = tuple(statement.strip() for statement in POSTGRES_SCHEMA_SQL.split(";") if statement.strip())
        with self._connection() as con:
            with con.transaction():
                for statement in statements:
                    con.execute(statement)

    def status(self, stream_id: str) -> MemoryCloudStreamStatus:
        if not stream_id.strip():
            raise MemorySyncContractError("stream_id is required")
        with self._connection() as con:
            row = con.execute(
                "SELECT next_remote_seq FROM jazn_memory_streams WHERE stream_id=%s", (stream_id,)
            ).fetchone()
            remote_seq = max(0, int(row[0]) - 1) if row else 0
            snapshot = con.execute(
                """SELECT snapshot_id FROM jazn_memory_snapshots
                   WHERE stream_id=%s ORDER BY committed_at_utc DESC,snapshot_id DESC LIMIT 1""",
                (stream_id,),
            ).fetchone()
        return MemoryCloudStreamStatus(stream_id, remote_seq, str(snapshot[0]) if snapshot else None)

    def ingest(self, batch: MemorySyncBatch) -> Sequence[MemorySyncReceipt]:
        receipts: list[MemorySyncReceipt] = []
        now = datetime.now(timezone.utc)
        with self._connection() as con:
            with con.transaction():
                con.execute(
                    """INSERT INTO jazn_memory_streams(stream_id,next_remote_seq)
                       VALUES(%s,1) ON CONFLICT(stream_id) DO NOTHING""",
                    (batch.stream_id,),
                )
                stream_row = con.execute(
                    "SELECT next_remote_seq FROM jazn_memory_streams WHERE stream_id=%s FOR UPDATE",
                    (batch.stream_id,),
                ).fetchone()
                if stream_row is None:
                    raise MemoryCloudRepositoryError("memory stream row disappeared during ingest")
                next_seq = int(stream_row[0])
                for event in batch.events:
                    existing = con.execute(
                        """SELECT remote_seq,event_id,idempotency_key,ciphertext_sha256
                           FROM jazn_memory_events
                           WHERE stream_id=%s AND (event_id=%s OR idempotency_key=%s)
                           ORDER BY remote_seq LIMIT 1""",
                        (event.stream_id, event.event_id, event.idempotency_key),
                    ).fetchone()
                    if existing is not None:
                        remote_seq, event_id, idem, cipher_hash = existing
                        if (
                            str(event_id) == event.event_id
                            and str(idem) == event.idempotency_key
                            and str(cipher_hash) == event.ciphertext_sha256
                        ):
                            receipts.append(self._receipt(event, MemorySyncReceiptStatus.ALREADY_EXISTS, int(remote_seq), now))
                        else:
                            receipts.append(
                                self._receipt(
                                    event, MemorySyncReceiptStatus.REJECTED, None, now,
                                    error_code="identity_hash_conflict",
                                )
                            )
                        continue
                    remote_seq = next_seq
                    next_seq += 1
                    con.execute(
                        """INSERT INTO jazn_memory_events(
                           stream_id,remote_seq,event_id,idempotency_key,ciphertext_sha256,event_json,received_at_utc)
                           VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                        (
                            event.stream_id,
                            remote_seq,
                            event.event_id,
                            event.idempotency_key,
                            event.ciphertext_sha256,
                            json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")),
                            now,
                        ),
                    )
                    receipts.append(self._receipt(event, MemorySyncReceiptStatus.ACCEPTED, remote_seq, now))
                con.execute(
                    "UPDATE jazn_memory_streams SET next_remote_seq=%s,updated_at_utc=%s WHERE stream_id=%s",
                    (next_seq, now, batch.stream_id),
                )
        return tuple(receipts)

    def pull(self, *, stream_id: str, after_remote_seq: int, limit: int) -> Sequence[tuple[int, MemorySyncEvent]]:
        if after_remote_seq < 0:
            raise MemorySyncContractError("after_remote_seq cannot be negative")
        bounded = max(1, min(int(limit), 1000))
        with self._connection() as con:
            rows = con.execute(
                """SELECT remote_seq,event_json FROM jazn_memory_events
                   WHERE stream_id=%s AND remote_seq>%s ORDER BY remote_seq LIMIT %s""",
                (stream_id, after_remote_seq, bounded),
            ).fetchall()
        result: list[tuple[int, MemorySyncEvent]] = []
        previous = after_remote_seq
        for remote_seq, raw_event in rows:
            seq = int(remote_seq)
            if seq <= previous:
                raise MemoryCloudRepositoryError("PostgreSQL returned non-monotonic remote_seq")
            value = raw_event if isinstance(raw_event, Mapping) else json.loads(str(raw_event))
            result.append((seq, MemorySyncEvent.from_dict(value)))
            previous = seq
        return tuple(result)

    def commit_snapshot(self, manifest: MemorySnapshotManifest) -> None:
        with self._connection() as con:
            with con.transaction():
                con.execute(
                    """INSERT INTO jazn_memory_streams(stream_id,next_remote_seq)
                       VALUES(%s,1) ON CONFLICT(stream_id) DO NOTHING""",
                    (manifest.stream_id,),
                )
                existing = con.execute(
                    """SELECT manifest_sha256 FROM jazn_memory_snapshots
                       WHERE stream_id=%s AND snapshot_id=%s""",
                    (manifest.stream_id, manifest.snapshot_id),
                ).fetchone()
                digest = manifest.manifest_sha256()
                if existing is not None:
                    if str(existing[0]) != digest:
                        raise MemoryCloudRepositoryError("snapshot id collision with different manifest")
                    return
                con.execute(
                    """INSERT INTO jazn_memory_snapshots(
                       stream_id,snapshot_id,base_remote_seq,manifest_sha256,manifest_json)
                       VALUES(%s,%s,%s,%s,%s::jsonb)""",
                    (
                        manifest.stream_id,
                        manifest.snapshot_id,
                        manifest.base_remote_seq,
                        digest,
                        json.dumps(manifest.to_dict(), ensure_ascii=False, separators=(",", ":")),
                    ),
                )

    def latest_snapshot(self, stream_id: str) -> MemorySnapshotManifest | None:
        with self._connection() as con:
            row = con.execute(
                """SELECT manifest_json FROM jazn_memory_snapshots
                   WHERE stream_id=%s ORDER BY committed_at_utc DESC,snapshot_id DESC LIMIT 1""",
                (stream_id,),
            ).fetchone()
        if row is None:
            return None
        value = row[0] if isinstance(row[0], Mapping) else json.loads(str(row[0]))
        return MemorySnapshotManifest.from_dict(value)

    def acquire_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str, ttl_seconds: int
    ) -> MemoryWriterLeaseState:
        return self._upsert_writer_lease(
            stream_id=stream_id, device_id=device_id, lease_token_sha256=lease_token_sha256,
            ttl_seconds=ttl_seconds, renew_only=False,
        )

    def renew_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str, ttl_seconds: int
    ) -> MemoryWriterLeaseState:
        return self._upsert_writer_lease(
            stream_id=stream_id, device_id=device_id, lease_token_sha256=lease_token_sha256,
            ttl_seconds=ttl_seconds, renew_only=True,
        )

    def _upsert_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str, ttl_seconds: int, renew_only: bool
    ) -> MemoryWriterLeaseState:
        if not stream_id.strip() or not device_id.strip() or len(lease_token_sha256) != 64:
            raise MemorySyncContractError("writer lease requires stream_id, device_id and SHA-256 token")
        ttl = max(10, min(int(ttl_seconds), 3600))
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl)
        with self._connection() as con:
            with con.transaction():
                con.execute(
                    "INSERT INTO jazn_memory_streams(stream_id,next_remote_seq) VALUES(%s,1) "
                    "ON CONFLICT(stream_id) DO NOTHING", (stream_id,),
                )
                row = con.execute(
                    "SELECT device_id,lease_token_sha256,lease_expires_at_utc "
                    "FROM jazn_memory_writer_leases WHERE stream_id=%s FOR UPDATE", (stream_id,),
                ).fetchone()
                if row is not None:
                    current_device, current_token, current_expiry = str(row[0]), str(row[1]), row[2]
                    if current_expiry.tzinfo is None:
                        current_expiry = current_expiry.replace(tzinfo=timezone.utc)
                    same_owner = current_device == device_id and secrets.compare_digest(current_token, lease_token_sha256)
                    if renew_only and not same_owner:
                        raise MemoryCloudRepositoryError("writer lease cannot be renewed by a different owner")
                    if current_expiry > now and not same_owner:
                        raise MemoryCloudRepositoryError("memory stream already has an active writer lease")
                elif renew_only:
                    raise MemoryCloudRepositoryError("writer lease does not exist")
                con.execute(
                    """INSERT INTO jazn_memory_writer_leases(
                       stream_id,device_id,lease_token_sha256,lease_expires_at_utc,updated_at_utc)
                       VALUES(%s,%s,%s,%s,%s)
                       ON CONFLICT(stream_id) DO UPDATE SET
                         device_id=EXCLUDED.device_id,
                         lease_token_sha256=EXCLUDED.lease_token_sha256,
                         lease_expires_at_utc=EXCLUDED.lease_expires_at_utc,
                         updated_at_utc=EXCLUDED.updated_at_utc""",
                    (stream_id, device_id, lease_token_sha256, expires, now),
                )
        return MemoryWriterLeaseState(stream_id=stream_id, device_id=device_id, expires_at_utc=expires)

    def release_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str
    ) -> bool:
        with self._connection() as con:
            with con.transaction():
                cursor = con.execute(
                    "DELETE FROM jazn_memory_writer_leases "
                    "WHERE stream_id=%s AND device_id=%s AND lease_token_sha256=%s",
                    (stream_id, device_id, lease_token_sha256),
                )
                return int(cursor.rowcount or 0) == 1

    def validate_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str
    ) -> bool:
        now = datetime.now(timezone.utc)
        with self._connection() as con:
            row = con.execute(
                "SELECT device_id,lease_token_sha256,lease_expires_at_utc "
                "FROM jazn_memory_writer_leases WHERE stream_id=%s", (stream_id,),
            ).fetchone()
        if row is None:
            return False
        expiry = row[2]
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return (
            str(row[0]) == device_id
            and secrets.compare_digest(str(row[1]), lease_token_sha256)
            and expiry > now
        )

    @staticmethod
    def _receipt(
        event: MemorySyncEvent,
        status: MemorySyncReceiptStatus,
        remote_seq: int | None,
        now: datetime,
        *,
        error_code: str | None = None,
    ) -> MemorySyncReceipt:
        return MemorySyncReceipt(
            stream_id=event.stream_id,
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
            status=status,
            remote_seq=remote_seq,
            ciphertext_sha256=event.ciphertext_sha256,
            received_at_utc=now,
            error_code=error_code,
        )


class InMemoryMemoryCloudRepository:
    """Deterministic server-side repository implementing the PostgreSQL contract.

    This is not a production durability backend. It exists for gateway integration,
    protocol conformance and fault-injection tests without requiring PostgreSQL.
    It implements the same immutable event identity, monotonic sequence, snapshot
    and writer-lease semantics as the production repository.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[tuple[int, MemorySyncEvent]]] = {}
        self._event_ids: dict[tuple[str, str], tuple[int, MemorySyncEvent]] = {}
        self._idempotency: dict[tuple[str, str], tuple[int, MemorySyncEvent]] = {}
        self._snapshots: dict[str, list[MemorySnapshotManifest]] = {}
        self._leases: dict[str, tuple[str, str, datetime]] = {}

    def ensure_schema(self) -> None:
        return None

    def status(self, stream_id: str) -> MemoryCloudStreamStatus:
        events = self._events.get(stream_id, [])
        snapshots = self._snapshots.get(stream_id, [])
        return MemoryCloudStreamStatus(
            stream_id=stream_id,
            remote_seq=events[-1][0] if events else 0,
            latest_snapshot_id=snapshots[-1].snapshot_id if snapshots else None,
        )

    def ingest(self, batch: MemorySyncBatch) -> Sequence[MemorySyncReceipt]:
        now = datetime.now(timezone.utc)
        values = self._events.setdefault(batch.stream_id, [])
        receipts: list[MemorySyncReceipt] = []
        for event in batch.events:
            existing = self._event_ids.get((event.stream_id, event.event_id)) or self._idempotency.get(
                (event.stream_id, event.idempotency_key)
            )
            if existing is not None:
                seq, stored = existing
                if (
                    stored.event_id == event.event_id
                    and stored.idempotency_key == event.idempotency_key
                    and stored.ciphertext_sha256 == event.ciphertext_sha256
                ):
                    receipts.append(PostgresMemoryCloudRepository._receipt(
                        event, MemorySyncReceiptStatus.ALREADY_EXISTS, seq, now
                    ))
                else:
                    receipts.append(PostgresMemoryCloudRepository._receipt(
                        event, MemorySyncReceiptStatus.REJECTED, None, now,
                        error_code="identity_hash_conflict",
                    ))
                continue
            seq = len(values) + 1
            values.append((seq, event))
            self._event_ids[(event.stream_id, event.event_id)] = (seq, event)
            self._idempotency[(event.stream_id, event.idempotency_key)] = (seq, event)
            receipts.append(PostgresMemoryCloudRepository._receipt(
                event, MemorySyncReceiptStatus.ACCEPTED, seq, now
            ))
        return tuple(receipts)

    def pull(self, *, stream_id: str, after_remote_seq: int, limit: int) -> Sequence[tuple[int, MemorySyncEvent]]:
        if after_remote_seq < 0:
            raise MemorySyncContractError("after_remote_seq cannot be negative")
        bounded = max(1, min(int(limit), 1000))
        return tuple((seq, event) for seq, event in self._events.get(stream_id, []) if seq > after_remote_seq)[:bounded]

    def commit_snapshot(self, manifest: MemorySnapshotManifest) -> None:
        values = self._snapshots.setdefault(manifest.stream_id, [])
        for existing in values:
            if existing.snapshot_id == manifest.snapshot_id:
                if existing.manifest_sha256() != manifest.manifest_sha256():
                    raise MemoryCloudRepositoryError("snapshot id collision with different manifest")
                return
        values.append(manifest)
        values.sort(key=lambda item: (item.created_at_utc, item.snapshot_id))

    def latest_snapshot(self, stream_id: str) -> MemorySnapshotManifest | None:
        values = self._snapshots.get(stream_id, [])
        return values[-1] if values else None

    def acquire_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str, ttl_seconds: int
    ) -> MemoryWriterLeaseState:
        return self._set_lease(
            stream_id=stream_id, device_id=device_id, lease_token_sha256=lease_token_sha256,
            ttl_seconds=ttl_seconds, renew_only=False,
        )

    def renew_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str, ttl_seconds: int
    ) -> MemoryWriterLeaseState:
        return self._set_lease(
            stream_id=stream_id, device_id=device_id, lease_token_sha256=lease_token_sha256,
            ttl_seconds=ttl_seconds, renew_only=True,
        )

    def _set_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str, ttl_seconds: int, renew_only: bool
    ) -> MemoryWriterLeaseState:
        now = datetime.now(timezone.utc)
        current = self._leases.get(stream_id)
        if current is not None:
            same = current[0] == device_id and secrets.compare_digest(current[1], lease_token_sha256)
            if renew_only and not same:
                raise MemoryCloudRepositoryError("writer lease cannot be renewed by a different owner")
            if current[2] > now and not same:
                raise MemoryCloudRepositoryError("memory stream already has an active writer lease")
        elif renew_only:
            raise MemoryCloudRepositoryError("writer lease does not exist")
        expires = now + timedelta(seconds=max(10, min(int(ttl_seconds), 3600)))
        self._leases[stream_id] = (device_id, lease_token_sha256, expires)
        return MemoryWriterLeaseState(stream_id, device_id, expires)

    def release_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str
    ) -> bool:
        current = self._leases.get(stream_id)
        if current is None:
            return False
        if current[0] != device_id or not secrets.compare_digest(current[1], lease_token_sha256):
            return False
        del self._leases[stream_id]
        return True

    def validate_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token_sha256: str
    ) -> bool:
        current = self._leases.get(stream_id)
        return bool(
            current is not None
            and current[0] == device_id
            and secrets.compare_digest(current[1], lease_token_sha256)
            and current[2] > datetime.now(timezone.utc)
        )


class CloudObjectStore(Protocol):
    def put_immutable(self, *, object_id: str, data: bytes) -> None: ...
    def get(self, *, object_id: str) -> bytes: ...
    def exists(self, *, object_id: str) -> bool: ...


class S3CompatibleObjectStore:
    """Immutable content-addressed object storage adapter.

    Object identifiers must end with the SHA-256 of their ciphertext. Uploads never
    overwrite an object with different bytes. boto3 is imported lazily so this
    service-side adapter does not affect normal local installations.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "jazn-memory",
        client: Any | None = None,
        endpoint_url: str | None = None,
        region_name: str | None = None,
    ) -> None:
        if not bucket.strip():
            raise MemoryCloudRepositoryError("object-store bucket is required")
        self.bucket = bucket.strip()
        self.prefix = prefix.strip("/")
        resolved_client: Any = client
        if resolved_client is None:
            try:
                boto3: Any = importlib.import_module("boto3")
            except Exception as exc:  # pragma: no cover - optional server dependency
                raise MemoryCloudRepositoryError(
                    "boto3 is required for S3-compatible memory objects; install latka-jazn[memory-cloud-server]"
                ) from exc
            resolved_client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region_name)
        if resolved_client is None:
            raise MemoryCloudRepositoryError("S3-compatible client construction returned no client")
        self.client: Any = resolved_client

    def put_immutable(self, *, object_id: str, data: bytes) -> None:
        digest = hashlib.sha256(data).hexdigest()
        if not object_id.endswith(digest):
            raise MemorySyncContractError("content-addressed object_id does not match ciphertext SHA-256")
        key = self._key(object_id)
        try:
            existing = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if not self._is_not_found(exc):
                raise
        else:
            metadata = existing.get("Metadata") or {}
            if str(metadata.get("sha256") or "") != digest:
                raise MemoryCloudRepositoryError("immutable object exists with different SHA-256 metadata")
            return
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            Metadata={"sha256": digest},
            ContentType="application/octet-stream",
        )
        verified = self.client.head_object(Bucket=self.bucket, Key=key)
        if str((verified.get("Metadata") or {}).get("sha256") or "") != digest:
            raise MemoryCloudRepositoryError("object-store upload verification failed")

    def get(self, *, object_id: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(object_id))
        data = bytes(response["Body"].read())
        digest = hashlib.sha256(data).hexdigest()
        if not object_id.endswith(digest):
            raise MemoryCloudRepositoryError("downloaded object hash does not match content-addressed id")
        return data

    def exists(self, *, object_id: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(object_id))
        except Exception as exc:
            if self._is_not_found(exc):
                return False
            raise
        return True

    def _key(self, object_id: str) -> str:
        clean = object_id.strip("/")
        if not clean or ".." in clean.split("/"):
            raise MemorySyncContractError("unsafe object_id")
        return f"{self.prefix}/{clean}" if self.prefix else clean

    @staticmethod
    def _is_not_found(exc: Exception) -> bool:
        response = getattr(exc, "response", None)
        if isinstance(response, Mapping):
            error = response.get("Error")
            if isinstance(error, Mapping) and str(error.get("Code")) in {"404", "NoSuchKey", "NotFound"}:
                return True
        return False


class MemoryCloudGatewayService:
    """Provider-neutral service boundary used by an HTTP deployment layer.

    The service accepts/returns only encrypted wire contracts. It has no API that
    accepts plaintext memory records. Snapshot manifests are committed only after all
    immutable ciphertext objects referenced by them are present.
    """

    def __init__(
        self, *, repository: MemoryCloudRepository, object_store: CloudObjectStore | None = None,
        require_writer_lease: bool = False,
    ) -> None:
        self.repository = repository
        self.object_store = object_store
        self.require_writer_lease = bool(require_writer_lease)

    def status(self, *, stream_id: str) -> dict[str, Any]:
        status = self.repository.status(stream_id)
        return {
            "ready": True,
            "stream_id": status.stream_id,
            "remote_seq": status.remote_seq,
            "latest_snapshot_id": status.latest_snapshot_id,
            "plaintext_memory_accepted": False,
        }

    def push_events(self, payload: Mapping[str, Any], *, writer_lease_token: str | None = None) -> dict[str, Any]:
        events_raw = payload.get("events")
        if not isinstance(events_raw, list):
            raise MemorySyncContractError("gateway batch requires events list")
        events = [MemorySyncEvent.from_dict(item) for item in events_raw if isinstance(item, Mapping)]
        if len(events) != len(events_raw):
            raise MemorySyncContractError("gateway batch contains non-object event")
        batch = MemorySyncBatch(events)
        if self.require_writer_lease:
            token = str(writer_lease_token or "")
            if not token:
                raise MemoryCloudRepositoryError("active writer lease token is required")
            token_sha = hashlib.sha256(token.encode("utf-8")).hexdigest()
            devices = {event.device_id for event in batch.events}
            if len(devices) != 1:
                raise MemorySyncContractError("a leased batch must contain events from exactly one device")
            if not self.repository.validate_writer_lease(
                stream_id=batch.stream_id, device_id=next(iter(devices)), lease_token_sha256=token_sha
            ):
                raise MemoryCloudRepositoryError("writer lease is missing, expired or owned by another device")
        return {"receipts": [receipt.to_dict() for receipt in self.repository.ingest(batch)]}

    def pull_events(self, *, stream_id: str, after: int, limit: int) -> dict[str, Any]:
        values = self.repository.pull(stream_id=stream_id, after_remote_seq=after, limit=limit)
        return {"events": [{"remote_seq": seq, "event": event.to_dict()} for seq, event in values]}

    def acquire_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token: str, ttl_seconds: int = 120
    ) -> dict[str, Any]:
        token = lease_token.strip()
        if len(token) < 32:
            raise MemorySyncContractError("writer lease token must contain at least 32 characters of entropy")
        state = self.repository.acquire_writer_lease(
            stream_id=stream_id, device_id=device_id,
            lease_token_sha256=hashlib.sha256(token.encode("utf-8")).hexdigest(), ttl_seconds=ttl_seconds,
        )
        return state.to_dict()

    def renew_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token: str, ttl_seconds: int = 120
    ) -> dict[str, Any]:
        state = self.repository.renew_writer_lease(
            stream_id=stream_id, device_id=device_id,
            lease_token_sha256=hashlib.sha256(lease_token.encode("utf-8")).hexdigest(), ttl_seconds=ttl_seconds,
        )
        return state.to_dict()

    def release_writer_lease(self, *, stream_id: str, device_id: str, lease_token: str) -> dict[str, Any]:
        released = self.repository.release_writer_lease(
            stream_id=stream_id, device_id=device_id,
            lease_token_sha256=hashlib.sha256(lease_token.encode("utf-8")).hexdigest(),
        )
        return {"stream_id": stream_id, "device_id": device_id, "released": released}

    def put_snapshot_object(self, *, object_id: str, data: bytes) -> None:
        if self.object_store is None:
            raise MemoryCloudRepositoryError("snapshot object store is not configured")
        self.object_store.put_immutable(object_id=object_id, data=data)

    def get_snapshot_object(self, *, object_id: str) -> bytes:
        if self.object_store is None:
            raise MemoryCloudRepositoryError("snapshot object store is not configured")
        return self.object_store.get(object_id=object_id)

    def commit_snapshot(self, manifest: MemorySnapshotManifest) -> None:
        if self.object_store is None:
            raise MemoryCloudRepositoryError("snapshot object store is not configured")
        missing = [chunk.object_id for chunk in manifest.chunks if not self.object_store.exists(object_id=chunk.object_id)]
        if missing:
            raise MemoryCloudRepositoryError(f"snapshot references missing immutable objects: {missing[:3]}")
        self.repository.commit_snapshot(manifest)

    def latest_snapshot(self, *, stream_id: str) -> MemorySnapshotManifest | None:
        return self.repository.latest_snapshot(stream_id)


class MemoryCloudGatewayWSGIApplication:
    """Small deployable WSGI transport for ``MemoryCloudGatewayService``.

    The application deliberately exposes encrypted protocol envelopes only. It
    enforces bearer authentication, bounded request bodies, strict route/method
    matching and JSON error responses without exception tracebacks or memory
    payloads. TLS termination is expected at the reverse proxy/load balancer; the
    client separately requires HTTPS except for explicitly enabled loopback tests.
    """

    def __init__(
        self,
        service: MemoryCloudGatewayService,
        *,
        bearer_tokens: Iterable[str],
        max_json_body_bytes: int = 4 * 1024 * 1024,
        max_object_body_bytes: int = 32 * 1024 * 1024,
    ) -> None:
        tokens = tuple(token.strip() for token in bearer_tokens if token.strip())
        if not tokens:
            raise MemoryCloudRepositoryError("at least one gateway bearer token is required")
        self.service = service
        self._tokens = tokens
        self.max_json_body_bytes = max(64 * 1024, min(int(max_json_body_bytes), 16 * 1024 * 1024))
        self.max_object_body_bytes = max(64 * 1024, min(int(max_object_body_bytes), 128 * 1024 * 1024))

    def __call__(self, environ: Mapping[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        try:
            self._authenticate(environ)
            status, headers, body = self._dispatch(environ)
        except PermissionError as exc:
            status, headers, body = self._json_response("401 Unauthorized", {"error": "unauthorized", "detail": str(exc)})
        except (MemorySyncContractError, MemoryCloudRepositoryError, ValueError) as exc:
            status, headers, body = self._json_response(
                "400 Bad Request", {"error": "request_rejected", "detail": str(exc)[:1000]}
            )
        except Exception:
            status, headers, body = self._json_response(
                "500 Internal Server Error", {"error": "internal_error", "detail": "memory gateway operation failed"}
            )
        start_response(status, headers)
        return [body]

    def _authenticate(self, environ: Mapping[str, Any]) -> None:
        header = str(environ.get("HTTP_AUTHORIZATION") or "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            raise PermissionError("bearer token is required")
        candidate = header[len(prefix):]
        if not any(secrets.compare_digest(candidate, expected) for expected in self._tokens):
            raise PermissionError("invalid bearer token")

    def _dispatch(self, environ: Mapping[str, Any]) -> tuple[str, list[tuple[str, str]], bytes]:
        method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        path = str(environ.get("PATH_INFO") or "/")
        query = urlparse.parse_qs(str(environ.get("QUERY_STRING") or ""), keep_blank_values=False)
        if method == "GET" and path == "/v1/memory/status":
            return self._json_response("200 OK", self.service.status(stream_id=self._one(query, "stream_id")))
        if method == "POST" and path == "/v1/memory/events:batch":
            payload = self._read_json(environ)
            return self._json_response(
                "200 OK", self.service.push_events(
                    payload, writer_lease_token=self._optional_header(environ, "HTTP_X_JAZN_WRITER_LEASE")
                )
            )
        if method == "GET" and path == "/v1/memory/events":
            return self._json_response(
                "200 OK", self.service.pull_events(
                    stream_id=self._one(query, "stream_id"),
                    after=self._int_query(query, "after", minimum=0, maximum=2**63 - 1),
                    limit=self._int_query(query, "limit", minimum=1, maximum=1000),
                )
            )
        if path.startswith("/v1/memory/objects/"):
            object_id = urlparse.unquote(path[len("/v1/memory/objects/"):])
            if method == "PUT":
                data = self._read_body(environ, self.max_object_body_bytes)
                self.service.put_snapshot_object(object_id=object_id, data=data)
                return self._json_response("200 OK", {"stored": True, "object_id": object_id})
            if method == "GET":
                data = self.service.get_snapshot_object(object_id=object_id)
                return "200 OK", [("Content-Type", "application/octet-stream"), ("Content-Length", str(len(data)))], data
        if method == "POST" and path == "/v1/memory/snapshots:commit":
            payload = self._read_json(environ)
            raw_manifest = payload.get("manifest")
            if not isinstance(raw_manifest, Mapping):
                raise MemorySyncContractError("snapshot commit requires manifest object")
            manifest = MemorySnapshotManifest.from_dict(raw_manifest)
            self.service.commit_snapshot(manifest)
            return self._json_response("200 OK", {"committed": True, "snapshot_id": manifest.snapshot_id})
        if method == "GET" and path == "/v1/memory/snapshots/latest":
            manifest = self.service.latest_snapshot(stream_id=self._one(query, "stream_id"))
            return self._json_response("200 OK", {"manifest": manifest.to_dict() if manifest else None})
        if method == "POST" and path in {
            "/v1/memory/writer-lease:acquire", "/v1/memory/writer-lease:renew", "/v1/memory/writer-lease:release"
        }:
            payload = self._read_json(environ)
            common = {
                "stream_id": str(payload.get("stream_id") or ""),
                "device_id": str(payload.get("device_id") or ""),
                "lease_token": str(payload.get("lease_token") or ""),
            }
            if path.endswith(":acquire"):
                result = self.service.acquire_writer_lease(**common, ttl_seconds=int(payload.get("ttl_seconds") or 120))
            elif path.endswith(":renew"):
                result = self.service.renew_writer_lease(**common, ttl_seconds=int(payload.get("ttl_seconds") or 120))
            else:
                result = self.service.release_writer_lease(**common)
            return self._json_response("200 OK", result)
        return self._json_response("404 Not Found", {"error": "not_found"})

    def _read_json(self, environ: Mapping[str, Any]) -> Mapping[str, Any]:
        raw = self._read_body(environ, self.max_json_body_bytes)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MemorySyncContractError("request body is not valid UTF-8 JSON") from exc
        if not isinstance(value, Mapping):
            raise MemorySyncContractError("request JSON must be an object")
        return value

    @staticmethod
    def _content_length(environ: Mapping[str, Any]) -> int:
        raw = str(environ.get("CONTENT_LENGTH") or "0").strip()
        try:
            value = int(raw or "0")
        except ValueError as exc:
            raise MemorySyncContractError("invalid Content-Length") from exc
        if value < 0:
            raise MemorySyncContractError("negative Content-Length")
        return value

    def _read_body(self, environ: Mapping[str, Any], maximum: int) -> bytes:
        length = self._content_length(environ)
        if length > maximum:
            raise MemorySyncContractError("request body exceeds safety limit")
        source = environ.get("wsgi.input")
        if source is None or not hasattr(source, "read"):
            raise MemorySyncContractError("WSGI input stream is missing")
        data = source.read(length) if length else b""
        if len(data) != length:
            raise MemorySyncContractError("request body ended before Content-Length")
        return bytes(data)

    @staticmethod
    def _one(query: Mapping[str, list[str]], name: str) -> str:
        values = query.get(name) or []
        if len(values) != 1 or not values[0].strip():
            raise MemorySyncContractError(f"query parameter {name} is required exactly once")
        return values[0].strip()

    @classmethod
    def _int_query(cls, query: Mapping[str, list[str]], name: str, *, minimum: int, maximum: int) -> int:
        text = cls._one(query, name)
        try:
            value = int(text)
        except ValueError as exc:
            raise MemorySyncContractError(f"query parameter {name} must be an integer") from exc
        if not minimum <= value <= maximum:
            raise MemorySyncContractError(f"query parameter {name} is outside allowed range")
        return value

    @staticmethod
    def _optional_header(environ: Mapping[str, Any], name: str) -> str | None:
        value = str(environ.get(name) or "").strip()
        return value or None

    @staticmethod
    def _json_response(status: str, payload: Mapping[str, Any]) -> tuple[str, list[tuple[str, str]], bytes]:
        body = canonical_json_bytes(payload)
        return status, [("Content-Type", "application/json"), ("Content-Length", str(len(body)))], body


__all__ = [
    "CloudObjectStore",
    "InMemoryMemoryCloudRepository",
    "MemoryCloudGatewayService",
    "MemoryCloudRepository",
    "MemoryCloudRepositoryError",
    "MemoryCloudStreamStatus",
    "MemoryCloudGatewayWSGIApplication",
    "MemoryWriterLeaseState",
    "POSTGRES_SCHEMA_SQL",
    "PostgresMemoryCloudRepository",
    "S3CompatibleObjectStore",
]
