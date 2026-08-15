from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import hashlib
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon import status_daemon
from latka_jazn.memory.memory_snapshot_runtime import (
    MemorySnapshotCreateResult,
    MemorySnapshotPolicy,
    MemorySnapshotRestoreResult,
    SQLiteMemorySnapshotManager,
    SQLiteSnapshotSource,
)
from latka_jazn.memory.memory_sync_contracts import MemorySyncContractError
from latka_jazn.memory.memory_sync_crypto import PyNaClMemorySnapshotChunkCrypto
from latka_jazn.memory.memory_sync_runtime import MemorySyncRuntime


@dataclass(slots=True, frozen=True)
class MemoryCloudSnapshotPlan:
    profile: str
    sources: tuple[SQLiteSnapshotSource, ...]
    source_memory_generation: str
    base_remote_seq: int
    event_chain_head_sha256: str | None
    runtime_stopped: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "sources": [source.logical_path for source in self.sources],
            "source_memory_generation": self.source_memory_generation,
            "base_remote_seq": self.base_remote_seq,
            "event_chain_head_sha256": self.event_chain_head_sha256,
            "runtime_stopped": self.runtime_stopped,
        }


class MemoryCloudSnapshotRuntime:
    """Operator-facing owner for verified cloud snapshot and restore.

    Snapshotting is deliberately separate from hot-path event replication. A snapshot
    spans multiple SQLite files, so this controller requires the Jaźń daemon to be
    stopped before creating one. Each individual database is then copied through the
    SQLite Online Backup API by ``SQLiteMemorySnapshotManager``. Restore always lands
    in a fresh staging directory and is never promoted over an active memory root.
    """

    PROFILE_CORE = "core"
    PROFILE_ALL_SQLITE = "all-sqlite"

    def __init__(self, cfg: JaznConfig) -> None:
        self.cfg = cfg
        self.sync_runtime = MemorySyncRuntime(cfg)

    def plan(self, *, profile: str = PROFILE_CORE) -> MemoryCloudSnapshotPlan:
        if profile not in {self.PROFILE_CORE, self.PROFILE_ALL_SQLITE}:
            raise MemorySyncContractError(f"unsupported memory snapshot profile: {profile}")
        daemon = status_daemon(self.cfg)
        stopped = daemon.get("active_state") not in {"active_trusted", "active_degraded"} and not bool(
            daemon.get("pid_alive")
        )
        sources = self._discover_sources(profile)
        if not sources:
            raise MemorySyncContractError("no SQLite memory databases are available for snapshot")
        generation = self._source_generation(sources)
        base_remote_seq, chain_head = self._replication_position()
        return MemoryCloudSnapshotPlan(
            profile=profile,
            sources=sources,
            source_memory_generation=generation,
            base_remote_seq=base_remote_seq,
            event_chain_head_sha256=chain_head,
            runtime_stopped=stopped,
        )

    def create_snapshot(self, *, profile: str = PROFILE_CORE) -> MemorySnapshotCreateResult:
        plan = self.plan(profile=profile)
        if not plan.runtime_stopped:
            raise MemorySyncContractError(
                "multi-database memory snapshot requires the Jaźń daemon to be stopped for a coherent generation"
            )
        backend = self.sync_runtime.build_backend()
        key_provider = self.sync_runtime.build_key_provider()
        manager = SQLiteMemorySnapshotManager(
            backend=backend,
            key_provider=key_provider,
            chunk_crypto=PyNaClMemorySnapshotChunkCrypto(),
            policy=MemorySnapshotPolicy(),
        )
        return manager.create_snapshot(
            stream_id=self.sync_runtime.runtime.stream_id,
            sources=plan.sources,
            source_memory_generation=plan.source_memory_generation,
            base_remote_seq=plan.base_remote_seq,
            event_chain_head_sha256=plan.event_chain_head_sha256,
        )

    def restore_latest(self, *, destination_parent: str | Path) -> MemorySnapshotRestoreResult:
        backend = self.sync_runtime.build_backend()
        manifest = backend.latest_snapshot(stream_id=self.sync_runtime.runtime.stream_id)
        if manifest is None:
            raise MemorySyncContractError("cloud backend does not contain a committed snapshot for this stream")
        manager = SQLiteMemorySnapshotManager(
            backend=backend,
            key_provider=self.sync_runtime.build_key_provider(),
            chunk_crypto=PyNaClMemorySnapshotChunkCrypto(),
            policy=MemorySnapshotPolicy(),
        )
        return manager.restore_snapshot(manifest, destination_parent=destination_parent)

    def _discover_sources(self, profile: str) -> tuple[SQLiteSnapshotSource, ...]:
        sqlite_root = (self.cfg.root / "memory" / "sqlite").resolve()
        candidates: set[Path] = set()
        if profile == self.PROFILE_ALL_SQLITE:
            if sqlite_root.is_dir():
                for path in sqlite_root.rglob("*.sqlite3"):
                    if path.is_file() and not self._is_staging_path(path, sqlite_root):
                        candidates.add(path.resolve())
        else:
            explicit = (
                self.cfg.memory_tier_db_path,
                self.cfg.runtime_write_db_path_readonly,
                self.cfg.recovered_memory_db_path,
                self.cfg.normalization_sidecar_db_path,
            )
            for path in explicit:
                resolved = Path(path).expanduser().resolve()
                if resolved.is_file():
                    candidates.add(resolved)
            # Include all complete shards in the canonical runtime-write generations,
            # not only the currently active shard selected by config.
            for relative in ("runtime_write_v1", "runtime_write_v2", "recovery_current"):
                directory = sqlite_root / relative
                if directory.is_dir():
                    candidates.update(path.resolve() for path in directory.glob("*.sqlite3") if path.is_file())
        result: list[SQLiteSnapshotSource] = []
        for path in sorted(candidates):
            try:
                relative = path.relative_to(self.cfg.root.resolve()).as_posix()
            except ValueError as exc:
                raise MemorySyncContractError(f"snapshot database escapes runtime root: {path}") from exc
            result.append(SQLiteSnapshotSource(logical_path=relative, path=path))
        return tuple(result)

    @staticmethod
    def _is_staging_path(path: Path, sqlite_root: Path) -> bool:
        relative = path.relative_to(sqlite_root)
        return any(part.startswith("staging") or part.startswith("restore-") for part in relative.parts)

    @staticmethod
    def _source_generation(sources: Iterable[SQLiteSnapshotSource]) -> str:
        digest = hashlib.sha256()
        for source in sorted(sources, key=lambda value: value.logical_path):
            stat = source.path.stat()
            digest.update(source.logical_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
            digest.update(b"\n")
        return "local-sqlite-generation:" + digest.hexdigest()

    def _replication_position(self) -> tuple[int, str | None]:
        path = Path(self.cfg.memory_tier_db_path)
        if not path.is_file():
            return 0, None
        uri = path.resolve().as_uri() + "?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True, timeout=5.0) as con:
                tables = {str(row[0]) for row in con.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                )}
                if "memory_sync_state" not in tables:
                    return 0, None
                row = con.execute(
                    "SELECT local_cursor,device_chain_head_sha256 FROM memory_sync_state WHERE state_id=1"
                ).fetchone()
        except sqlite3.Error as exc:
            raise MemorySyncContractError(f"cannot read local memory replication position: {exc}") from exc
        if row is None:
            return 0, None
        return int(row[0]), str(row[1]) if row[1] else None


__all__ = ["MemoryCloudSnapshotPlan", "MemoryCloudSnapshotRuntime"]
