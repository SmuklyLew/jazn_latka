from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Protocol, Sequence
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest
import json
import ssl
import threading

from latka_jazn.memory.memory_sync_contracts import (
    MemorySnapshotManifest,
    MemorySyncBatch,
    MemorySyncContractError,
    MemorySyncEvent,
    MemorySyncReceipt,
    MemorySyncReceiptStatus,
    canonical_json_bytes,
)


class MemorySyncBackendError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class MemorySyncBackendStatus:
    ready: bool
    backend_id: str
    endpoint: str | None = None
    remote_seq: int | None = None
    latest_snapshot_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "backend_id": self.backend_id,
            "endpoint": self.endpoint,
            "remote_seq": self.remote_seq,
            "latest_snapshot_id": self.latest_snapshot_id,
            "error": self.error,
        }


class MemorySyncBackend(Protocol):
    def status(self, *, stream_id: str) -> MemorySyncBackendStatus: ...
    def push_events(self, batch: MemorySyncBatch) -> Sequence[MemorySyncReceipt]: ...
    def pull_events(self, *, stream_id: str, after_remote_seq: int, limit: int = 100) -> Sequence[tuple[int, MemorySyncEvent]]: ...


class MemorySnapshotBackend(Protocol):
    def put_object(self, *, object_id: str, data: bytes) -> None: ...
    def get_object(self, *, object_id: str) -> bytes: ...
    def commit_snapshot(self, manifest: MemorySnapshotManifest) -> None: ...
    def latest_snapshot(self, *, stream_id: str) -> MemorySnapshotManifest | None: ...


