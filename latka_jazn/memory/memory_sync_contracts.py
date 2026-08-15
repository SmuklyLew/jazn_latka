from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable, Mapping
import base64
import hashlib
import json

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("memory_sync_contracts")
EVENT_SCHEMA_VERSION = "jazn_memory_sync_event/v1"
RECEIPT_SCHEMA_VERSION = "jazn_memory_sync_receipt/v1"
SNAPSHOT_SCHEMA_VERSION = "jazn_memory_snapshot_manifest/v1"


class MemorySyncMode(StrEnum):
    OFF = "off"
    BACKUP = "backup"
    PUSH_PULL = "push_pull"


class MemorySyncReceiptStatus(StrEnum):
    ACCEPTED = "accepted"
    ALREADY_EXISTS = "already_exists"
    REJECTED = "rejected"


class MemoryInboxStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class MemorySyncContractError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class MemorySyncPlainEvent:
    """Local plaintext event before client-side encryption.

    This type never crosses the network. It exists so the outbox/domain layer and
    encryption layer have a typed boundary. ``payload`` may contain private memory
    content and therefore must never be logged by cloud adapters.
    """

    stream_id: str
    event_id: str
    idempotency_key: str
    device_id: str
    device_seq: int
    event_type: str
    aggregate_id: str
    aggregate_revision: int
    payload: Mapping[str, Any]
    created_at_utc: datetime
    parent_event_id: str | None = None
    turn_id: str | None = None
    thought_id: str | None = None
    previous_device_event_sha256: str | None = None

    def __post_init__(self) -> None:
        required = {
            "stream_id": self.stream_id,
            "event_id": self.event_id,
            "idempotency_key": self.idempotency_key,
            "device_id": self.device_id,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
        }
        for name, value in required.items():
            if not str(value).strip():
                raise MemorySyncContractError(f"{name} is required")
        if self.device_seq < 1:
            raise MemorySyncContractError("device_seq must be positive")
        if self.aggregate_revision < 1:
            raise MemorySyncContractError("aggregate_revision must be positive")
        if self.created_at_utc.tzinfo is None:
            raise MemorySyncContractError("created_at_utc must be timezone-aware")
        object.__setattr__(self, "payload", dict(self.payload))

    def payload_bytes(self) -> bytes:
        return canonical_json_bytes(self.payload)

    def aad(self, *, key_version: int, payload_codec: str = "json") -> dict[str, Any]:
        return {
            "schema_version": EVENT_SCHEMA_VERSION,
            "stream_id": self.stream_id,
            "event_id": self.event_id,
            "idempotency_key": self.idempotency_key,
            "device_id": self.device_id,
            "device_seq": self.device_seq,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "aggregate_revision": self.aggregate_revision,
            "parent_event_id": self.parent_event_id,
            "turn_id": self.turn_id,
            "thought_id": self.thought_id,
            "payload_codec": payload_codec,
            "key_version": key_version,
            "created_at_utc": utc_iso(self.created_at_utc),
            "previous_device_event_sha256": self.previous_device_event_sha256,
        }


