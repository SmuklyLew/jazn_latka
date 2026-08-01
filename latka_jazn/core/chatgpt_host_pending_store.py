from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("chatgpt_host_pending_request")


class HostRequestStoreError(RuntimeError):
    """Raised when the two-phase ChatGPT host contract cannot be trusted."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HostRequestStoreError("turn_id_missing")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _store_root(root: Path) -> Path:
    return workspace_runtime_path(Path(root)) / "chatgpt_host_bridge"


def _path(root: Path, state: str, turn_id: str) -> Path:
    return _store_root(root) / state / f"{_safe_id(turn_id)}.json"


def canonical_host_request_binding(bridge: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable phase-1 fields that a phase-2 reply must match."""
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_version": str(bridge.get("runtime_version") or PACKAGE_VERSION_FULL),
        "phase": str(bridge.get("phase") or ""),
        "turn_id": str(bridge.get("turn_id") or ""),
        "trace_id": str(bridge.get("trace_id") or ""),
        "timestamp_header": str(bridge.get("timestamp_header") or ""),
        "timezone": str(bridge.get("timezone") or ""),
        "timestamp_sample_iso": str(bridge.get("timestamp_sample_iso") or ""),
        "timestamp_source": str(bridge.get("timestamp_source") or ""),
        "timestamp_trusted": bridge.get("timestamp_trusted"),
        "author_id": str(bridge.get("author_id") or ""),
        "author_label": str(bridge.get("author_label") or ""),
        "author_source": str(bridge.get("author_source") or ""),
        "state_emoticon": str(bridge.get("state_emoticon") or ""),
        "user_text_sha256": str(bridge.get("user_text_sha256") or ""),
        "finalization_contract_hash": str(bridge.get("finalization_contract_hash") or ""),
        "runtime_context_sha256": str(bridge.get("runtime_context_sha256") or ""),
    }


def calculate_host_request_contract_hash(bridge: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(canonical_host_request_binding(bridge))).hexdigest()


@dataclass(slots=True)
class PendingHostRequest:
    state: str
    request_contract_hash: str
    binding: dict[str, Any]
    created_at_utc: str
    claimed_at_utc: str | None = None
    consumed_at_utc: str | None = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HostRequestStoreError("pending_host_request_not_found") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HostRequestStoreError(f"pending_host_request_unreadable:{type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise HostRequestStoreError("pending_host_request_not_object")
    return value


def persist_pending_host_request(root: Path, bridge: Mapping[str, Any]) -> dict[str, Any]:
    binding = canonical_host_request_binding(bridge)
    if binding["phase"] != "host_visible_generation_requested":
        raise HostRequestStoreError("host_request_phase_invalid")
    required = (
        "turn_id", "trace_id", "timestamp_header", "timezone", "timestamp_sample_iso",
        "timestamp_source", "author_id", "author_label", "author_source", "state_emoticon",
        "user_text_sha256", "finalization_contract_hash", "runtime_context_sha256",
    )
    missing = [name for name in required if not str(binding.get(name) or "").strip()]
    if not isinstance(binding.get("timestamp_trusted"), bool):
        missing.append("timestamp_trusted")
    if missing:
        raise HostRequestStoreError("host_request_binding_missing:" + ",".join(missing))
    calculated = calculate_host_request_contract_hash(bridge)
    supplied = str(bridge.get("host_request_contract_hash") or "").strip().lower()
    if supplied != calculated:
        raise HostRequestStoreError("host_request_contract_hash_mismatch")
    pending_path = _path(root, "pending", binding["turn_id"])
    consumed_path = _path(root, "consumed", binding["turn_id"])
    claimed_path = _path(root, "claimed", binding["turn_id"])
    if consumed_path.exists():
        raise HostRequestStoreError("host_request_already_consumed")
    if claimed_path.exists():
        raise HostRequestStoreError("host_request_already_claimed")
    if pending_path.exists():
        existing = _read(pending_path)
        if str(existing.get("request_contract_hash") or "") != calculated:
            raise HostRequestStoreError("pending_host_request_conflict")
        return existing
    record = PendingHostRequest(
        state="pending",
        request_contract_hash=calculated,
        binding=binding,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
    ).to_dict()
    _atomic_write(pending_path, record)
    return record


def claim_pending_host_request(root: Path, *, turn_id: str, request_contract_hash: str) -> dict[str, Any]:
    pending_path = _path(root, "pending", turn_id)
    claimed_path = _path(root, "claimed", turn_id)
    consumed_path = _path(root, "consumed", turn_id)
    if consumed_path.exists():
        raise HostRequestStoreError("host_request_replay_detected")
    if claimed_path.exists():
        claimed = _read(claimed_path)
        if str(claimed.get("state") or "") == "indeterminate":
            raise HostRequestStoreError("host_request_persistence_indeterminate")
        raise HostRequestStoreError("host_request_in_progress")
    record = _read(pending_path)
    expected = str(record.get("request_contract_hash") or "")
    if expected != str(request_contract_hash or "").strip().lower():
        raise HostRequestStoreError("host_request_contract_hash_mismatch")
    record["state"] = "claimed"
    record["claimed_at_utc"] = datetime.now(timezone.utc).isoformat()
    claimed_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(pending_path, claimed_path)
    except FileNotFoundError as exc:
        if consumed_path.exists():
            raise HostRequestStoreError("host_request_replay_detected") from exc
        raise HostRequestStoreError("pending_host_request_not_found") from exc
    _atomic_write(claimed_path, record)
    return record


def release_claimed_host_request(root: Path, *, turn_id: str) -> None:
    claimed_path = _path(root, "claimed", turn_id)
    if not claimed_path.exists():
        return
    record = _read(claimed_path)
    record["state"] = "pending"
    record["claimed_at_utc"] = None
    pending_path = _path(root, "pending", turn_id)
    _atomic_write(claimed_path, record)
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(claimed_path, pending_path)


def mark_claimed_host_request_indeterminate(root: Path, *, turn_id: str, error: str) -> dict[str, Any]:
    """Fail closed after persistence starts and its exact outcome cannot be proven.

    The request stays non-replayable.  An operator may inspect the event ledger and
    the stored error before deciding whether manual recovery is safe.
    """
    claimed_path = _path(root, "claimed", turn_id)
    record = _read(claimed_path)
    record["state"] = "indeterminate"
    record["persistence_error"] = str(error or "host_visible_reply_persistence_failed")
    record["indeterminate_at_utc"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(claimed_path, record)
    return record


def consume_claimed_host_request(root: Path, *, turn_id: str, request_contract_hash: str) -> dict[str, Any]:
    claimed_path = _path(root, "claimed", turn_id)
    record = _read(claimed_path)
    if str(record.get("request_contract_hash") or "") != str(request_contract_hash or "").strip().lower():
        raise HostRequestStoreError("host_request_contract_hash_mismatch")
    record["state"] = "consumed"
    record["consumed_at_utc"] = datetime.now(timezone.utc).isoformat()
    consumed_path = _path(root, "consumed", turn_id)
    _atomic_write(claimed_path, record)
    consumed_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(claimed_path, consumed_path)
    return record