class InMemoryMemorySyncBackend(MemorySyncBackend, MemorySnapshotBackend):
    """Deterministic reference backend used for local verification and fault injection.

    It models the protocol invariants of a transactional gateway: event identity is
    immutable, retries are idempotent, remote sequence numbers are monotonic per
    stream, and snapshots are committed only after all referenced objects exist.
    """

    backend_id = "in_memory_reference"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: dict[str, list[tuple[int, MemorySyncEvent]]] = {}
        self._by_event_id: dict[tuple[str, str], tuple[int, MemorySyncEvent]] = {}
        self._by_idempotency: dict[tuple[str, str], tuple[int, MemorySyncEvent]] = {}
        self._objects: dict[str, bytes] = {}
        self._snapshots: dict[str, list[MemorySnapshotManifest]] = {}
        self._leases: dict[str, tuple[str, str, datetime]] = {}
        self.fail_next_push: str | None = None
        self.fail_next_pull: str | None = None

    def status(self, *, stream_id: str) -> MemorySyncBackendStatus:
        with self._lock:
            values = self._events.get(stream_id, [])
            snapshots = self._snapshots.get(stream_id, [])
            return MemorySyncBackendStatus(
                ready=True,
                backend_id=self.backend_id,
                remote_seq=values[-1][0] if values else 0,
                latest_snapshot_id=snapshots[-1].snapshot_id if snapshots else None,
            )

    def push_events(self, batch: MemorySyncBatch) -> Sequence[MemorySyncReceipt]:
        with self._lock:
            if self.fail_next_push:
                message = self.fail_next_push
                self.fail_next_push = None
                raise MemorySyncBackendError(message)
            receipts: list[MemorySyncReceipt] = []
            stream_events = self._events.setdefault(batch.stream_id, [])
            for event in batch.events:
                by_event = self._by_event_id.get((event.stream_id, event.event_id))
                by_key = self._by_idempotency.get((event.stream_id, event.idempotency_key))
                existing = by_event or by_key
                if existing is not None:
                    remote_seq, stored = existing
                    if (
                        stored.event_id != event.event_id
                        or stored.idempotency_key != event.idempotency_key
                        or stored.ciphertext_sha256 != event.ciphertext_sha256
                    ):
                        receipts.append(self._receipt(event, MemorySyncReceiptStatus.REJECTED, None, "identity_hash_conflict"))
                        continue
                    receipts.append(self._receipt(event, MemorySyncReceiptStatus.ALREADY_EXISTS, remote_seq, None))
                    continue
                remote_seq = len(stream_events) + 1
                stream_events.append((remote_seq, event))
                self._by_event_id[(event.stream_id, event.event_id)] = (remote_seq, event)
                self._by_idempotency[(event.stream_id, event.idempotency_key)] = (remote_seq, event)
                receipts.append(self._receipt(event, MemorySyncReceiptStatus.ACCEPTED, remote_seq, None))
            return tuple(receipts)

    def pull_events(self, *, stream_id: str, after_remote_seq: int, limit: int = 100) -> Sequence[tuple[int, MemorySyncEvent]]:
        with self._lock:
            if self.fail_next_pull:
                message = self.fail_next_pull
                self.fail_next_pull = None
                raise MemorySyncBackendError(message)
            if after_remote_seq < 0:
                raise MemorySyncContractError("after_remote_seq cannot be negative")
            bounded = max(1, min(int(limit), 1000))
            return tuple((seq, event) for seq, event in self._events.get(stream_id, []) if seq > after_remote_seq)[:bounded]

    def acquire_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token: str, ttl_seconds: int = 120
    ) -> dict[str, Any]:
        return self._set_lease(stream_id=stream_id, device_id=device_id, lease_token=lease_token, ttl_seconds=ttl_seconds, renew=False)

    def renew_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token: str, ttl_seconds: int = 120
    ) -> dict[str, Any]:
        return self._set_lease(stream_id=stream_id, device_id=device_id, lease_token=lease_token, ttl_seconds=ttl_seconds, renew=True)

    def release_writer_lease(self, *, stream_id: str, device_id: str, lease_token: str) -> dict[str, Any]:
        with self._lock:
            current = self._leases.get(stream_id)
            released = bool(current and current[0] == device_id and current[1] == lease_token)
            if released:
                del self._leases[stream_id]
        return {"stream_id": stream_id, "device_id": device_id, "released": released}

    def _set_lease(
        self, *, stream_id: str, device_id: str, lease_token: str, ttl_seconds: int, renew: bool
    ) -> dict[str, Any]:
        if not stream_id.strip() or not device_id.strip() or len(lease_token.strip()) < 32:
            raise MemorySyncContractError("writer lease requires stream, device and a token with at least 32 characters")
        now = datetime.now(timezone.utc)
        ttl = max(10, min(int(ttl_seconds), 3600))
        with self._lock:
            current = self._leases.get(stream_id)
            if renew:
                if current is None or current[0] != device_id or current[1] != lease_token:
                    raise MemorySyncBackendError("writer lease cannot be renewed by a different owner")
            elif current is not None and current[2] > now and (current[0], current[1]) != (device_id, lease_token):
                raise MemorySyncBackendError("memory stream already has an active writer lease")
            expires = now + timedelta(seconds=ttl)
            self._leases[stream_id] = (device_id, lease_token, expires)
        return {
            "stream_id": stream_id, "device_id": device_id,
            "expires_at_utc": expires.isoformat().replace("+00:00", "Z"), "active": True,
        }

    def put_object(self, *, object_id: str, data: bytes) -> None:
        if not object_id.strip():
            raise MemorySyncContractError("object_id is required")
        with self._lock:
            existing = self._objects.get(object_id)
            if existing is not None and existing != data:
                raise MemorySyncBackendError("immutable object id already exists with different bytes")
            self._objects[object_id] = bytes(data)

    def get_object(self, *, object_id: str) -> bytes:
        with self._lock:
            try:
                return bytes(self._objects[object_id])
            except KeyError as exc:
                raise MemorySyncBackendError(f"snapshot object not found: {object_id}") from exc

    def commit_snapshot(self, manifest: MemorySnapshotManifest) -> None:
        with self._lock:
            missing = [chunk.object_id for chunk in manifest.chunks if chunk.object_id not in self._objects]
            if missing:
                raise MemorySyncBackendError(f"snapshot references missing objects: {missing[:3]}")
            snapshots = self._snapshots.setdefault(manifest.stream_id, [])
            for existing in snapshots:
                if existing.snapshot_id == manifest.snapshot_id:
                    if existing.manifest_sha256() != manifest.manifest_sha256():
                        raise MemorySyncBackendError("snapshot id collision with different manifest")
                    return
            snapshots.append(manifest)
            snapshots.sort(key=lambda item: (item.created_at_utc, item.snapshot_id))

    def latest_snapshot(self, *, stream_id: str) -> MemorySnapshotManifest | None:
        with self._lock:
            values = self._snapshots.get(stream_id, [])
            return values[-1] if values else None

    @staticmethod
    def _receipt(
        event: MemorySyncEvent,
        status: MemorySyncReceiptStatus,
        remote_seq: int | None,
        error_code: str | None,
    ) -> MemorySyncReceipt:
        return MemorySyncReceipt(
            stream_id=event.stream_id,
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
            status=status,
            remote_seq=remote_seq,
            ciphertext_sha256=event.ciphertext_sha256,
            received_at_utc=datetime.now(timezone.utc),
            error_code=error_code,
        )


