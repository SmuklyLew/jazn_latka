from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from threading import Thread
from wsgiref.simple_server import WSGIRequestHandler, make_server
import base64
import hashlib

import pytest

from latka_jazn.memory.memory_cloud_gateway import (
    InMemoryMemoryCloudRepository,
    MemoryCloudGatewayService,
    MemoryCloudGatewayWSGIApplication,
    MemoryCloudRepositoryError,
)
from latka_jazn.memory.memory_sync_backend import HttpMemorySyncBackend
from latka_jazn.memory.memory_sync_contracts import (
    MemorySnapshotChunk,
    MemorySnapshotManifest,
    MemorySyncBatch,
    MemorySyncEvent,
    MemorySyncPlainEvent,
    MemorySyncReceiptStatus,
    canonical_json_bytes,
)

NOW = datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc)
TOKEN = "gateway-test-token-that-is-not-a-production-secret"


class MemoryObjectStore:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def put_immutable(self, *, object_id: str, data: bytes) -> None:
        previous = self.values.get(object_id)
        if previous is not None and previous != data:
            raise MemoryCloudRepositoryError("immutable object collision")
        self.values[object_id] = bytes(data)

    def get(self, *, object_id: str) -> bytes:
        try:
            return self.values[object_id]
        except KeyError as exc:
            raise MemoryCloudRepositoryError("object not found") from exc

    def exists(self, *, object_id: str) -> bool:
        return object_id in self.values


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib override name
        return None


@contextmanager
def running_gateway(*, require_writer_lease: bool = False):
    repository = InMemoryMemoryCloudRepository()
    object_store = MemoryObjectStore()
    service = MemoryCloudGatewayService(
        repository=repository,
        object_store=object_store,
        require_writer_lease=require_writer_lease,
    )
    app = MemoryCloudGatewayWSGIApplication(service, bearer_tokens=[TOKEN])
    server = make_server("127.0.0.1", 0, app, handler_class=QuietHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        yield repository, object_store, HttpMemorySyncBackend(
            endpoint,
            bearer_token=TOKEN,
            allow_insecure_loopback=True,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def wire_event(*, event_id: str = "event-1", device_id: str = "device-1") -> MemorySyncEvent:
    plain = MemorySyncPlainEvent(
        stream_id="stream-1",
        event_id=event_id,
        idempotency_key=f"idem:{event_id}",
        device_id=device_id,
        device_seq=1,
        event_type="memory.runtime_turn_staged",
        aggregate_id="memory-1",
        aggregate_revision=1,
        payload={"private": "ciphertext placeholder"},
        created_at_utc=NOW,
    )
    ciphertext = b"encrypted-placeholder"
    nonce = b"n" * 24
    aad = canonical_json_bytes(plain.aad(key_version=1))
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
        key_version=1,
        nonce_b64=base64.b64encode(nonce).decode("ascii"),
        aad_sha256=hashlib.sha256(aad).hexdigest(),
        created_at_utc=NOW,
    )


def snapshot_manifest(*, object_id: str, data: bytes) -> MemorySnapshotManifest:
    digest = hashlib.sha256(data).hexdigest()
    chunk = MemorySnapshotChunk(
        object_id=object_id,
        logical_path="memory/sqlite/memory.sqlite3",
        chunk_index=0,
        ciphertext_sha256=digest,
        plaintext_sha256="a" * 64,
        compressed_size=1,
        plaintext_size=1,
        key_version=1,
        nonce_b64=base64.b64encode(b"n" * 24).decode("ascii"),
        aad_sha256="b" * 64,
    )
    return MemorySnapshotManifest(
        snapshot_id="snapshot-1",
        stream_id="stream-1",
        base_remote_seq=0,
        created_at_utc=NOW,
        source_memory_generation="generation-1",
        event_chain_head_sha256=None,
        chunks=(chunk,),
        database_identity={"memory/sqlite/memory.sqlite3": {"sha256": "c" * 64}},
    )


def test_http_gateway_round_trips_encrypted_events_and_status() -> None:
    with running_gateway() as (_, _, backend):
        event = wire_event()
        receipts = backend.push_events(MemorySyncBatch((event,)))
        assert len(receipts) == 1
        assert receipts[0].status is MemorySyncReceiptStatus.ACCEPTED
        assert receipts[0].remote_seq == 1
        replay = backend.push_events(MemorySyncBatch((event,)))
        assert replay[0].status is MemorySyncReceiptStatus.ALREADY_EXISTS
        values = backend.pull_events(stream_id="stream-1", after_remote_seq=0)
        assert values == ((1, event),)
        status = backend.status(stream_id="stream-1")
        assert status.ready is True
        assert status.remote_seq == 1


def test_http_gateway_snapshot_transport_is_immutable_and_manifest_commits_last() -> None:
    data = b"encrypted-snapshot-object"
    object_id = "objects/" + hashlib.sha256(data).hexdigest()
    manifest = snapshot_manifest(object_id=object_id, data=data)
    with running_gateway() as (_, _, backend):
        with pytest.raises(Exception):
            backend.commit_snapshot(manifest)
        backend.put_object(object_id=object_id, data=data)
        backend.commit_snapshot(manifest)
        assert backend.get_object(object_id=object_id) == data
        assert backend.latest_snapshot(stream_id="stream-1") == manifest
        assert backend.status(stream_id="stream-1").latest_snapshot_id == manifest.snapshot_id


def test_gateway_writer_lease_blocks_other_device_when_enforced() -> None:
    lease_token = "l" * 48
    with running_gateway(require_writer_lease=True) as (_, _, backend):
        event = wire_event(device_id="device-1")
        with pytest.raises(Exception):
            backend.push_events(MemorySyncBatch((event,)))
        lease = backend.acquire_writer_lease(
            stream_id="stream-1", device_id="device-1", lease_token=lease_token, ttl_seconds=60
        )
        assert lease["active"] is True
        leased_backend = HttpMemorySyncBackend(
            backend.endpoint,
            bearer_token=TOKEN,
            allow_insecure_loopback=True,
            writer_lease_token=lease_token,
        )
        assert leased_backend.push_events(MemorySyncBatch((event,)))[0].status is MemorySyncReceiptStatus.ACCEPTED
        with pytest.raises(Exception):
            backend.acquire_writer_lease(
                stream_id="stream-1", device_id="device-2", lease_token="x" * 48, ttl_seconds=60
            )
        assert leased_backend.renew_writer_lease(
            stream_id="stream-1", device_id="device-1", lease_token=lease_token, ttl_seconds=60
        )["active"] is True
        assert leased_backend.release_writer_lease(
            stream_id="stream-1", device_id="device-1", lease_token=lease_token
        )["released"] is True


def test_wsgi_gateway_rejects_missing_auth_without_calling_service() -> None:
    service = MemoryCloudGatewayService(repository=InMemoryMemoryCloudRepository())
    app = MemoryCloudGatewayWSGIApplication(service, bearer_tokens=[TOKEN])
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = app(
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/v1/memory/status",
            "QUERY_STRING": "stream_id=stream-1",
            "wsgi.input": BytesIO(b""),
            "CONTENT_LENGTH": "0",
        },
        start_response,
    )
    assert str(captured["status"]).startswith("401")
    assert b"unauthorized" in body[0]
