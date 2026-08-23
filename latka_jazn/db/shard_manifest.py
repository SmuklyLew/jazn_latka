from __future__ import annotations

from latka_jazn.version_contract import normalize_component_schema
from latka_jazn.memory.storage_limits import DEFAULT_MAX_SQLITE_FILE_BYTES
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import datetime
import hashlib
import json
import os
import threading
import time
import uuid

SCHEMA_VERSION = "jazn_sqlite_shards/v1"
DEFAULT_MAX_BYTES = DEFAULT_MAX_SQLITE_FILE_BYTES
_SHARD_MANIFEST_WRITE_LOCK = threading.RLock()


class ShardManifestError(RuntimeError):
    """Raised when an existing shard manifest cannot be trusted."""


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        while b := f.read(chunk_size):
            h.update(b)
    return h.hexdigest()


def _safe_relative_path(root: Path, raw: str) -> str:
    candidate = Path(str(raw))
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ShardManifestError(f"unsafe shard path: {raw!r}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ShardManifestError(f"shard path escapes runtime root: {raw!r}") from exc
    return candidate.as_posix()


@dataclass(slots=True)
class SQLiteShard:
    shard_id: str
    path: str
    role: str
    created_at_utc: str
    sealed_at_utc: str | None = None
    size_bytes: int = 0
    sha256: str | None = None
    note: str = ""


@dataclass(slots=True)
class SQLiteShardManifest:
    logical_database: str
    role: str
    active_write_shard: str
    max_file_bytes: int
    shards: list[SQLiteShard]
    schema_version: str = SCHEMA_VERSION
    updated_at_utc: str = ""
    truth_boundary: str = (
        "To jest logiczny manifest shardów. Każdy shard jest pełnoprawnym plikiem SQLite. "
        "System nie czyta pociętych binarnie fragmentów .sqlite3 jako działającej bazy; części transportowe trzeba najpierw złożyć."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "logical_database": self.logical_database,
            "role": self.role,
            "active_write_shard": self.active_write_shard,
            "max_file_bytes": self.max_file_bytes,
            "updated_at_utc": self.updated_at_utc or _now_utc(),
            "truth_boundary": self.truth_boundary,
            "shards": [asdict(s) for s in self.shards],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SQLiteShardManifest":
        try:
            shards = [SQLiteShard(**item) for item in data.get("shards", [])]
            return cls(
                schema_version=normalize_component_schema(
                    "jazn_sqlite_shards", data.get("schema_version")
                ),
                logical_database=str(data["logical_database"]),
                role=str(data.get("role") or data["logical_database"]),
                active_write_shard=str(data["active_write_shard"]),
                max_file_bytes=int(data.get("max_file_bytes") or DEFAULT_MAX_BYTES),
                updated_at_utc=str(data.get("updated_at_utc") or ""),
                truth_boundary=str(
                    data.get("truth_boundary")
                    or cls.__dataclass_fields__["truth_boundary"].default
                ),
                shards=shards,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ShardManifestError(f"invalid shard manifest structure: {exc}") from exc

    def validate(self, root: Path, *, logical_database: str, role: str) -> None:
        if self.logical_database != logical_database:
            raise ShardManifestError(
                f"logical database mismatch: {self.logical_database!r} != {logical_database!r}"
            )
        if self.role != role:
            raise ShardManifestError(f"role mismatch: {self.role!r} != {role!r}")
        if self.max_file_bytes <= 0:
            raise ShardManifestError("max_file_bytes must be positive")
        if not self.shards:
            raise ShardManifestError("shard manifest contains no shards")
        ids = [str(shard.shard_id) for shard in self.shards]
        if any(not shard_id for shard_id in ids) or len(ids) != len(set(ids)):
            raise ShardManifestError("shard ids must be non-empty and unique")
        if ids.count(self.active_write_shard) != 1:
            raise ShardManifestError(
                f"active shard not found exactly once: {self.active_write_shard!r}"
            )
        active_role_count = 0
        for shard in self.shards:
            shard.path = _safe_relative_path(root, shard.path)
            if shard.role == "active_write":
                active_role_count += 1
            if shard.shard_id == self.active_write_shard and shard.role != "active_write":
                raise ShardManifestError("active_write_shard does not have active_write role")
        if active_role_count != 1:
            raise ShardManifestError("manifest must contain exactly one active_write role")

    def active_path(self, root: Path) -> Path:
        for shard in self.shards:
            if shard.shard_id == self.active_write_shard:
                safe = _safe_relative_path(root, shard.path)
                return root.resolve() / safe
        raise ShardManifestError(f"active shard not found: {self.active_write_shard}")


class SQLiteShardManager:
    """Logical sharding helper using complete SQLite database files only."""

    def __init__(
        self,
        root: Path,
        manifest_path: str | Path,
        *,
        logical_database: str,
        role: str,
        default_db_path: str | Path,
        max_file_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.root = Path(root).resolve()
        self.manifest_path = self.root / manifest_path
        self.logical_database = logical_database
        self.role = role
        self.default_db_path = _safe_relative_path(self.root, Path(default_db_path).as_posix())
        self.max_file_bytes = int(
            os.environ.get("JAZN_MAX_SQLITE_FILE_BYTES", str(max_file_bytes))
        )

    def load_existing(self) -> SQLiteShardManifest:
        if not self.manifest_path.is_file():
            raise FileNotFoundError(self.manifest_path)
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            raise ShardManifestError(
                f"cannot read shard manifest {self.manifest_path}: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ShardManifestError("shard manifest root must be a JSON object")
        manifest = SQLiteShardManifest.from_dict(data)
        manifest.validate(
            self.root,
            logical_database=self.logical_database,
            role=self.role,
        )
        return manifest

    def load_or_create(self) -> SQLiteShardManifest:
        if self.manifest_path.exists():
            return self.load_existing()
        db_path = self.root / self.default_db_path
        shard = SQLiteShard(
            "0001",
            self.default_db_path,
            "active_write",
            _now_utc(),
            size_bytes=db_path.stat().st_size if db_path.exists() else 0,
            sha256=_sha256_file(db_path),
            note="Initial canonical shard generated by runtime migration.",
        )
        manifest = SQLiteShardManifest(
            self.logical_database,
            self.role,
            shard.shard_id,
            self.max_file_bytes,
            [shard],
            updated_at_utc=_now_utc(),
        )
        self.save(manifest)
        return manifest

    def save(self, manifest: SQLiteShardManifest) -> None:
        manifest.validate(
            self.root,
            logical_database=self.logical_database,
            role=self.role,
        )
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_name(
            f".{self.manifest_path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with _SHARD_MANIFEST_WRITE_LOCK:
                tmp.write_text(
                    json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                for attempt in range(6):
                    try:
                        os.replace(tmp, self.manifest_path)
                        return
                    except PermissionError:
                        if attempt == 5:
                            raise
                        time.sleep(0.02 * (attempt + 1))
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def active_path(self) -> Path:
        return self.load_or_create().active_path(self.root)

    def refresh_sizes(self) -> SQLiteShardManifest:
        manifest = self.load_or_create()
        for shard in manifest.shards:
            p = self.root / shard.path
            shard.size_bytes = p.stat().st_size if p.exists() else 0
            if os.environ.get("JAZN_SHARD_REFRESH_SHA", "0").strip().lower() in {
                "1", "true", "yes", "tak", "on"
            }:
                shard.sha256 = _sha256_file(p)
        manifest.updated_at_utc = _now_utc()
        self.save(manifest)
        return manifest

    def rotate_if_needed(self) -> Path:
        manifest = self.refresh_sizes()
        active = manifest.active_path(self.root)
        if not active.exists() or active.stat().st_size < manifest.max_file_bytes:
            return active
        current = next(
            s for s in manifest.shards if s.shard_id == manifest.active_write_shard
        )
        current.role = "sealed"
        current.sealed_at_utc = _now_utc()
        numeric_ids = [int(s.shard_id) for s in manifest.shards if s.shard_id.isdigit()]
        next_num = max(numeric_ids or [0]) + 1
        new_id = f"{next_num:04d}"
        base = Path(self.default_db_path)
        new_rel = (base.parent / f"{base.stem}_{new_id}{base.suffix}").as_posix()
        manifest.shards.append(
            SQLiteShard(
                new_id,
                new_rel,
                "active_write",
                _now_utc(),
                note="Created automatically because previous active shard reached max_file_bytes.",
            )
        )
        manifest.active_write_shard = new_id
        manifest.updated_at_utc = _now_utc()
        self.save(manifest)
        new_path = self.root / new_rel
        new_path.parent.mkdir(parents=True, exist_ok=True)
        return new_path


def ensure_manifest(
    root: Path,
    manifest_path: str,
    *,
    logical_database: str,
    role: str,
    default_db_path: str,
    max_file_bytes: int = DEFAULT_MAX_BYTES,
) -> SQLiteShardManifest:
    mgr = SQLiteShardManager(
        root,
        manifest_path,
        logical_database=logical_database,
        role=role,
        default_db_path=default_db_path,
        max_file_bytes=max_file_bytes,
    )
    return mgr.refresh_sizes()
