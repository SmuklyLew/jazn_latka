from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path
from typing import Any, Mapping

from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError,
    host_request_lifecycle_by_daemon_request_id,
)
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("turn_settlement")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RECOVERABLE_EXECUTION_ERRORS = frozenset({"runtime_turn_not_accepted"})


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sha_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def execution_failure_allows_durable_settlement_recovery(error_code: str | None) -> bool:
    """Return whether a daemon execution rejection may defer to bound durable phase-1 state."""

    return str(error_code or "").strip() in _RECOVERABLE_EXECUTION_ERRORS


def resolve_durable_turn_settlement(
    root: Path,
    *,
    daemon_request_id: str,
    expected_user_text: str | None = None,
    expected_user_text_sha256: str | None = None,
) -> dict[str, Any]:
    """Resolve and validate the canonical durable settlement for one daemon request.

    Once phase-1 has been durably bound, the host-request store is the settlement
    authority.  The daemon job remains the execution/supervision projection and
    must reconcile to this record instead of inventing an independent terminal
    truth after a recoverable ``runtime_turn_not_accepted`` rejection.
    """

    try:
        lifecycle = host_request_lifecycle_by_daemon_request_id(
            Path(root), daemon_request_id=str(daemon_request_id or "")
        )
    except HostRequestStoreError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "found": False,
            "valid": False,
            "state": "invalid",
            "settlement_state": "invalid",
            "authority": "durable_host_request_store",
            "violations": [str(exc)],
        }
    if lifecycle.get("found") is not True:
        return {
            "schema_version": SCHEMA_VERSION,
            "found": False,
            "valid": False,
            "state": "missing",
            "settlement_state": "missing",
            "authority": "durable_host_request_store",
            "violations": ["durable_host_settlement_missing"],
        }

    binding = _mapping(lifecycle.get("binding"))
    contract_hash = str(lifecycle.get("request_contract_hash") or "").strip().lower()
    state = str(lifecycle.get("state") or "").strip()
    violations: list[str] = []
    required = ("daemon_request_id", "turn_id", "trace_id", "user_text_sha256")
    for key in required:
        if not str(binding.get(key) or "").strip():
            violations.append(f"missing_binding:{key}")
    if not _SHA256_RE.fullmatch(contract_hash):
        violations.append("invalid_request_contract_hash")
    bound_request_id = str(binding.get("daemon_request_id") or "").strip()
    if bound_request_id and not hmac.compare_digest(
        bound_request_id, str(daemon_request_id or "").strip()
    ):
        violations.append("daemon_request_id_binding_mismatch")

    expected_hash = str(expected_user_text_sha256 or "").strip().lower()
    if not _SHA256_RE.fullmatch(expected_hash) and expected_user_text is not None:
        expected_hash = _sha_text(expected_user_text)
    bound_user_hash = str(binding.get("user_text_sha256") or "").strip().lower()
    if expected_hash and not hmac.compare_digest(bound_user_hash, expected_hash):
        violations.append("user_text_binding_mismatch")

    settlement_state = {
        "pending": "awaiting_host_finalization",
        "claimed": "host_finalization_in_progress",
        "indeterminate": "host_finalization_indeterminate",
        "consumed": "accepted_final_committed",
        "expired": "host_finalization_expired",
    }.get(state, "invalid")
    if settlement_state == "invalid":
        violations.append(f"unsupported_durable_state:{state or 'missing'}")

    return {
        "schema_version": SCHEMA_VERSION,
        "found": True,
        "valid": not violations,
        "state": state,
        "settlement_state": settlement_state,
        "authority": "durable_host_request_store",
        "request_contract_hash": contract_hash,
        "binding": binding,
        "generation_context": _mapping(lifecycle.get("generation_context")),
        "daemon_finalization_notification_state": lifecycle.get(
            "daemon_finalization_notification_state"
        ),
        "violations": violations,
    }