@dataclass(slots=True, frozen=True)
class MemorySyncEvent:
    """Encrypted wire event.

    Only opaque identifiers and authenticated protocol metadata are plaintext.
    Memory content exists exclusively in ``ciphertext_b64``.
    """

    stream_id: str
    event_id: str
    idempotency_key: str
    device_id: str
    device_seq: int
    event_type: str
    aggregate_id: str
    aggregate_revision: int
    payload_codec: str
    ciphertext_b64: str
    ciphertext_sha256: str
    key_version: int
    nonce_b64: str
    aad_sha256: str
    created_at_utc: datetime
    parent_event_id: str | None = None
    turn_id: str | None = None
    thought_id: str | None = None
    previous_device_event_sha256: str | None = None
    schema_version: str = EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise MemorySyncContractError(f"unsupported event schema: {self.schema_version}")
        if self.device_seq < 1 or self.aggregate_revision < 1 or self.key_version < 1:
            raise MemorySyncContractError("device_seq, aggregate_revision and key_version must be positive")
        if self.created_at_utc.tzinfo is None:
            raise MemorySyncContractError("created_at_utc must be timezone-aware")
        for field_name in (
            "stream_id", "event_id", "idempotency_key", "device_id", "event_type",
            "aggregate_id", "payload_codec", "ciphertext_b64", "ciphertext_sha256",
            "nonce_b64", "aad_sha256",
        ):
            if not str(getattr(self, field_name)).strip():
                raise MemorySyncContractError(f"{field_name} is required")
        ciphertext = strict_b64decode(self.ciphertext_b64, "ciphertext_b64")
        if hashlib.sha256(ciphertext).hexdigest() != self.ciphertext_sha256:
            raise MemorySyncContractError("ciphertext_sha256 mismatch")
        strict_b64decode(self.nonce_b64, "nonce_b64")
        if self.aad_sha256 != hashlib.sha256(self.aad_bytes()).hexdigest():
            raise MemorySyncContractError("aad_sha256 mismatch")

    def aad_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "stream_id": self.stream_id,
            "event_id": self.event_id,
            "idempotency_key": self.idempotency_key,
            "device_id": self.device_id,
            "device_seq": self.device_seq,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "aggregate_revision": self.aggregate_revision,
            "parent_event_id": self.parent_event_id,
            "turn_id": self.turn_id,
            "thought_id": self.thought_id,
            "payload_codec": self.payload_codec,
            "key_version": self.key_version,
            "created_at_utc": utc_iso(self.created_at_utc),
            "previous_device_event_sha256": self.previous_device_event_sha256,
        }

    def aad_bytes(self) -> bytes:
        return canonical_json_bytes(self.aad_dict())

    def ciphertext_bytes(self) -> bytes:
        return strict_b64decode(self.ciphertext_b64, "ciphertext_b64")

    def nonce_bytes(self) -> bytes:
        return strict_b64decode(self.nonce_b64, "nonce_b64")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at_utc"] = utc_iso(self.created_at_utc)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemorySyncEvent":
        return cls(
            schema_version=str(data.get("schema_version") or ""),
            stream_id=str(data.get("stream_id") or ""),
            event_id=str(data.get("event_id") or ""),
            idempotency_key=str(data.get("idempotency_key") or ""),
            device_id=str(data.get("device_id") or ""),
            device_seq=int(data.get("device_seq") or 0),
            event_type=str(data.get("event_type") or ""),
            aggregate_id=str(data.get("aggregate_id") or ""),
            aggregate_revision=int(data.get("aggregate_revision") or 0),
            parent_event_id=_none_or_str(data.get("parent_event_id")),
            turn_id=_none_or_str(data.get("turn_id")),
            thought_id=_none_or_str(data.get("thought_id")),
            payload_codec=str(data.get("payload_codec") or ""),
            ciphertext_b64=str(data.get("ciphertext_b64") or ""),
            ciphertext_sha256=str(data.get("ciphertext_sha256") or ""),
            key_version=int(data.get("key_version") or 0),
            nonce_b64=str(data.get("nonce_b64") or ""),
            aad_sha256=str(data.get("aad_sha256") or ""),
            created_at_utc=parse_utc(str(data.get("created_at_utc") or "")),
            previous_device_event_sha256=_none_or_str(data.get("previous_device_event_sha256")),
        )


@dataclass(slots=True, frozen=True)
class MemorySyncReceipt:
    stream_id: str
    event_id: str
    idempotency_key: str
    status: MemorySyncReceiptStatus
    remote_seq: int | None
    ciphertext_sha256: str
    received_at_utc: datetime
    receipt_sha256: str = ""
    error_code: str | None = None
    schema_version: str = RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RECEIPT_SCHEMA_VERSION:
            raise MemorySyncContractError(f"unsupported receipt schema: {self.schema_version}")
        if self.status in {MemorySyncReceiptStatus.ACCEPTED, MemorySyncReceiptStatus.ALREADY_EXISTS}:
            if self.remote_seq is None or self.remote_seq < 1:
                raise MemorySyncContractError("successful receipt requires positive remote_seq")
        if self.received_at_utc.tzinfo is None:
            raise MemorySyncContractError("received_at_utc must be timezone-aware")
        expected = self.compute_receipt_sha256()
        if self.receipt_sha256 and self.receipt_sha256 != expected:
            raise MemorySyncContractError("receipt_sha256 mismatch")
        if not self.receipt_sha256:
            object.__setattr__(self, "receipt_sha256", expected)

    def hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "stream_id": self.stream_id,
            "event_id": self.event_id,
            "idempotency_key": self.idempotency_key,
            "status": self.status.value,
            "remote_seq": self.remote_seq,
            "ciphertext_sha256": self.ciphertext_sha256,
            "received_at_utc": utc_iso(self.received_at_utc),
            "error_code": self.error_code,
        }

    def compute_receipt_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.hash_payload())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.hash_payload(), "receipt_sha256": self.receipt_sha256}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemorySyncReceipt":
        return cls(
            schema_version=str(data.get("schema_version") or ""),
            stream_id=str(data.get("stream_id") or ""),
            event_id=str(data.get("event_id") or ""),
            idempotency_key=str(data.get("idempotency_key") or ""),
            status=MemorySyncReceiptStatus(str(data.get("status") or "")),
            remote_seq=int(data["remote_seq"]) if data.get("remote_seq") is not None else None,
            ciphertext_sha256=str(data.get("ciphertext_sha256") or ""),
            received_at_utc=parse_utc(str(data.get("received_at_utc") or "")),
            receipt_sha256=str(data.get("receipt_sha256") or ""),
            error_code=_none_or_str(data.get("error_code")),
        )


