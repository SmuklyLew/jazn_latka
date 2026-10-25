from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_sync_backend import HttpMemorySyncBackend, MemorySyncBackendStatus
from latka_jazn.memory.memory_sync_contracts import MemorySyncContractError, MemorySyncMode
from latka_jazn.memory.memory_sync_crypto import (
    EnvironmentMemoryKeyProvider,
    MemoryCryptoUnavailable,
    PyNaClXChaCha20Poly1305Provider,
)
from latka_jazn.memory.memory_sync_worker import CloudMemorySyncWorker, MemorySyncWorkerConfig, MemorySyncWorkerResult
from latka_jazn.memory.memory_tier_store import MemoryTierStore


@dataclass(slots=True, frozen=True)
class MemorySyncRuntimeConfig:
    """Resolved operator configuration for optional cloud replication.

    Cloud sync is deliberately opt-in. An empty endpoint/stream/device while mode is
    ``off`` is a valid local-only configuration. When sync is enabled all identity
    fields and the bearer-token environment variable must resolve before any network
    request is attempted.
    """

    mode: MemorySyncMode
    endpoint: str
    stream_id: str
    device_id: str
    bearer_token_env: str
    timeout_seconds: float
    push_batch_size: int
    pull_batch_size: int
    max_batch_wire_bytes: int
    stale_claim_seconds: int
    retry_base_seconds: float
    retry_max_seconds: float
    retry_jitter_fraction: float
    allow_loopback_http: bool = False
    writer_lease_enabled: bool = True
    writer_lease_token_env: str = "JAZN_MEMORY_WRITER_LEASE_TOKEN"
    writer_lease_ttl_seconds: int = 120

    @classmethod
    def from_jazn_config(cls, cfg: JaznConfig) -> "MemorySyncRuntimeConfig":
        try:
            mode = MemorySyncMode(cfg.memory_sync_mode)
        except ValueError as exc:
            raise MemorySyncContractError(f"unsupported JAZN_MEMORY_SYNC_MODE: {cfg.memory_sync_mode!r}") from exc
        return cls(
            mode=mode,
            endpoint=cfg.memory_sync_endpoint.strip().rstrip("/"),
            stream_id=cfg.memory_sync_stream_id.strip(),
            device_id=cfg.memory_sync_device_id.strip(),
            bearer_token_env=cfg.memory_sync_bearer_token_env.strip(),
            timeout_seconds=max(1.0, float(cfg.memory_sync_timeout_seconds)),
            push_batch_size=max(1, int(cfg.memory_sync_push_batch_size)),
            pull_batch_size=max(1, int(cfg.memory_sync_pull_batch_size)),
            max_batch_wire_bytes=max(64 * 1024, int(cfg.memory_sync_max_batch_wire_bytes)),
            stale_claim_seconds=max(30, int(cfg.memory_sync_stale_claim_seconds)),
            retry_base_seconds=max(0.25, float(cfg.memory_sync_retry_base_seconds)),
            retry_max_seconds=max(float(cfg.memory_sync_retry_base_seconds), float(cfg.memory_sync_retry_max_seconds)),
            retry_jitter_fraction=min(1.0, max(0.0, float(cfg.memory_sync_retry_jitter_fraction))),
            allow_loopback_http=bool(cfg.memory_sync_allow_loopback_http),
            writer_lease_enabled=bool(cfg.memory_sync_writer_lease_enabled),
            writer_lease_token_env=cfg.memory_sync_writer_lease_token_env.strip(),
            writer_lease_ttl_seconds=max(10, min(int(cfg.memory_sync_writer_lease_ttl_seconds), 3600)),
        )

    @property
    def enabled(self) -> bool:
        return self.mode is not MemorySyncMode.OFF

    def missing_requirements(self) -> tuple[str, ...]:
        if not self.enabled:
            return ()
        missing: list[str] = []
        if not self.endpoint:
            missing.append("endpoint")
        if not self.stream_id:
            missing.append("stream_id")
        if not self.device_id:
            missing.append("device_id")
        if not self.bearer_token_env:
            missing.append("bearer_token_env")
        elif not os.environ.get(self.bearer_token_env, "").strip():
            missing.append(f"secret_env:{self.bearer_token_env}")
        if self.writer_lease_required:
            if not self.writer_lease_token_env:
                missing.append("writer_lease_token_env")
            elif len(os.environ.get(self.writer_lease_token_env, "").strip()) < 32:
                missing.append(f"secret_env:{self.writer_lease_token_env}")
        return tuple(missing)

    @property
    def writer_lease_required(self) -> bool:
        return bool(self.mode is MemorySyncMode.PUSH_PULL and self.writer_lease_enabled)

    def writer_lease_token(self) -> str | None:
        if not self.writer_lease_required:
            return None
        value = os.environ.get(self.writer_lease_token_env, "").strip()
        if len(value) < 32:
            return None
        return value

    def public_dict(self) -> dict[str, Any]:
        """Return non-secret operator diagnostics suitable for status/doctor output."""
        return {
            "mode": self.mode.value,
            "enabled": self.enabled,
            "endpoint": self.endpoint or None,
            "stream_id": self.stream_id or None,
            "device_id": self.device_id or None,
            "bearer_token_env": self.bearer_token_env or None,
            "bearer_token_present": bool(
                self.bearer_token_env and os.environ.get(self.bearer_token_env, "").strip()
            ),
            "missing_requirements": list(self.missing_requirements()),
            "timeout_seconds": self.timeout_seconds,
            "push_batch_size": self.push_batch_size,
            "pull_batch_size": self.pull_batch_size,
            "max_batch_wire_bytes": self.max_batch_wire_bytes,
            "allow_loopback_http": self.allow_loopback_http,
            "writer_lease_required": self.writer_lease_required,
            "writer_lease_token_env": self.writer_lease_token_env if self.writer_lease_required else None,
            "writer_lease_token_present": bool(self.writer_lease_token()),
            "writer_lease_ttl_seconds": self.writer_lease_ttl_seconds,
            "secret_material_exposed": False,
        }


