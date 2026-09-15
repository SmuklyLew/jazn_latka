from __future__ import annotations

"""Durable MCP Tasks adapter for long-running Jaźń turns.

The adapter implements the poll-oriented core of ``io.modelcontextprotocol/tasks``
without changing the canonical Jaźń turn/finalization contract.  A daemon turn
that is still pending becomes a durable task handle; subsequent ``tasks/get``
requests poll the same daemon request id and never replay the user message.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol
import json
import os
import secrets
import uuid

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
        if self.status == "completed" and self.result is not None:
            payload["result"] = self.result
        if self.status == "failed" and self.error is not None:
            payload["error"] = self.error
        return payload

    def to_storage_dict(self) -> dict[str, Any]:
        return asdict(self)


class McpTaskStore:
    """Strongly-created task records under host-level workspace state."""

    def __init__(self, runtime_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.root = workspace_runtime_path(self.runtime_root) / "mcp_tasks"
        self._lock = RLock()

    def _path(self, task_id: str) -> Path:
        value = str(task_id or "").strip()
        if not value or len(value) > 256:
            raise ValueError("invalid_task_id")
        # task ids are generated from URL-safe entropy, but hash filenames keep
        # path handling fail-closed even if a future external id is accepted.
        import hashlib

        return self.root / (hashlib.sha256(value.encode("utf-8")).hexdigest() + ".json")

    def _read(self, task_id: str) -> McpTaskRecord | None:
        path = self._path(task_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"mcp_task_store_read_failed:{type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("mcp_task_record_not_object")
        filtered = {key: value for key, value in payload.items() if key in McpTaskRecord.__dataclass_fields__}
        record = McpTaskRecord(**filtered)
        if record.status not in VALID_TASK_STATES:
            raise RuntimeError("mcp_task_record_invalid_status")
        return record

    def get(self, task_id: str) -> McpTaskRecord | None:
        with self._lock:
            return self._read(task_id)

    def _write(self, record: McpTaskRecord) -> McpTaskRecord:
        path = self._path(record.task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(record.to_storage_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        return record

    def create(
        self,
        *,
        daemon_request_id: str,
        ttl_ms: int | None = DEFAULT_TASK_TTL_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        status_message: str = "Jaźń runtime turn is still in progress.",
    ) -> McpTaskRecord:
        request_id = str(daemon_request_id or "").strip()
        if not request_id:
            raise ValueError("daemon_request_id_required")
        now = datetime.now(timezone.utc).isoformat()
        task_id = "jazn-task-" + secrets.token_urlsafe(32)
        record = McpTaskRecord(
            task_id=task_id,
            daemon_request_id=request_id,
            status="working",
            created_at=now,
            last_updated_at=now,
            ttl_ms=ttl_ms,
            poll_interval_ms=max(100, int(poll_interval_ms)),
            status_message=status_message,
        )
        with self._lock:
            # The response is returned only after this durable write succeeds.
            return self._write(record)

    def update(
        self,
        task_id: str,
        *,
        status: str,
        result: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
        status_message: str | None = None,
    ) -> McpTaskRecord:
        target = str(status or "").strip()
        if target not in VALID_TASK_STATES:
            raise ValueError("invalid_task_status")
        with self._lock:
            record = self._read(task_id)
            if record is None:
                raise KeyError("unknown_task")
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
            return self._write(record)

    def cancel(self, task_id: str) -> McpTaskRecord:
        record = self.get(task_id)
        if record is None:
            raise KeyError("unknown_task")
        if record.terminal:
            return record
        return self.update(
            task_id,
            status="cancelled",
            status_message="Cancellation recorded by the MCP task adapter; daemon cancellation is cooperative and not implied.",
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
        record = self.store.create(
            daemon_request_id=request_id,
            ttl_ms=self.ttl_ms,
            poll_interval_ms=self.poll_interval_ms,
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
                error={"code": -32002, "message": f"task_poll_failed:{type(exc).__name__}:{exc}"},
                status_message="Polling the existing Jaźń request failed.",
            )
            return failed.to_task_result()

        structured = resumed.get("structuredContent")
        structured_map = structured if isinstance(structured, Mapping) else {}
        action = str(structured_map.get("action") or "").strip()
        if action == "poll_runtime" and not resumed.get("isError"):
            working = self.store.update(
                task_id,
                status="working",
                status_message="Jaźń runtime turn remains in progress; continue polling this task.",
            )
            return working.to_task_result()

        # MCP specifies that a completed tool result may itself carry isError=true;
        # this is still a completed task, not a JSON-RPC task failure.
        completed = self.store.update(
            task_id,
            status="completed",
            result=dict(resumed),
            status_message="Jaźń tool result is available.",
        )
        return completed.to_task_result()

    def cancel(self, task_id: str) -> dict[str, Any]:
        return self.store.cancel(task_id).to_task_result()

    def update_input(self, task_id: str, input_responses: Mapping[str, Any] | None = None) -> dict[str, Any]:
        record = self.store.get(task_id)
        if record is None:
            raise KeyError("unknown_task")
        # Jaźń host turns currently do not surface MCP task inputRequests. Keep
        # the method for protocol completeness without inventing an input flow.
        if record.status != "input_required":
            return record.to_task_result()
        working = self.store.update(
            task_id,
            status="working",
            status_message=(
                "Input responses acknowledged by the task adapter; the underlying Jaźń turn remains authoritative."
                if input_responses
                else "No input responses supplied."
            ),
        )
        return working.to_task_result()


__all__ = [
    "DEFAULT_POLL_INTERVAL_MS",
    "DEFAULT_TASK_TTL_MS",
    "McpTaskRecord",
    "McpTaskResumeAdapter",
    "McpTaskStore",
    "TASK_EXTENSION_ID",
]