@dataclass(slots=True, frozen=True)
class MemorySyncCursor:
    stream_id: str
    remote_seq: int = 0
    updated_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.stream_id.strip():
            raise MemorySyncContractError("stream_id is required")
        if self.remote_seq < 0:
            raise MemorySyncContractError("remote_seq cannot be negative")
        if self.updated_at_utc.tzinfo is None:
            raise MemorySyncContractError("updated_at_utc must be timezone-aware")


@dataclass(slots=True, frozen=True)
class MemorySyncStatus:
    configured: bool
    mode: MemorySyncMode
    stream_id: str | None
    device_id: str | None
    backend_ready: bool
    crypto_ready: bool
    outbox_pending: int
    outbox_failed: int
    inbox_pending: int
    conflict_count: int
    local_cursor: int
    last_push_at_utc: datetime | None = None
    last_pull_at_utc: datetime | None = None
    last_error: str | None = None
    truth_boundary: str = (
        "Cloud sync readiness never proves local runtime or continuity readiness; local commits remain authoritative "
        "for the active runtime until a separately verified restore/promotion policy says otherwise."
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        for key in ("last_push_at_utc", "last_pull_at_utc"):
            value = data[key]
            data[key] = utc_iso(value) if isinstance(value, datetime) else None
        return data


@dataclass(slots=True, frozen=True)
class MemorySnapshotChunk:
    object_id: str
    logical_path: str
    chunk_index: int
    ciphertext_sha256: str
    plaintext_sha256: str
    compressed_size: int
    plaintext_size: int
    key_version: int
    nonce_b64: str
    codec: str = "zlib"
    aad_sha256: str = ""

    def __post_init__(self) -> None:
        if self.chunk_index < 0:
            raise MemorySyncContractError("snapshot chunk_index cannot be negative")
        if min(self.compressed_size, self.plaintext_size, self.key_version) < 1:
            raise MemorySyncContractError("snapshot chunk sizes and key_version must be positive")
        if self.codec != "zlib":
            raise MemorySyncContractError(f"unsupported snapshot chunk codec: {self.codec}")


@dataclass(slots=True, frozen=True)
class MemorySnapshotManifest:
    snapshot_id: str
    stream_id: str
    created_at_utc: datetime
    source_memory_generation: str
    base_remote_seq: int
    event_chain_head_sha256: str | None
    chunks: tuple[MemorySnapshotChunk, ...]
    database_identity: Mapping[str, Any]
    schema_version: str = SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise MemorySyncContractError(f"unsupported snapshot schema: {self.schema_version}")
        if not self.snapshot_id.strip() or not self.stream_id.strip() or not self.source_memory_generation.strip():
            raise MemorySyncContractError("snapshot_id, stream_id and source_memory_generation are required")
        if self.base_remote_seq < 0:
            raise MemorySyncContractError("base_remote_seq cannot be negative")
        if self.created_at_utc.tzinfo is None:
            raise MemorySyncContractError("created_at_utc must be timezone-aware")
        if not self.chunks:
            raise MemorySyncContractError("snapshot manifest must contain at least one chunk")
        paths = [chunk.logical_path for chunk in self.chunks]
        if any(not path.strip() or _unsafe_relative_path(path) for path in paths):
            raise MemorySyncContractError("snapshot manifest contains unsafe logical path")
        object.__setattr__(self, "database_identity", dict(self.database_identity))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "stream_id": self.stream_id,
            "created_at_utc": utc_iso(self.created_at_utc),
            "source_memory_generation": self.source_memory_generation,
            "base_remote_seq": self.base_remote_seq,
            "event_chain_head_sha256": self.event_chain_head_sha256,
            "chunks": [asdict(chunk) for chunk in self.chunks],
            "database_identity": dict(self.database_identity),
        }

    def manifest_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemorySnapshotManifest":
        raw_chunks = data.get("chunks")
        raw_identity = data.get("database_identity")
        if not isinstance(raw_chunks, list):
            raise MemorySyncContractError("snapshot manifest chunks must be a list")
        if not isinstance(raw_identity, Mapping):
            raise MemorySyncContractError("snapshot manifest database_identity must be an object")
        chunks: list[MemorySnapshotChunk] = []
        for item in raw_chunks:
            if not isinstance(item, Mapping):
                raise MemorySyncContractError("snapshot manifest chunk must be an object")
            chunks.append(MemorySnapshotChunk(
                object_id=str(item.get("object_id") or ""),
                logical_path=str(item.get("logical_path") or ""),
                chunk_index=int(item.get("chunk_index") if item.get("chunk_index") is not None else -1),
                ciphertext_sha256=str(item.get("ciphertext_sha256") or ""),
                plaintext_sha256=str(item.get("plaintext_sha256") or ""),
                compressed_size=int(item.get("compressed_size") or 0),
                plaintext_size=int(item.get("plaintext_size") or 0),
                key_version=int(item.get("key_version") or 0),
                nonce_b64=str(item.get("nonce_b64") or ""),
                codec=str(item.get("codec") or ""),
                aad_sha256=str(item.get("aad_sha256") or ""),
            ))
        return cls(
            schema_version=str(data.get("schema_version") or ""),
            snapshot_id=str(data.get("snapshot_id") or ""),
            stream_id=str(data.get("stream_id") or ""),
            created_at_utc=parse_utc(str(data.get("created_at_utc") or "")),
            source_memory_generation=str(data.get("source_memory_generation") or ""),
            base_remote_seq=int(data.get("base_remote_seq") or 0),
            event_chain_head_sha256=_none_or_str(data.get("event_chain_head_sha256")),
            chunks=tuple(chunks),
            database_identity=dict(raw_identity),
        )