class MemorySyncRuntime:
    """Lifecycle owner for optional local-first memory replication.

    This object is the single runtime boundary for cloud memory. It owns config
    resolution, crypto readiness, backend construction, explicit one-shot sync and
    non-blocking status. The rest of Jaźń can continue to use ``MemoryTierStore``
    without importing HTTP or crypto modules. There is intentionally no background
    thread here: scheduling belongs to the daemon/controller and local commits never
    wait on this runtime.
    """

    def __init__(self, cfg: JaznConfig) -> None:
        self.cfg = cfg
        self.runtime = MemorySyncRuntimeConfig.from_jazn_config(cfg)
        self.store_path = Path(cfg.memory_tier_db_path)

    def status(self, *, probe_remote: bool = False) -> dict[str, Any]:
        crypto = PyNaClXChaCha20Poly1305Provider()
        key_provider = EnvironmentMemoryKeyProvider()
        crypto_status = crypto.status()
        key_status = key_provider.status()
        crypto_ready = bool(crypto_status.get("ready")) and bool(key_status.get("ready"))
        configured = self.runtime.enabled and not self.runtime.missing_requirements()

        backend_status = MemorySyncBackendStatus(
            ready=False,
            backend_id="disabled" if not self.runtime.enabled else "not_probed",
            endpoint=self.runtime.endpoint or None,
            error=None if not self.runtime.enabled else "remote_probe_not_requested",
        )
        if probe_remote and configured:
            try:
                backend_status = self.build_backend().status(stream_id=self.runtime.stream_id)
            except Exception as exc:
                backend_status = MemorySyncBackendStatus(
                    ready=False,
                    backend_id="http_gateway",
                    endpoint=self.runtime.endpoint or None,
                    error=f"{type(exc).__name__}: {exc}",
                )

        local = self._read_local_replication_state(
            configured=configured,
            backend_ready=bool(backend_status.ready),
            crypto_ready=crypto_ready,
        )
        return {
            "schema_version": "jazn_memory_sync_runtime_status/v1",
            "configuration": self.runtime.public_dict(),
            "local_replication_state": local,
            "crypto": {
                "provider": crypto_status,
                "keys": key_status,
            },
            "backend": backend_status.to_dict(),
            "cloud_sync_configuration_ready": bool(configured and crypto_ready),
            "cloud_sync_ready": bool(configured and crypto_ready and backend_status.ready),
            "remote_probe_performed": bool(probe_remote),
            "local_memory_ready_independent_of_cloud": True,
            "truth_boundary": (
                "Cloud synchronization is optional durability/replication. Its readiness never proves or blocks "
                "the health of the local runtime, local memory, wake-state or continuity."
            ),
        }

    def _read_local_replication_state(
        self, *, configured: bool, backend_ready: bool, crypto_ready: bool
    ) -> dict[str, Any]:
        """Inspect sync ledgers without creating or migrating the local database."""
        base: dict[str, Any] = {
            "configured": configured, "mode": self.runtime.mode.value,
            "stream_id": None, "device_id": None, "backend_ready": backend_ready,
            "crypto_ready": crypto_ready, "outbox_pending": 0, "outbox_failed": 0,
            "inbox_pending": 0, "conflict_count": 0, "local_cursor": 0,
            "last_push_at_utc": None, "last_pull_at_utc": None, "last_error": None,
            "store_exists": self.store_path.is_file(), "sync_schema_present": False, "read_only": True,
        }
        if not self.store_path.is_file():
            return base
        uri = self.store_path.as_uri() + "?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True, timeout=5.0) as con:
                con.row_factory = sqlite3.Row
                tables = {str(row[0]) for row in con.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                ).fetchall()}
                required = {"memory_outbox", "memory_sync_state", "memory_sync_inbox", "memory_sync_conflicts"}
                if not required.issubset(tables):
                    base["schema_status"] = "sync_schema_not_initialized"
                    return base
                base["sync_schema_present"] = True
                state = con.execute("SELECT * FROM memory_sync_state WHERE state_id=1").fetchone()
                if state is not None:
                    base.update({
                        "stream_id": str(state["stream_id"]), "device_id": str(state["device_id"]),
                        "local_cursor": int(state["local_cursor"]), "last_push_at_utc": state["last_push_at_utc"],
                        "last_pull_at_utc": state["last_pull_at_utc"], "last_error": state["last_error"],
                    })
                base.update({
                    "outbox_pending": int(con.execute(
                        "SELECT COUNT(*) FROM memory_outbox WHERE status IN ('pending','processing')"
                    ).fetchone()[0]),
                    "outbox_failed": int(con.execute(
                        "SELECT COUNT(*) FROM memory_outbox WHERE status='failed'"
                    ).fetchone()[0]),
                    "inbox_pending": int(con.execute(
                        "SELECT COUNT(*) FROM memory_sync_inbox WHERE status='pending'"
                    ).fetchone()[0]),
                    "conflict_count": int(con.execute(
                        "SELECT COUNT(*) FROM memory_sync_conflicts WHERE resolved_at_utc IS NULL"
                    ).fetchone()[0]),
                    "schema_status": "ready",
                })
                return base
        except sqlite3.Error as exc:
            base["schema_status"] = "read_error"
            base["read_error"] = f"{type(exc).__name__}: {exc}"
            return base

    def sync_once(self) -> MemorySyncWorkerResult:
        if not self.runtime.enabled:
            return MemorySyncWorkerResult()
        missing = self.runtime.missing_requirements()
        if missing:
            raise MemorySyncContractError(
                "memory cloud sync is enabled but configuration is incomplete: " + ", ".join(missing)
            )
        key_provider = self.build_key_provider()
        key_status = key_provider.status()
        if not bool(key_status.get("ready")):
            raise MemoryCryptoUnavailable(str(key_status.get("error") or "memory encryption key is unavailable"))
        crypto = self.build_event_crypto()
        if not bool(crypto.status().get("ready")):
            raise MemoryCryptoUnavailable("PyNaCl/libsodium memory crypto provider is unavailable")
        backend = self.build_backend()
        if self.runtime.writer_lease_required:
            lease_token = self.runtime.writer_lease_token()
            if lease_token is None:
                raise MemorySyncContractError("writer lease is required but its secret is unavailable")
            backend.acquire_writer_lease(
                stream_id=self.runtime.stream_id,
                device_id=self.runtime.device_id,
                lease_token=lease_token,
                ttl_seconds=self.runtime.writer_lease_ttl_seconds,
            )
        worker = CloudMemorySyncWorker(
            store_path=str(self.store_path),
            backend=backend,
            crypto=crypto,
            key_provider=key_provider,
            config=MemorySyncWorkerConfig(
                stream_id=self.runtime.stream_id,
                device_id=self.runtime.device_id,
                mode=self.runtime.mode,
                push_batch_size=self.runtime.push_batch_size,
                pull_batch_size=self.runtime.pull_batch_size,
                max_batch_wire_bytes=self.runtime.max_batch_wire_bytes,
                stale_claim_seconds=self.runtime.stale_claim_seconds,
                retry_base_seconds=self.runtime.retry_base_seconds,
                retry_max_seconds=self.runtime.retry_max_seconds,
                retry_jitter_fraction=self.runtime.retry_jitter_fraction,
            ),
        )
        return worker.sync_once()

    def build_key_provider(self) -> EnvironmentMemoryKeyProvider:
        return EnvironmentMemoryKeyProvider()

    def build_event_crypto(self) -> PyNaClXChaCha20Poly1305Provider:
        return PyNaClXChaCha20Poly1305Provider()

    def build_backend(self) -> HttpMemorySyncBackend:
        """Build the configured encrypted gateway client after explicit validation."""
        if not self.runtime.enabled:
            raise MemorySyncContractError("memory cloud sync is disabled")
        missing = self.runtime.missing_requirements()
        if missing:
            raise MemorySyncContractError(
                "memory cloud sync configuration is incomplete: " + ", ".join(missing)
            )
        token = os.environ.get(self.runtime.bearer_token_env, "").strip()
        if not token:
            raise MemorySyncContractError(
                f"memory cloud token environment variable {self.runtime.bearer_token_env!r} is empty"
            )
        return HttpMemorySyncBackend(
            endpoint=self.runtime.endpoint,
            bearer_token=token,
            timeout_seconds=self.runtime.timeout_seconds,
            allow_insecure_loopback=self.runtime.allow_loopback_http,
            writer_lease_token=self.runtime.writer_lease_token(),
        )


__all__ = ["MemorySyncRuntime", "MemorySyncRuntimeConfig"]
