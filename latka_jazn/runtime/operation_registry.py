from __future__ import annotations

"""Durable, payload-redacted operation registry.

The registry exists outside private MEMORY so transport ambiguity can be
resolved even in SYSTEM-only mode.  It stores operation identity, hashes and
state transitions only; raw user text and generated replies are deliberately
excluded.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
import hashlib
import json
import os
import uuid

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("operation_registry")
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})
VALID_STATES = frozenset({
    "registered",
    "submitted",
    "outcome_unknown",
    "working",
    "awaiting_host_finalization",
    "completed",
    "failed",
    "cancelled",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_digest(payload: Mapping[str, Any] | str | bytes) -> str:
    if isinstance(payload, bytes):
        raw = payload
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _record_filename(operation_id: str) -> str:
    digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
    return f"{digest}.json"


@dataclass(slots=True)
class OperationRecord:
    operation_id: str
    operation_kind: str
    payload_sha256: str
    state: str
    created_at_utc: str
    updated_at_utc: str
    attempt_count: int = 0
    last_error: str | None = None
    result_sha256: str | None = None
    result_status: str | None = None
    relation: dict[str, str] | None = None
    schema_version: str = SCHEMA_VERSION

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["terminal"] = self.terminal
        return payload


class OperationConflictError(RuntimeError):
    pass


class OperationRegistry:
    """Atomic per-operation records under ``workspace_runtime/operations``."""

    def __init__(self, runtime_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.root = workspace_runtime_path(self.runtime_root) / "operations"
        self._lock = RLock()

    def _path(self, operation_id: str) -> Path:
        normalized = str(operation_id or "").strip()
        if not normalized:
            raise ValueError("operation_id_required")
        if len(normalized) > 512:
            raise ValueError("operation_id_too_large")
        return self.root / _record_filename(normalized)

    def _read_path(self, path: Path) -> OperationRecord | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"operation_registry_read_failed:{type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("operation_registry_record_not_object")
        filtered = {key: value for key, value in payload.items() if key in OperationRecord.__dataclass_fields__}
        record = OperationRecord(**filtered)
        if record.state not in VALID_STATES:
            raise RuntimeError("operation_registry_invalid_state")
        return record

    def get(self, operation_id: str) -> OperationRecord | None:
        with self._lock:
            return self._read_path(self._path(operation_id))

    def _write(self, record: OperationRecord) -> OperationRecord:
        path = self._path(record.operation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        payload = record.to_dict()
        payload.pop("terminal", None)
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        return record

    def claim(
        self,
        *,
        operation_id: str,
        operation_kind: str,
        payload: Mapping[str, Any] | str | bytes,
        relation: Mapping[str, str] | None = None,
    ) -> OperationRecord:
        digest = _payload_digest(payload)
        now = _utc_now()
        with self._lock:
            path = self._path(operation_id)
            current = self._read_path(path)
            if current is not None:
                if current.operation_kind != str(operation_kind) or current.payload_sha256 != digest:
                    raise OperationConflictError("operation_id_payload_conflict")
                return current
            return self._write(OperationRecord(
                operation_id=str(operation_id),
                operation_kind=str(operation_kind),
                payload_sha256=digest,
                state="registered",
                created_at_utc=now,
                updated_at_utc=now,
                relation=dict(relation or {}) or None,
            ))

    def transition(
        self,
        operation_id: str,
        state: str,
        *,
        last_error: str | None = None,
        result: Mapping[str, Any] | str | bytes | None = None,
        result_status: str | None = None,
        relation: Mapping[str, str] | None = None,
        increment_attempt: bool = False,
    ) -> OperationRecord:
        target = str(state or "").strip()
        if target not in VALID_STATES:
            raise ValueError("invalid_operation_state")
        with self._lock:
            current = self._read_path(self._path(operation_id))
            if current is None:
                raise KeyError(f"unknown_operation:{operation_id}")
            if current.terminal and target != current.state:
                raise OperationConflictError("terminal_operation_cannot_transition")
            current.state = target
            current.updated_at_utc = _utc_now()
            if increment_attempt:
                current.attempt_count += 1
            if last_error is not None:
                current.last_error = str(last_error)[:1024]
            if result is not None:
                current.result_sha256 = _payload_digest(result)
            if result_status is not None:
                current.result_status = str(result_status)[:128]
            if relation:
                merged = dict(current.relation or {})
                merged.update({str(key): str(value) for key, value in relation.items()})
                current.relation = merged
            return self._write(current)

    def note_attempt(self, operation_id: str) -> OperationRecord:
        current = self.get(operation_id)
        if current is None:
            raise KeyError(f"unknown_operation:{operation_id}")
        return self.transition(operation_id, current.state, increment_attempt=True)

    def snapshot(self, operation_id: str) -> dict[str, Any] | None:
        record = self.get(operation_id)
        return record.to_dict() if record else None


__all__ = [
    "OperationConflictError",
    "OperationRecord",
    "OperationRegistry",
    "TERMINAL_STATES",
    "VALID_STATES",
]
