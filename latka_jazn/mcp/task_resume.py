from __future__ import annotations

"""Durable MCP Tasks adapter for long-running Jaźń turns.

MCP 2026-07-28 makes Tasks an extension rather than hidden transport state.
Jaźń therefore persists each task handle before returning it and keeps the
daemon request id as the execution identity.  Polling after a host disconnect
always resumes that same request; the original user message is never replayed.

The current store is SQLite-backed for crash/process continuity.  Historical
JSON task records from the v76 adapter are migrated lazily and are left in place
for audit/recovery rather than deleted.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol
import hashlib
import json
import secrets
import sqlite3

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.mcp.tools import jazn_resume_visible_reply
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("mcp_task_resume")
TASK_EXTENSION_ID = "io.modelcontextprotocol/tasks"
TERMINAL_TASK_STATES = frozenset({"completed", "failed", "cancelled"})
VALID_TASK_STATES = frozenset({"working", "input_required", "completed", "failed", "cancelled"})
DEFAULT_TASK_TTL_MS = 60 * 60 * 1000
DEFAULT_POLL_INTERVAL_MS = 750


class TaskGateway(Protocol):
    def result(self, request_id: str) -> dict[str, Any]: ...


@dataclass(slots=True)
class McpTaskRecord:
    task_id: str
    daemon_request_id: str
    status: str
    created_at: str
    last_updated_at: str
    ttl_ms: int | None
    poll_interval_ms: int
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    status_message: str | None = None
    request_id: str | None = None
    turn_id: str | None = None
    trace_id: str | None = None
    host_request_contract_hash: str | None = None
    input_requests: dict[str, Any] | None = None
    request_state: str | None = None
    cancel_requested: bool = False
    schema_version: str = SCHEMA_VERSION

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_TASK_STATES

    def to_task_result(self, *, creation: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "resultType": "task" if creation else "complete",
            "taskId": self.task_id,
            "status": self.status,
            "createdAt": self.created_at,
            "lastUpdatedAt": self.last_updated_at,
            "ttlMs": self.ttl_ms,
            "pollIntervalMs": self.poll_interval_ms,
        }
        if self.status_message:
            payload["statusMessage"] = self.status_message
        if self.status == "input_required":
            payload["inputRequests"] = dict(self.input_requests or {})
            if self.request_state is not None:
                payload["requestState"] = self.request_state
        if self.status == "completed" and self.result is not None:
            payload["result"] = self.result
        if self.status == "failed" and self.error is not None:
            payload["error"] = self.error
        return payload

    def lineage(self) -> dict[str, str]:
        result: dict[str, str] = {"daemon_request_id": self.daemon_request_id}
        for key, value in (
            ("request_id", self.request_id),
            ("turn_id", self.turn_id),
            ("trace_id", self.trace_id),
            ("host_request_contract_hash", self.host_request_contract_hash),
        ):
            normalized = str(value or "").strip()
            if normalized:
                result[key] = normalized
        return result


class McpTaskStore:
    """SQLite-backed durable task registry with bounded legacy migration."""

    def __init__(self, runtime_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        workspace = workspace_runtime_path(self.runtime_root)
        self.db_path = workspace / "mcp_tasks.sqlite3"
        # Compatibility attributes retained for old diagnostics/tools.
        self.root = workspace / "mcp_tasks"
        self.index_root = self.root / "by_daemon_request"
        self._lock = RLock()
        self._ensure_schema()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_tasks (
                    task_id TEXT PRIMARY KEY,
                    daemon_request_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL,
                    ttl_ms INTEGER,
                    poll_interval_ms INTEGER NOT NULL,
                    result_json TEXT,
                    error_json TEXT,
                    status_message TEXT,
                    request_id TEXT,
                    turn_id TEXT,
                    trace_id TEXT,
                    host_request_contract_hash TEXT,
                    input_requests_json TEXT,
                    request_state TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    schema_version TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_tasks_status_updated "
                "ON mcp_tasks(status, last_updated_at)"
            )

    @staticmethod
    def _dump_object(value: Mapping[str, Any] | None) -> str | None:
        if value is None:
            return None
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _load_object(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        decoded = json.loads(str(value))
        if not isinstance(decoded, dict):
            raise RuntimeError("mcp_task_json_field_not_object")
        return decoded

    @classmethod
    def _row_to_record(cls, row: sqlite3.Row) -> McpTaskRecord:
        record = McpTaskRecord(
            task_id=str(row["task_id"]),
            daemon_request_id=str(row["daemon_request_id"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            last_updated_at=str(row["last_updated_at"]),
            ttl_ms=int(row["ttl_ms"]) if row["ttl_ms"] is not None else None,
            poll_interval_ms=int(row["poll_interval_ms"]),
            result=cls._load_object(row["result_json"]),
            error=cls._load_object(row["error_json"]),
            status_message=str(row["status_message"]) if row["status_message"] is not None else None,
            request_id=str(row["request_id"]) if row["request_id"] is not None else None,
            turn_id=str(row["turn_id"]) if row["turn_id"] is not None else None,
            trace_id=str(row["trace_id"]) if row["trace_id"] is not None else None,
            host_request_contract_hash=(
                str(row["host_request_contract_hash"])
                if row["host_request_contract_hash"] is not None
                else None
            ),
            input_requests=cls._load_object(row["input_requests_json"]),
            request_state=str(row["request_state"]) if row["request_state"] is not None else None,
            cancel_requested=bool(row["cancel_requested"]),
            schema_version=str(row["schema_version"]),
        )
        if record.status not in VALID_TASK_STATES:
            raise RuntimeError("mcp_task_record_invalid_status")
        return record

    def _select_task(self, conn: sqlite3.Connection, task_id: str) -> McpTaskRecord | None:
        row = conn.execute("SELECT * FROM mcp_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._row_to_record(row) if row is not None else None

    def _select_request(self, conn: sqlite3.Connection, daemon_request_id: str) -> McpTaskRecord | None:
        row = conn.execute(
            "SELECT * FROM mcp_tasks WHERE daemon_request_id = ?",
            (daemon_request_id,),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def _legacy_task_path(self, task_id: str) -> Path:
        return self.root / (self._digest(task_id) + ".json")

    def _legacy_index_path(self, daemon_request_id: str) -> Path:
        return self.index_root / (self._digest(daemon_request_id) + ".json")

    def _read_legacy_task(self, task_id: str) -> McpTaskRecord | None:
        try:
            payload = json.loads(self._legacy_task_path(task_id).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"mcp_task_legacy_read_failed:{type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("mcp_task_legacy_record_not_object")
        allowed = McpTaskRecord.__dataclass_fields__
        filtered = {key: value for key, value in payload.items() if key in allowed}
        record = McpTaskRecord(**filtered)
        if record.status not in VALID_TASK_STATES:
            raise RuntimeError("mcp_task_legacy_record_invalid_status")
        return record

    def _read_legacy_by_request(self, daemon_request_id: str) -> McpTaskRecord | None:
        try:
            payload = json.loads(self._legacy_index_path(daemon_request_id).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"mcp_task_legacy_index_read_failed:{type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("mcp_task_legacy_index_not_object")
        task_id = str(payload.get("task_id") or "").strip()
        if not task_id:
            raise RuntimeError("mcp_task_legacy_index_invalid")
        record = self._read_legacy_task(task_id)
        if record is None or record.daemon_request_id != daemon_request_id:
            raise RuntimeError("mcp_task_legacy_index_mismatch")
        return record

    def _upsert(self, conn: sqlite3.Connection, record: McpTaskRecord) -> McpTaskRecord:
        conn.execute(
            """
            INSERT INTO mcp_tasks (
                task_id, daemon_request_id, status, created_at, last_updated_at,
                ttl_ms, poll_interval_ms, result_json, error_json, status_message,
                request_id, turn_id, trace_id, host_request_contract_hash,
                input_requests_json, request_state, cancel_requested, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                status=excluded.status,
                last_updated_at=excluded.last_updated_at,
                ttl_ms=excluded.ttl_ms,
                poll_interval_ms=excluded.poll_interval_ms,
                result_json=excluded.result_json,
                error_json=excluded.error_json,
                status_message=excluded.status_message,
                request_id=COALESCE(excluded.request_id, mcp_tasks.request_id),
                turn_id=COALESCE(excluded.turn_id, mcp_tasks.turn_id),
                trace_id=COALESCE(excluded.trace_id, mcp_tasks.trace_id),
                host_request_contract_hash=COALESCE(
                    excluded.host_request_contract_hash,
                    mcp_tasks.host_request_contract_hash
                ),
                input_requests_json=excluded.input_requests_json,
                request_state=excluded.request_state,
                cancel_requested=excluded.cancel_requested,
                schema_version=excluded.schema_version
            """,
            (
                record.task_id,
                record.daemon_request_id,
                record.status,
                record.created_at,
                record.last_updated_at,
                record.ttl_ms,
                record.poll_interval_ms,
                self._dump_object(record.result),
                self._dump_object(record.error),
                record.status_message,
                record.request_id,
                record.turn_id,
                record.trace_id,
                record.host_request_contract_hash,
                self._dump_object(record.input_requests),
                record.request_state,
                1 if record.cancel_requested else 0,
                record.schema_version,
            ),
        )
        return record

    def get(self, task_id: str) -> McpTaskRecord | None:
        value = str(task_id or "").strip()
        if not value or len(value) > 256:
            raise ValueError("invalid_task_id")
        with self._lock, self._connect() as conn:
            record = self._select_task(conn, value)
            if record is not None:
                return record
            legacy = self._read_legacy_task(value)
            if legacy is None:
                return None
            self._upsert(conn, legacy)
            return legacy

    def list_recent(self, *, limit: int = 50) -> list[McpTaskRecord]:
        bounded = max(1, min(int(limit), 200))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mcp_tasks ORDER BY last_updated_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def create_or_get(
        self,
        *,
        daemon_request_id: str,
        ttl_ms: int | None = DEFAULT_TASK_TTL_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        status_message: str = "Jaźń runtime turn is still in progress.",
        request_id: str | None = None,
        turn_id: str | None = None,
        trace_id: str | None = None,
        host_request_contract_hash: str | None = None,
    ) -> McpTaskRecord:
        request_value = str(daemon_request_id or "").strip()
        if not request_value or len(request_value) > 256:
            raise ValueError("daemon_request_id_required")
        with self._lock, self._connect() as conn:
            existing = self._select_request(conn, request_value)
            if existing is not None:
                return existing
            legacy = self._read_legacy_by_request(request_value)
            if legacy is not None:
                self._upsert(conn, legacy)
                return legacy
            now = datetime.now(timezone.utc).isoformat()
            record = McpTaskRecord(
                task_id="jazn-task-" + secrets.token_urlsafe(32),
                daemon_request_id=request_value,
                status="working",
                created_at=now,
                last_updated_at=now,
                ttl_ms=ttl_ms,
                poll_interval_ms=max(100, int(poll_interval_ms)),
                status_message=status_message,
                request_id=str(request_id or request_value),
                turn_id=str(turn_id) if turn_id else None,
                trace_id=str(trace_id) if trace_id else None,
                host_request_contract_hash=(
                    str(host_request_contract_hash).lower()
                    if host_request_contract_hash
                    else None
                ),
            )
            try:
                self._upsert(conn, record)
            except sqlite3.IntegrityError:
                winner = self._select_request(conn, request_value)
                if winner is None:
                    raise
                return winner
            return record

    def update(
        self,
        task_id: str,
        *,
        status: str,
        result: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
        status_message: str | None = None,
        input_requests: Mapping[str, Any] | None = None,
        request_state: str | None = None,
        cancel_requested: bool | None = None,
    ) -> McpTaskRecord:
        target = str(status or "").strip()
        if target not in VALID_TASK_STATES:
            raise ValueError("invalid_task_status")
        with self._lock, self._connect() as conn:
            record = self._select_task(conn, str(task_id))
            if record is None:
                legacy = self._read_legacy_task(str(task_id))
                if legacy is None:
                    raise KeyError("unknown_task")
                self._upsert(conn, legacy)
                record = legacy
            if record.terminal and target != record.status:
                raise RuntimeError("terminal_task_cannot_transition")
            record.status = target
            record.last_updated_at = datetime.now(timezone.utc).isoformat()
            if result is not None:
                record.result = dict(result)
            if error is not None:
                record.error = dict(error)
            if status_message is not None:
                record.status_message = str(status_message)[:1024]
            if input_requests is not None:
                record.input_requests = dict(input_requests)
            elif target != "input_required":
                record.input_requests = None
            if request_state is not None:
                record.request_state = str(request_state)
            elif target != "input_required":
                record.request_state = None
            if cancel_requested is not None:
                record.cancel_requested = bool(cancel_requested)
            return self._upsert(conn, record)

    def request_cancel(self, task_id: str) -> McpTaskRecord:
        record = self.get(task_id)
        if record is None:
            raise KeyError("unknown_task")
        if record.terminal:
            return record
        return self.update(
            task_id,
            status="working",
            cancel_requested=True,
            status_message=(
                "Cancellation requested; the underlying Jaźń turn has no verified "
                "cancellation acknowledgement yet."
            ),
        )


class McpTaskResumeAdapter:
    def __init__(
        self,
        *,
        root: Path | str,
        gateway: TaskGateway,
        ttl_ms: int | None = DEFAULT_TASK_TTL_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.gateway = gateway
        self.store = McpTaskStore(self.root)
        self.ttl_ms = ttl_ms
        self.poll_interval_ms = poll_interval_ms

    @staticmethod
    def pending_daemon_request_id(tool_result: Mapping[str, Any]) -> str | None:
        structured = tool_result.get("structuredContent")
        if not isinstance(structured, Mapping):
            return None
        if str(structured.get("action") or "") != "poll_runtime":
            return None
        value = str(
            structured.get("daemon_request_id")
            or structured.get("request_id")
            or ""
        ).strip()
        return value or None

    def create_from_pending_result(self, tool_result: Mapping[str, Any]) -> dict[str, Any] | None:
        request_id = self.pending_daemon_request_id(tool_result)
        if not request_id:
            return None
        structured = tool_result.get("structuredContent")
        structured_map = structured if isinstance(structured, Mapping) else {}
        record = self.store.create_or_get(
            daemon_request_id=request_id,
            ttl_ms=self.ttl_ms,
            poll_interval_ms=self.poll_interval_ms,
            request_id=str(structured_map.get("request_id") or request_id),
            turn_id=str(structured_map.get("turn_id") or "") or None,
            trace_id=str(structured_map.get("trace_id") or "") or None,
            host_request_contract_hash=(
                str(structured_map.get("host_request_contract_hash") or "") or None
            ),
        )
        return record.to_task_result(creation=True)

    def get(self, task_id: str) -> dict[str, Any]:
        record = self.store.get(task_id)
        if record is None:
            raise KeyError("unknown_task")
        if record.terminal:
            return record.to_task_result()

        try:
            resumed = jazn_resume_visible_reply.run(
                root=self.root,
                gateway=self.gateway,
                daemon_request_id=record.daemon_request_id,
            )
        except Exception as exc:
            failed = self.store.update(
                task_id,
                status="failed",
                error={"code": -32603, "message": f"task_poll_failed:{type(exc).__name__}:{exc}"},
                status_message="Polling the existing Jaźń request failed.",
            )
            return failed.to_task_result()

        structured = resumed.get("structuredContent")
        structured_map = structured if isinstance(structured, Mapping) else {}
        action = str(structured_map.get("action") or "").strip()
        result_type = str(structured_map.get("resultType") or resumed.get("resultType") or "").strip()
        if result_type == "input_required" or action == "input_required":
            input_requests = structured_map.get("inputRequests")
            if not isinstance(input_requests, Mapping):
                input_requests = {}
            waiting = self.store.update(
                task_id,
                status="input_required",
                input_requests=input_requests,
                request_state=str(structured_map.get("requestState") or "") or None,
                status_message="Jaźń task requires explicit client input before it can continue.",
            )
            return waiting.to_task_result()

        if action == "poll_runtime" and not resumed.get("isError"):
            working = self.store.update(
                task_id,
                status="working",
                status_message="Jaźń runtime turn remains in progress; continue polling this task.",
            )
            return working.to_task_result()

        completed = self.store.update(
            task_id,
            status="completed",
            result=dict(resumed),
            status_message="Jaźń tool result is available.",
        )
        return completed.to_task_result()

    def cancel(self, task_id: str) -> dict[str, Any]:
        self.store.request_cancel(task_id)
        # Cancellation is cooperative.  We acknowledge receipt but do not lie
        # that the underlying runtime stopped before it confirms cancellation.
        return {"resultType": "complete"}

    def update_input(
        self,
        task_id: str,
        input_responses: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.store.get(task_id)
        if record is None:
            raise KeyError("unknown_task")
        if record.status != "input_required":
            return {"resultType": "complete"}

        responses = dict(input_responses or {})
        outstanding = dict(record.input_requests or {})
        for key in responses:
            outstanding.pop(str(key), None)
        if outstanding:
            self.store.update(
                task_id,
                status="input_required",
                input_requests=outstanding,
                request_state=record.request_state,
                status_message="Waiting for remaining task input responses.",
            )
            return {"resultType": "complete"}

        # Current Jaźń visible-turn tools do not emit input_required yet.
        # Fail closed rather than pretending the runtime consumed answers.
        raise RuntimeError("task_input_runtime_transport_not_implemented")


__all__ = [
    "DEFAULT_POLL_INTERVAL_MS",
    "DEFAULT_TASK_TTL_MS",
    "McpTaskRecord",
    "McpTaskResumeAdapter",
    "McpTaskStore",
    "TASK_EXTENSION_ID",
]
