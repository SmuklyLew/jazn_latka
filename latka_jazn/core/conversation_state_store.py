from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import hashlib
import json
import os
import re
import time
import uuid

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("conversation_state_store")
PROJECTION_SCHEMA_VERSION = schema_version("conversation_context_projection")
DEFAULT_MAX_TURNS = 24
DEFAULT_MAX_CHARS = 12000


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _safe_component(value: str, *, fallback: str) -> str:
    raw = str(value or "").strip()
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", raw).strip("._")[:80]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{safe or fallback}-{digest}"


def _fsync_directory(path: Path) -> None:
    fd: int | None = None
    try:
        fd = os.open(path, getattr(os, "O_RDONLY", 0))
        os.fsync(fd)
    except (AttributeError, OSError):
        return
    finally:
        if fd is not None:
            os.close(fd)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(payload), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


@dataclass(slots=True, frozen=True)
class ConversationTurnRecord:
    session_id: str
    turn_id: str
    trace_id: str
    user_text: str
    assistant_text: str
    accepted_at_utc: str
    source: str
    user_text_sha256: str
    assistant_text_sha256: str
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def build(
        cls,
        *,
        session_id: str,
        turn_id: str,
        trace_id: str,
        user_text: str,
        assistant_text: str,
        source: str,
    ) -> "ConversationTurnRecord":
        resolved_session = str(session_id or "").strip()
        resolved_turn = str(turn_id or "").strip()
        resolved_trace = str(trace_id or "").strip()
        if not resolved_session:
            raise ValueError("session_id_required")
        if not resolved_turn:
            raise ValueError("turn_id_required")
        if not resolved_trace:
            raise ValueError("trace_id_required")
        visible = str(assistant_text or "")
        if not visible.strip():
            raise ValueError("assistant_text_required")
        user = str(user_text or "")
        return cls(
            session_id=resolved_session,
            turn_id=resolved_turn,
            trace_id=resolved_trace,
            user_text=user,
            assistant_text=visible,
            accepted_at_utc=datetime.now(timezone.utc).isoformat(),
            source=str(source or "runtime").strip() or "runtime",
            user_text_sha256=hashlib.sha256(user.encode("utf-8")).hexdigest(),
            assistant_text_sha256=hashlib.sha256(visible.encode("utf-8")).hexdigest(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConversationStateStore:
    """Durable, local-first short-term conversation state.

    Each accepted turn is stored as its own hash-bound JSON record under
    ``workspace_runtime``.  The store never deletes or rewrites older accepted
    turns during context compaction.  Model-facing context is a bounded
    projection over these canonical records.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.storage_root = workspace_runtime_path(self.root) / "conversation_state"

    def _session_dir(self, session_id: str) -> Path:
        raw = str(session_id or "").strip()
        if not raw:
            raise ValueError("session_id_required")
        if len(raw.encode("utf-8")) > 512:
            raise ValueError("session_id_too_long")
        return self.storage_root / _safe_component(raw, fallback="session")

    def _turn_path(self, session_id: str, turn_id: str) -> Path:
        return self._session_dir(session_id) / f"{_safe_component(turn_id, fallback='turn')}.json"

    def _lock_path(self, session_id: str, turn_id: str) -> Path:
        path = self._turn_path(session_id, turn_id)
        return path.with_suffix(path.suffix + ".lock")

    @staticmethod
    def _record_payload(record: ConversationTurnRecord) -> dict[str, Any]:
        payload = record.to_dict()
        payload["record_sha256"] = _sha256(payload)
        payload["truth_boundary"] = (
            "This record proves one accepted visible conversation turn and its source hashes. "
            "It is short-term conversation state, not automatic long-term canon or an autobiographical claim."
        )
        return payload

    @staticmethod
    def _validate_payload(payload: Any) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(payload, dict):
            return None, "turn_record_not_object"
        required = (
            "session_id",
            "turn_id",
            "trace_id",
            "user_text",
            "assistant_text",
            "accepted_at_utc",
            "source",
            "user_text_sha256",
            "assistant_text_sha256",
            "record_sha256",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            return None, f"turn_record_missing:{','.join(missing)}"
        unsigned = {key: value for key, value in payload.items() if key not in {"record_sha256", "truth_boundary"}}
        if str(payload.get("record_sha256") or "") != _sha256(unsigned):
            return None, "turn_record_hash_mismatch"
        user = str(payload.get("user_text") or "")
        assistant = str(payload.get("assistant_text") or "")
        if str(payload.get("user_text_sha256") or "") != hashlib.sha256(user.encode("utf-8")).hexdigest():
            return None, "user_text_hash_mismatch"
        if str(payload.get("assistant_text_sha256") or "") != hashlib.sha256(assistant.encode("utf-8")).hexdigest():
            return None, "assistant_text_hash_mismatch"
        return dict(payload), None

    def append_finalized_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        trace_id: str,
        user_text: str,
        assistant_text: str,
        source: str,
        lock_timeout_seconds: float = 2.0,
    ) -> dict[str, Any]:
        record = ConversationTurnRecord.build(
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            user_text=user_text,
            assistant_text=assistant_text,
            source=source,
        )
        payload = self._record_payload(record)
        path = self._turn_path(record.session_id, record.turn_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path(record.session_id, record.turn_id)
        deadline = time.monotonic() + max(0.05, float(lock_timeout_seconds))
        lock_fd: int | None = None
        while lock_fd is None:
            try:
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    return {
                        "ok": False,
                        "status": "turn_commit_lock_timeout",
                        "path": str(path),
                        "session_id": record.session_id,
                        "turn_id": record.turn_id,
                    }
                time.sleep(0.01)
        try:
            os.write(lock_fd, record.turn_id.encode("utf-8"))
            os.fsync(lock_fd)
            if path.is_file():
                try:
                    existing_raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    return {
                        "ok": False,
                        "status": "existing_turn_unreadable",
                        "error_type": type(exc).__name__,
                        "path": str(path),
                        "session_id": record.session_id,
                        "turn_id": record.turn_id,
                    }
                existing, error = self._validate_payload(existing_raw)
                if error is not None or existing is None:
                    return {
                        "ok": False,
                        "status": "existing_turn_invalid",
                        "error": error,
                        "path": str(path),
                        "session_id": record.session_id,
                        "turn_id": record.turn_id,
                    }
                same_binding = all(
                    str(existing.get(key) or "") == str(payload.get(key) or "")
                    for key in (
                        "session_id",
                        "turn_id",
                        "trace_id",
                        "user_text_sha256",
                        "assistant_text_sha256",
                    )
                )
                return {
                    "ok": same_binding,
                    "status": "already_committed" if same_binding else "turn_commit_conflict",
                    "idempotent": same_binding,
                    "path": str(path),
                    "session_id": record.session_id,
                    "turn_id": record.turn_id,
                    "trace_id": record.trace_id,
                    "record_sha256": existing.get("record_sha256"),
                }
            _atomic_write_json(path, payload)
            return {
                "ok": True,
                "status": "committed",
                "idempotent": False,
                "path": str(path),
                "session_id": record.session_id,
                "turn_id": record.turn_id,
                "trace_id": record.trace_id,
                "record_sha256": payload["record_sha256"],
            }
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    def load_context_projection(
        self,
        session_id: str,
        *,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> dict[str, Any]:
        try:
            turn_limit = max(0, int(max_turns))
        except (TypeError, ValueError):
            turn_limit = DEFAULT_MAX_TURNS
        try:
            char_limit = max(0, int(max_chars))
        except (TypeError, ValueError):
            char_limit = DEFAULT_MAX_CHARS
        session_dir = self._session_dir(session_id)
        records: list[dict[str, Any]] = []
        invalid_count = 0
        if session_dir.is_dir():
            for path in session_dir.glob("*.json"):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    invalid_count += 1
                    continue
                record, error = self._validate_payload(raw)
                if error is not None or record is None:
                    invalid_count += 1
                    continue
                if str(record.get("session_id") or "") != str(session_id):
                    invalid_count += 1
                    continue
                records.append(record)
        records.sort(key=lambda item: (str(item.get("accepted_at_utc") or ""), str(item.get("turn_id") or "")))
        selected_reverse: list[dict[str, Any]] = []
        selected_chars = 0
        for record in reversed(records):
            if len(selected_reverse) >= turn_limit:
                break
            user_text = str(record.get("user_text") or "")
            assistant_text = str(record.get("assistant_text") or "")
            cost = len(user_text) + len(assistant_text)
            if selected_reverse and selected_chars + cost > char_limit:
                break
            if not selected_reverse and cost > char_limit and char_limit > 0:
                remaining = max(0, char_limit)
                user_budget = min(len(user_text), remaining // 2)
                assistant_budget = max(0, remaining - user_budget)
                user_text = user_text[-user_budget:] if user_budget else ""
                assistant_text = assistant_text[-assistant_budget:] if assistant_budget else ""
                cost = len(user_text) + len(assistant_text)
            selected_reverse.append(
                {
                    "turn_id": str(record.get("turn_id") or ""),
                    "trace_id": str(record.get("trace_id") or ""),
                    "user_text": user_text,
                    "assistant_text": assistant_text,
                    "accepted_at_utc": str(record.get("accepted_at_utc") or ""),
                    "source": str(record.get("source") or "runtime"),
                }
            )
            selected_chars += cost
        selected = list(reversed(selected_reverse))
        omitted = max(0, len(records) - len(selected))
        projection: dict[str, Any] = {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "session_id": str(session_id),
            "turns": selected,
            "total_turn_count": len(records),
            "selected_turn_count": len(selected),
            "omitted_turn_count": omitted,
            "invalid_record_count": invalid_count,
            "max_turns": turn_limit,
            "max_chars": char_limit,
            "selected_chars": selected_chars,
            "compaction_mode": "bounded_non_destructive_projection",
            "source_of_truth": "workspace_runtime/conversation_state per-turn accepted records",
            "truth_boundary": (
                "Older accepted turns are omitted only from the model-facing projection. "
                "Their durable records are not deleted, summarized into canon, or rewritten."
            ),
        }
        projection["projection_sha256"] = _sha256(projection)
        return projection