class HttpMemorySyncBackend(MemorySyncBackend, MemorySnapshotBackend):
    """Strict HTTPS client for a provider-neutral memory gateway.

    The client does not know PostgreSQL, S3, or provider credentials. Its only
    responsibility is the authenticated encrypted event protocol. Plaintext memory
    is never accepted by this class.
    """

    backend_id = "http_memory_gateway"

    def __init__(
        self,
        endpoint: str,
        *,
        bearer_token: str,
        timeout_seconds: float = 10.0,
        allow_insecure_loopback: bool = False,
        ssl_context: ssl.SSLContext | None = None,
        user_agent: str = "LatkaJazn-MemorySync/1",
        max_json_response_bytes: int = 4 * 1024 * 1024,
        max_object_bytes: int = 32 * 1024 * 1024,
        writer_lease_token: str | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        parsed = urlparse.urlparse(self.endpoint)
        if parsed.scheme != "https":
            loopback = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            if not (allow_insecure_loopback and loopback):
                raise MemorySyncContractError("memory cloud endpoint must use HTTPS")
        if not bearer_token.strip():
            raise MemorySyncContractError("memory cloud bearer token is required")
        self.bearer_token = bearer_token
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.ssl_context = ssl_context or ssl.create_default_context()
        self.user_agent = user_agent
        self.max_json_response_bytes = max(64 * 1024, min(int(max_json_response_bytes), 64 * 1024 * 1024))
        self.max_object_bytes = max(64 * 1024, min(int(max_object_bytes), 128 * 1024 * 1024))
        self.writer_lease_token = writer_lease_token.strip() if writer_lease_token else None

    def status(self, *, stream_id: str) -> MemorySyncBackendStatus:
        try:
            payload = self._request("GET", f"/v1/memory/status?stream_id={urlparse.quote(stream_id)}")
            return MemorySyncBackendStatus(
                ready=bool(payload.get("ready", True)),
                backend_id=self.backend_id,
                endpoint=self.endpoint,
                remote_seq=int(payload.get("remote_seq") or 0),
                latest_snapshot_id=str(payload["latest_snapshot_id"]) if payload.get("latest_snapshot_id") else None,
                error=str(payload["error"]) if payload.get("error") else None,
            )
        except Exception as exc:
            return MemorySyncBackendStatus(False, self.backend_id, endpoint=self.endpoint, error=f"{type(exc).__name__}: {exc}")

    def push_events(self, batch: MemorySyncBatch) -> Sequence[MemorySyncReceipt]:
        payload = self._request(
            "POST", "/v1/memory/events:batch", body=batch.to_dict(),
            extra_headers={"X-Jazn-Writer-Lease": self.writer_lease_token} if self.writer_lease_token else None,
        )
        raw = payload.get("receipts")
        if not isinstance(raw, list):
            raise MemorySyncBackendError("gateway response does not contain receipts list")
        receipts = tuple(MemorySyncReceipt.from_dict(item) for item in raw if isinstance(item, dict))
        if len(receipts) != len(batch.events):
            raise MemorySyncBackendError("gateway returned a different number of receipts than events")
        return receipts

    def pull_events(self, *, stream_id: str, after_remote_seq: int, limit: int = 100) -> Sequence[tuple[int, MemorySyncEvent]]:
        bounded = max(1, min(int(limit), 1000))
        path = (
            f"/v1/memory/events?stream_id={urlparse.quote(stream_id)}"
            f"&after={int(after_remote_seq)}&limit={bounded}"
        )
        payload = self._request("GET", path)
        raw = payload.get("events")
        if not isinstance(raw, list):
            raise MemorySyncBackendError("gateway response does not contain events list")
        values: list[tuple[int, MemorySyncEvent]] = []
        previous = int(after_remote_seq)
        for item in raw:
            if not isinstance(item, dict):
                raise MemorySyncBackendError("gateway event item must be an object")
            remote_seq = int(item.get("remote_seq") or 0)
            event_data = item.get("event")
            if remote_seq <= previous:
                raise MemorySyncBackendError("gateway returned non-monotonic remote_seq")
            if not isinstance(event_data, dict):
                raise MemorySyncBackendError("gateway event payload is missing")
            values.append((remote_seq, MemorySyncEvent.from_dict(event_data)))
            previous = remote_seq
        return tuple(values)

    def acquire_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token: str, ttl_seconds: int = 120
    ) -> dict[str, Any]:
        return self._request(
            "POST", "/v1/memory/writer-lease:acquire",
            body={"stream_id": stream_id, "device_id": device_id, "lease_token": lease_token, "ttl_seconds": ttl_seconds},
        )

    def renew_writer_lease(
        self, *, stream_id: str, device_id: str, lease_token: str, ttl_seconds: int = 120
    ) -> dict[str, Any]:
        return self._request(
            "POST", "/v1/memory/writer-lease:renew",
            body={"stream_id": stream_id, "device_id": device_id, "lease_token": lease_token, "ttl_seconds": ttl_seconds},
        )

    def release_writer_lease(self, *, stream_id: str, device_id: str, lease_token: str) -> dict[str, Any]:
        return self._request(
            "POST", "/v1/memory/writer-lease:release",
            body={"stream_id": stream_id, "device_id": device_id, "lease_token": lease_token},
        )

    def put_object(self, *, object_id: str, data: bytes) -> None:
        if len(data) > self.max_object_bytes:
            raise MemorySyncBackendError("snapshot object exceeds client safety limit")
        path = f"/v1/memory/objects/{urlparse.quote(object_id, safe='')}"
        self._request_bytes(
            "PUT", path, body=bytes(data), content_type="application/octet-stream",
            accept="application/json", max_response_bytes=self.max_json_response_bytes,
        )

    def get_object(self, *, object_id: str) -> bytes:
        path = f"/v1/memory/objects/{urlparse.quote(object_id, safe='')}"
        return self._request_bytes(
            "GET", path, accept="application/octet-stream", max_response_bytes=self.max_object_bytes,
        )

    def commit_snapshot(self, manifest: MemorySnapshotManifest) -> None:
        payload = self._request(
            "POST", "/v1/memory/snapshots:commit", body={"manifest": manifest.to_dict()}
        )
        if not bool(payload.get("committed")):
            raise MemorySyncBackendError("gateway did not confirm snapshot commit")
        if str(payload.get("snapshot_id") or "") != manifest.snapshot_id:
            raise MemorySyncBackendError("gateway confirmed a different snapshot id")

    def latest_snapshot(self, *, stream_id: str) -> MemorySnapshotManifest | None:
        path = f"/v1/memory/snapshots/latest?stream_id={urlparse.quote(stream_id)}"
        payload = self._request("GET", path)
        raw = payload.get("manifest")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise MemorySyncBackendError("gateway latest snapshot manifest must be an object or null")
        return MemorySnapshotManifest.from_dict(raw)

    def _request(
        self, method: str, path: str, *, body: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        raw = self._request_bytes(
            method, path, body=canonical_json_bytes(body) if body is not None else None,
            content_type="application/json" if body is not None else None,
            accept="application/json", max_response_bytes=self.max_json_response_bytes,
            extra_headers=extra_headers,
        )
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MemorySyncBackendError("memory gateway returned invalid UTF-8 JSON") from exc
        if not isinstance(decoded, dict):
            raise MemorySyncBackendError("memory gateway response must be a JSON object")
        return decoded

    def _request_bytes(
        self, method: str, path: str, *, body: bytes | None = None,
        content_type: str | None = None, accept: str, max_response_bytes: int,
        extra_headers: Mapping[str, str] | None = None,
    ) -> bytes:
        url = f"{self.endpoint}{path}"
        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {self.bearer_token}",
            "User-Agent": self.user_agent,
        }
        if content_type is not None:
            headers["Content-Type"] = content_type
        if extra_headers:
            for key, value in extra_headers.items():
                if value:
                    headers[str(key)] = str(value)
        request = urlrequest.Request(url, data=body, headers=headers, method=method)
        try:
            with urlrequest.urlopen(request, timeout=self.timeout_seconds, context=self.ssl_context) as response:
                raw = response.read(max_response_bytes + 1)
                if len(raw) > max_response_bytes:
                    raise MemorySyncBackendError("gateway response exceeds configured safety limit")
        except urlerror.HTTPError as exc:
            detail = exc.read(64 * 1024).decode("utf-8", errors="replace")
            raise MemorySyncBackendError(f"memory gateway HTTP {exc.code}: {detail[:1000]}") from exc
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            raise MemorySyncBackendError(f"memory gateway request failed: {exc}") from exc
        return raw


__all__ = [
    "HttpMemorySyncBackend",
    "InMemoryMemorySyncBackend",
    "MemorySnapshotBackend",
    "MemorySyncBackend",
    "MemorySyncBackendError",
    "MemorySyncBackendStatus",
]
