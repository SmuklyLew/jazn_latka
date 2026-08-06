from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("chatgpt_host_pending_request")
DEFAULT_CONTINUATION_TTL_SECONDS = 60 * 60
LONG_WORK_CONTINUATION_TTL_SECONDS = 4 * 60 * 60
MIN_CONTINUATION_TTL_SECONDS = 30
MAX_CONTINUATION_TTL_SECONDS = 24 * 60 * 60
_TOKEN_PREFIX = "jct1"


class HostRequestStoreError(RuntimeError):
    """Raised when the two-phase ChatGPT host contract cannot be trusted."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def _continuation_secret_path(root: Path) -> Path:
    return _store_root(root) / "continuation.secret"


def _write_private_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_bytes(payload)
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _continuation_secret(root: Path) -> bytes:
    path = _continuation_secret_path(root)
    try:
        value = path.read_bytes()
    except FileNotFoundError:
        value = secrets.token_bytes(32)
        try:
            _write_private_bytes(path, value)
        except OSError as exc:
            raise HostRequestStoreError(f"continuation_secret_unwritable:{type(exc).__name__}") from exc
    except OSError as exc:
        raise HostRequestStoreError(f"continuation_secret_unreadable:{type(exc).__name__}") from exc
    if len(value) < 32:
        raise HostRequestStoreError("continuation_secret_invalid")
    return value


def _normalize_ttl(ttl_seconds: int | float | None) -> int:
    try:
        requested = int(ttl_seconds if ttl_seconds is not None else DEFAULT_CONTINUATION_TTL_SECONDS)
    except (TypeError, ValueError) as exc:
        raise HostRequestStoreError("continuation_ttl_invalid") from exc
    return max(MIN_CONTINUATION_TTL_SECONDS, min(requested, MAX_CONTINUATION_TTL_SECONDS))


LONG_WORK_INTENTS = frozenset({
    "external_research_request",
    "system_update_execution_request",
    "system_update_manifest_request",
    "runtime_behavior_diagnostic_request",
    "system_diagnostic_question",
    "self_architecture_audit_request",
    "post_update_coverage_audit_request",
    "external_tool_assistance_request",
    "memory_audit_request",
})
LONG_WORK_ROUTES = frozenset({
    "external_research",
    "system_update",
    "runtime_diagnostic_repair",
    "self_architecture_audit",
    "post_update_coverage_audit",
    "external_tool_assistance",
    "memory_audit",
})


def continuation_ttl_for_bridge(bridge: Mapping[str, Any]) -> int:
    """Return a bounded lease selected from immutable phase-1 work metadata."""
    summary_value = bridge.get("runtime_summary")
    summary: Mapping[str, Any] = summary_value if isinstance(summary_value, Mapping) else {}
    intent = str(summary.get("detected_intent") or bridge.get("detected_intent") or "").strip()
    route = str(summary.get("route") or bridge.get("route") or "").strip()
    if intent in LONG_WORK_INTENTS or route in LONG_WORK_ROUTES:
        return LONG_WORK_CONTINUATION_TTL_SECONDS
    return DEFAULT_CONTINUATION_TTL_SECONDS


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
    expires_at_utc: str
    generation_context: dict[str, Any] = field(default_factory=dict)
    regeneration_attempts: int = 0
    max_regeneration_attempts: int = 1
    last_regeneration_reason: str | None = None
    last_regeneration_at_utc: str | None = None
    continuation_token_sha256: str | None = None
    token_issued_at_utc: str | None = None
    claimed_at_utc: str | None = None
    consumed_at_utc: str | None = None
    expired_at_utc: str | None = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.{secrets.token_hex(6)}.tmp")
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


def _is_expired(record: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    expires = _parse_utc(record.get("expires_at_utc"))
    return bool(expires is not None and expires <= (now or _utc_now()))


def _expire_record(root: Path, source: Path, record: dict[str, Any], *, reason: str) -> dict[str, Any]:
    record["state"] = "expired"
    record["expired_at_utc"] = _utc_now().isoformat()
    record["expiration_reason"] = reason
    turn_id = str((record.get("binding") or {}).get("turn_id") or "")
    if not turn_id:
        raise HostRequestStoreError("pending_host_request_turn_id_missing")
    destination = _path(root, "expired", turn_id)
    _atomic_write(source, record)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    return record


def cleanup_expired_host_requests(root: Path, *, now: datetime | None = None) -> dict[str, int]:
    """Move expired pending/claimed records out of active state without enabling replay."""
    current = now or _utc_now()
    counts = {"pending_expired": 0, "claimed_expired": 0, "unreadable": 0}
    for state in ("pending", "claimed"):
        directory = _store_root(root) / state
        if not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            try:
                record = _read(path)
            except HostRequestStoreError:
                counts["unreadable"] += 1
                continue
            if not _is_expired(record, now=current):
                continue
            _expire_record(root, path, record, reason=f"{state}_ttl_elapsed")
            counts[f"{state}_expired"] += 1
    return counts


def persist_pending_host_request(
    root: Path,
    bridge: Mapping[str, Any],
    *,
    ttl_seconds: int | float | None = None,
) -> dict[str, Any]:
    cleanup_expired_host_requests(root)
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
    expired_path = _path(root, "expired", binding["turn_id"])
    if consumed_path.exists():
        raise HostRequestStoreError("host_request_already_consumed")
    if claimed_path.exists():
        raise HostRequestStoreError("host_request_already_claimed")
    if expired_path.exists():
        raise HostRequestStoreError("host_request_expired")
    if pending_path.exists():
        existing = _read(pending_path)
        if str(existing.get("request_contract_hash") or "") != calculated:
            raise HostRequestStoreError("pending_host_request_conflict")
        if _is_expired(existing):
            _expire_record(root, pending_path, existing, reason="pending_ttl_elapsed")
            raise HostRequestStoreError("host_request_expired")
        return existing
    now = _utc_now()
    ttl = _normalize_ttl(ttl_seconds)
    record = PendingHostRequest(
        state="pending",
        request_contract_hash=calculated,
        binding=binding,
        created_at_utc=now.isoformat(),
        expires_at_utc=(now + timedelta(seconds=ttl)).isoformat(),
        generation_context={
            'host_generation_policy': dict(bridge.get('host_generation_policy') or {}),
            'host_generation_rules': list(bridge.get('host_generation_rules') or []),
            'required_visible_prefix': bridge.get('required_visible_prefix'),
            'runtime_summary': dict(bridge.get('runtime_summary') or {}),
        },
    ).to_dict()
    _atomic_write(pending_path, record)
    return record


def _token_for_record(root: Path, record: Mapping[str, Any]) -> str:
    contract_hash = str(record.get("request_contract_hash") or "").strip().lower()
    binding_value = record.get("binding")
    binding: dict[str, Any] = binding_value if isinstance(binding_value, dict) else {}
    turn_id = str(binding.get("turn_id") or "").strip()
    created_at = str(record.get("created_at_utc") or "").strip()
    if not contract_hash or not turn_id or not created_at:
        raise HostRequestStoreError("continuation_binding_invalid")
    material = f"{SCHEMA_VERSION}\n{contract_hash}\n{turn_id}\n{created_at}".encode("utf-8")
    digest = hmac.new(_continuation_secret(root), material, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{_TOKEN_PREFIX}.{encoded}"


def issue_continuation_token(
    root: Path,
    *,
    turn_id: str,
    request_contract_hash: str,
) -> dict[str, Any]:
    cleanup_expired_host_requests(root)
    pending_path = _path(root, "pending", turn_id)
    record = _read(pending_path)
    if _is_expired(record):
        _expire_record(root, pending_path, record, reason="token_issue_after_expiry")
        raise HostRequestStoreError("host_request_expired")
    expected = str(record.get("request_contract_hash") or "")
    supplied = str(request_contract_hash or "").strip().lower()
    if expected != supplied:
        raise HostRequestStoreError("host_request_contract_hash_mismatch")
    token = _token_for_record(root, record)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    existing_hash = str(record.get("continuation_token_sha256") or "")
    if existing_hash and not hmac.compare_digest(existing_hash, token_hash):
        raise HostRequestStoreError("continuation_token_conflict")
    if not existing_hash:
        record["continuation_token_sha256"] = token_hash
        record["token_issued_at_utc"] = _utc_now().isoformat()
        _atomic_write(pending_path, record)
    return {
        "continuation_token": token,
        "expires_at_utc": record.get("expires_at_utc"),
        "turn_id": turn_id,
        "trace_id": (record.get("binding") or {}).get("trace_id"),
        "request_contract_hash": expected,
        "state": record.get("state"),
    }


def resolve_continuation_token(root: Path, token: str) -> dict[str, Any]:
    cleanup_expired_host_requests(root)
    candidate = str(token or "").strip()
    if not candidate.startswith(f"{_TOKEN_PREFIX}.") or len(candidate) > 256:
        raise HostRequestStoreError("continuation_token_invalid")
    candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    for state in ("pending", "claimed", "consumed", "expired"):
        directory = _store_root(root) / state
        if not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            record = _read(path)
            stored_hash = str(record.get("continuation_token_sha256") or "")
            if not stored_hash or not hmac.compare_digest(stored_hash, candidate_hash):
                continue
            expected_token = _token_for_record(root, record)
            if not hmac.compare_digest(expected_token, candidate):
                raise HostRequestStoreError("continuation_token_invalid")
            if state == "consumed":
                raise HostRequestStoreError("host_request_replay_detected")
            if state == "expired" or _is_expired(record):
                if state != "expired":
                    _expire_record(root, path, record, reason="token_resolve_after_expiry")
                raise HostRequestStoreError("host_request_expired")
            if state == "claimed":
                if str(record.get("state") or "") == "indeterminate":
                    raise HostRequestStoreError("host_request_persistence_indeterminate")
                raise HostRequestStoreError("host_request_in_progress")
            return record
    raise HostRequestStoreError("continuation_token_not_found")


def claim_pending_host_request(root: Path, *, turn_id: str, request_contract_hash: str) -> dict[str, Any]:
    cleanup_expired_host_requests(root)
    pending_path = _path(root, "pending", turn_id)
    claimed_path = _path(root, "claimed", turn_id)
    consumed_path = _path(root, "consumed", turn_id)
    expired_path = _path(root, "expired", turn_id)
    if consumed_path.exists():
        raise HostRequestStoreError("host_request_replay_detected")
    if expired_path.exists():
        raise HostRequestStoreError("host_request_expired")
    if claimed_path.exists():
        claimed = _read(claimed_path)
        if str(claimed.get("state") or "") == "indeterminate":
            raise HostRequestStoreError("host_request_persistence_indeterminate")
        raise HostRequestStoreError("host_request_in_progress")
    record = _read(pending_path)
    if _is_expired(record):
        _expire_record(root, pending_path, record, reason="claim_after_expiry")
        raise HostRequestStoreError("host_request_expired")
    expected = str(record.get("request_contract_hash") or "")
    if expected != str(request_contract_hash or "").strip().lower():
        raise HostRequestStoreError("host_request_contract_hash_mismatch")
    record["state"] = "claimed"
    record["claimed_at_utc"] = _utc_now().isoformat()
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
    if _is_expired(record):
        _expire_record(root, claimed_path, record, reason="release_after_expiry")
        return
    record["state"] = "pending"
    record["claimed_at_utc"] = None
    pending_path = _path(root, "pending", turn_id)
    _atomic_write(claimed_path, record)
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(claimed_path, pending_path)


def request_host_regeneration(root: Path, *, turn_id: str, reason: str) -> dict[str, Any]:
    claimed_path = _path(root, 'claimed', turn_id)
    record = _read(claimed_path)
    attempts = int(record.get('regeneration_attempts') or 0)
    maximum = int(record.get('max_regeneration_attempts') or 1)
    if attempts >= maximum:
        _expire_record(root, claimed_path, record, reason='regeneration_budget_exhausted')
        raise HostRequestStoreError('host_regeneration_budget_exhausted')
    record['state'] = 'pending'
    record['claimed_at_utc'] = None
    record['regeneration_attempts'] = attempts + 1
    record['last_regeneration_reason'] = str(reason or 'host_finalization_rejected')
    record['last_regeneration_at_utc'] = _utc_now().isoformat()
    pending_path = _path(root, 'pending', turn_id)
    _atomic_write(claimed_path, record)
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(claimed_path, pending_path)
    return record


def mark_claimed_host_request_indeterminate(root: Path, *, turn_id: str, error: str) -> dict[str, Any]:
    """Fail closed after persistence starts and its exact outcome cannot be proven."""
    claimed_path = _path(root, "claimed", turn_id)
    record = _read(claimed_path)
    record["state"] = "indeterminate"
    record["persistence_error"] = str(error or "host_visible_reply_persistence_failed")
    record["indeterminate_at_utc"] = _utc_now().isoformat()
    _atomic_write(claimed_path, record)
    return record


def consume_claimed_host_request(root: Path, *, turn_id: str, request_contract_hash: str) -> dict[str, Any]:
    claimed_path = _path(root, "claimed", turn_id)
    record = _read(claimed_path)
    if str(record.get("request_contract_hash") or "") != str(request_contract_hash or "").strip().lower():
        raise HostRequestStoreError("host_request_contract_hash_mismatch")
    record["state"] = "consumed"
    record["consumed_at_utc"] = _utc_now().isoformat()
    consumed_path = _path(root, "consumed", turn_id)
    _atomic_write(claimed_path, record)
    consumed_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(claimed_path, consumed_path)
    return record


def host_request_store_status(root: Path) -> dict[str, Any]:
    cleanup = cleanup_expired_host_requests(root)
    counts: dict[str, int] = {}
    for state in ("pending", "claimed", "consumed", "expired"):
        directory = _store_root(root) / state
        counts[state] = len(list(directory.glob("*.json"))) if directory.is_dir() else 0
    return {
        "schema_version": SCHEMA_VERSION,
        "counts": counts,
        "cleanup": cleanup,
        "continuation_ttl_default_seconds": DEFAULT_CONTINUATION_TTL_SECONDS,
        "continuation_ttl_long_work_seconds": LONG_WORK_CONTINUATION_TTL_SECONDS,
        "replay_protection": True,
        "max_host_regeneration_attempts": 1,
        "plaintext_tokens_persisted": False,
    }
