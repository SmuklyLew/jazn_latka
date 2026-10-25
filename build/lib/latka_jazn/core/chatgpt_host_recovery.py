from __future__ import annotations

import hmac
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from latka_jazn.core.chatgpt_host_executor_contract import (
    HostCapabilitySnapshot,
    HostExecutorObservation,
    HostExecutorRecoveryDecision,
    aggregate_host_executor_observations,
    classify_host_executor_observation,
)
from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError,
    cleanup_expired_host_requests,
    issue_continuation_token,
    read_committed_host_request,
)
from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("chatgpt_host_recovery")


def _bridge_store_root(root: Path) -> Path:
    return workspace_runtime_path(Path(root)) / "chatgpt_host_bridge"


def _read_record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HostRequestStoreError("pending_host_request_not_found") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HostRequestStoreError(
            f"pending_host_recovery_record_unreadable:{type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise HostRequestStoreError("pending_host_recovery_record_not_object")
    return value


def _binding(record: Mapping[str, Any]) -> dict[str, Any]:
    value = record.get("binding")
    if not isinstance(value, Mapping):
        raise HostRequestStoreError("pending_host_recovery_binding_missing")
    return dict(value)


def _generation_context(record: Mapping[str, Any]) -> dict[str, Any]:
    value = record.get("generation_context")
    return dict(value) if isinstance(value, Mapping) else {}


def _record_daemon_request_id(record: Mapping[str, Any]) -> str:
    binding = _binding(record)
    generation = _generation_context(record)
    return str(
        binding.get("daemon_request_id")
        or generation.get("daemon_request_id")
        or binding.get("turn_id")
        or ""
    ).strip()


def _matches_optional(value: str, expected: str | None) -> bool:
    if expected is None:
        return True
    return hmac.compare_digest(value, str(expected).strip())


def _state_error(state: str, record: Mapping[str, Any]) -> HostRequestStoreError:
    if state == "claimed":
        if str(record.get("state") or "") == "indeterminate":
            return HostRequestStoreError(
                "host_request_persistence_indeterminate", record=record
            )
        return HostRequestStoreError("host_request_in_progress", record=record)
    if state == "consumed":
        return HostRequestStoreError("host_request_replay_detected", record=record)
    if state == "expired":
        return HostRequestStoreError("host_request_expired", record=record)
    return HostRequestStoreError("pending_host_request_not_found")


def plan_host_executor_recovery(
    observation: HostExecutorObservation,
) -> HostExecutorRecoveryDecision:
    """Return the backwards-compatible recovery decision for one host surface.

    This function deliberately does not start, probe, or repair the local
    runtime itself.  A host-tool failure that happens before process creation is
    outside the Jaźń process boundary; callers that can observe more than one
    execution surface should use :func:`plan_host_capability_recovery` so one
    broken bridge is not mistaken for failure of the whole host environment.
    """

    return classify_host_executor_observation(observation)


def plan_host_capability_recovery(
    observations: Iterable[HostExecutorObservation],
) -> HostCapabilitySnapshot:
    """Aggregate independently observed executor surfaces into one host snapshot.

    The function is pure and performs no retries itself.  It preserves the
    bounded one-alternative-probe policy while allowing a working terminal (or
    another execution surface) to keep canonical discovery available when a
    separate bridge such as ``python_tool`` fails before process creation.
    """

    return aggregate_host_executor_observations(observations)


def recover_pending_host_request(
    root: Path,
    *,
    daemon_request_id: str,
    turn_id: str | None = None,
    request_contract_hash: str | None = None,
) -> dict[str, Any]:
    """Resolve exactly one still-pending phase-1 record without replaying a turn.

    Recovery is deliberately read-only with respect to the user turn.  It never
    submits user text and never moves a record from pending to claimed.  Claimed,
    consumed and expired records remain non-resumable and are surfaced as
    fail-closed store errors.
    """

    requested_id = str(daemon_request_id or "").strip()
    if not requested_id:
        raise HostRequestStoreError("daemon_request_id_missing")
    if len(requested_id) > 256:
        raise HostRequestStoreError("daemon_request_id_too_large")

    cleanup_expired_host_requests(Path(root))
    store_root = _bridge_store_root(Path(root))
    matches: list[tuple[str, dict[str, Any]]] = []

    for state in ("pending", "claimed", "consumed", "expired"):
        directory = store_root / state
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            record = _read_record(path)
            if _record_daemon_request_id(record) != requested_id:
                continue
            matches.append((state, record))

    if not matches:
        raise HostRequestStoreError("pending_host_request_not_found")
    if len(matches) != 1:
        raise HostRequestStoreError("pending_host_recovery_ambiguous")

    state, record = matches[0]
    if state != "pending" or str(record.get("state") or "") != "pending":
        raise _state_error(state, record)

    binding = _binding(record)
    actual_turn_id = str(binding.get("turn_id") or "").strip()
    actual_hash = str(record.get("request_contract_hash") or "").strip().lower()
    if not actual_turn_id or len(actual_hash) != 64:
        raise HostRequestStoreError("pending_host_recovery_binding_invalid")
    if not _matches_optional(actual_turn_id, turn_id):
        raise HostRequestStoreError("pending_host_recovery_turn_mismatch")
    if request_contract_hash is not None:
        expected_hash = str(request_contract_hash).strip().lower()
        if not hmac.compare_digest(actual_hash, expected_hash):
            raise HostRequestStoreError("host_request_contract_hash_mismatch")
    return record


def reissue_pending_continuation(
    root: Path,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the deterministic continuation token for an existing pending lease."""

    binding = _binding(record)
    turn_id = str(binding.get("turn_id") or "").strip()
    request_contract_hash = str(record.get("request_contract_hash") or "").strip().lower()
    if not turn_id or len(request_contract_hash) != 64:
        raise HostRequestStoreError("pending_host_recovery_binding_invalid")
    return issue_continuation_token(
        Path(root),
        turn_id=turn_id,
        request_contract_hash=request_contract_hash,
    )


def recover_committed_host_presentation(
    root: Path,
    *,
    daemon_request_id: str,
    turn_id: str | None = None,
    request_contract_hash: str | None = None,
) -> dict[str, Any] | None:
    """Recover only delivery of an already-accepted reply (never execute a turn).

    The contract hash is compulsory for this local-disk fallback: possessing a
    possibly guessable daemon request id alone cannot expose private reply text.
    Returns None when no committed record matches, so normal daemon polling can
    still handle pending/claimed work. Malformed or ambiguous committed records
    fail closed rather than regenerating or replaying side effects.
    """
    request_id = str(daemon_request_id or "").strip()
    if not request_id or len(request_id) > 256:
        raise HostRequestStoreError("daemon_request_id_invalid")
    if request_contract_hash is None:
        return None
    expected_hash = str(request_contract_hash).strip().lower()
    if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
        raise HostRequestStoreError("host_request_contract_hash_invalid")
    directory = _bridge_store_root(Path(root)) / "consumed"
    if not directory.is_dir():
        return None
    matching: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        record = _read_record(path)
        if not hmac.compare_digest(_record_daemon_request_id(record), request_id):
            continue
        matching.append(record)
    if not matching:
        return None
    if len(matching) != 1:
        raise HostRequestStoreError("committed_host_recovery_ambiguous")
    record = matching[0]
    binding = _binding(record)
    accepted_turn_id = str(binding.get("turn_id") or "")
    if turn_id is not None and not hmac.compare_digest(accepted_turn_id, str(turn_id).strip()):
        raise HostRequestStoreError("committed_host_recovery_turn_mismatch")
    if not hmac.compare_digest(str(record.get("request_contract_hash") or "").lower(), expected_hash):
        raise HostRequestStoreError("host_request_contract_hash_mismatch")
    accepted = read_committed_host_request(Path(root), turn_id=accepted_turn_id)
    capture = accepted["final_visible_capture"]
    return {
        "ok": True,
        "action": "display_exact",
        "final_visible_text": capture["final_visible_text"],
        "final_text_sha256": capture["final_text_sha256"],
        "turn_id": accepted_turn_id,
        "trace_id": binding["trace_id"],
        "must_display_exactly": True,
        "recovered_existing_request": True,
        "recovered_committed_delivery_only": True,
        "must_not_resubmit_user_message": True,
    }