class MemorySyncBatch:
    """Validated immutable batch with explicit size and ordering limits."""

    def __init__(self, events: Iterable[MemorySyncEvent], *, max_events: int = 100, max_wire_bytes: int = 2_000_000) -> None:
        values = tuple(events)
        if not values:
            raise MemorySyncContractError("sync batch cannot be empty")
        if len(values) > max_events:
            raise MemorySyncContractError("sync batch exceeds max_events")
        stream_ids = {item.stream_id for item in values}
        if len(stream_ids) != 1:
            raise MemorySyncContractError("all batch events must belong to one stream")
        if len({item.event_id for item in values}) != len(values):
            raise MemorySyncContractError("sync batch contains duplicate event_id")
        wire_size = sum(len(canonical_json_bytes(item.to_dict())) for item in values)
        if wire_size > max_wire_bytes:
            raise MemorySyncContractError("sync batch exceeds max_wire_bytes")
        self.events = tuple(sorted(values, key=lambda item: (item.device_seq, item.event_id)))
        self.stream_id = self.events[0].stream_id
        self.wire_size = wire_size

    def to_dict(self) -> dict[str, Any]:
        return {"stream_id": self.stream_id, "events": [event.to_dict() for event in self.events]}


def _unsafe_relative_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("~"):
        return True
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    return not parts or ".." in parts or ":" in parts[0]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise MemorySyncContractError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def parse_utc(value: str) -> datetime:
    if not value:
        raise MemorySyncContractError("UTC timestamp is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise MemorySyncContractError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def strict_b64decode(value: str, field_name: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise MemorySyncContractError(f"invalid base64 in {field_name}") from exc


def b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _none_or_str(value: Any) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "EVENT_SCHEMA_VERSION",
    "MemoryInboxStatus",
    "MemorySnapshotChunk",
    "MemorySnapshotManifest",
    "MemorySyncBatch",
    "MemorySyncContractError",
    "MemorySyncCursor",
    "MemorySyncEvent",
    "MemorySyncMode",
    "MemorySyncPlainEvent",
    "MemorySyncReceipt",
    "MemorySyncReceiptStatus",
    "MemorySyncStatus",
    "SNAPSHOT_SCHEMA_VERSION",
    "b64encode",
    "canonical_json_bytes",
    "parse_utc",
    "strict_b64decode",
    "utc_iso",
]
