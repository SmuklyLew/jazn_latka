from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("host_action_evidence")
_MAX_ITEMS = 8
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_OPERATIONS = frozenset({
    "audit",
    "command",
    "deploy",
    "file_write",
    "process_start",
    "repo_update",
    "runtime_start",
    "test",
})


@dataclass(slots=True, frozen=True)
class HostActionEvidence:
    action_id: str
    turn_id: str
    trace_id: str
    host_request_contract_hash: str
    surface: str
    operation: str
    process_created: bool
    process_pid: int | None
    process_exit_code: int | None
    error_type: str | None
    command_sha256: str | None
    result_sha256: str | None
    schema_version: str = SCHEMA_VERSION

    @property
    def successful_process_action(self) -> bool:
        return self.process_created and self.process_exit_code == 0 and self.error_type is None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["successful_process_action"] = self.successful_process_action
        return payload


def _bounded(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _sha(value: Any, *, field: str) -> str | None:
    text = _bounded(value, 64).lower()
    if not text:
        return None
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{field}_must_be_sha256")
    return text


def _canonical_action_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"host_action:{hashlib.sha256(encoded).hexdigest()}"


def validate_host_action_evidence(
    value: Any,
    *,
    expected_turn_id: str,
    expected_trace_id: str,
    expected_request_contract_hash: str,
) -> dict[str, Any]:
    """Validate bounded host-local action attestations against one phase-2 binding.

    Host evidence is an authenticated-host attestation, not a claim that the
    local Jaźń runtime independently executed the process.  Raw command lines
    are intentionally excluded; callers may provide only digests plus bounded
    process telemetry.  Every item must bind to the exact turn, trace and
    phase-1 request contract before it may support a visible action claim.
    """

    if value is None:
        return {"ok": False, "evidence": [], "errors": ["host_action_evidence_missing"]}
    if not isinstance(value, list):
        return {"ok": False, "evidence": [], "errors": ["host_action_evidence_not_list"]}

    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    if len(value) > _MAX_ITEMS:
        errors.append("host_action_evidence_item_limit_exceeded")

    expected_turn = _bounded(expected_turn_id, 160)
    expected_trace = _bounded(expected_trace_id, 160)
    expected_hash = _bounded(expected_request_contract_hash, 64).lower()
    if not expected_turn or not expected_trace or not _SHA256_RE.fullmatch(expected_hash):
        errors.append("host_action_expected_binding_invalid")

    for index, raw in enumerate(value[:_MAX_ITEMS]):
        if not isinstance(raw, Mapping):
            errors.append(f"host_action_evidence_not_object:{index}")
            continue

        turn_id = _bounded(raw.get("turn_id"), 160)
        trace_id = _bounded(raw.get("trace_id"), 160)
        request_hash = _bounded(raw.get("host_request_contract_hash"), 64).lower()
        surface = _bounded(raw.get("surface"), 64).lower()
        operation = _bounded(raw.get("operation"), 64).lower()
        process_created = raw.get("process_created")
        process_pid_raw = raw.get("process_pid")
        process_exit_raw = raw.get("process_exit_code")
        error_type = _bounded(raw.get("error_type"), 160) or None

        if turn_id != expected_turn:
            errors.append(f"host_action_turn_id_mismatch:{index}")
        if trace_id != expected_trace:
            errors.append(f"host_action_trace_id_mismatch:{index}")
        if request_hash != expected_hash:
            errors.append(f"host_action_request_contract_hash_mismatch:{index}")
        if not _SLUG_RE.fullmatch(surface):
            errors.append(f"host_action_surface_invalid:{index}")
        if operation not in _ALLOWED_OPERATIONS:
            errors.append(f"host_action_operation_invalid:{index}")
        if not isinstance(process_created, bool):
            errors.append(f"host_action_process_created_not_bool:{index}")
            process_created = False

        process_pid: int | None
        if process_pid_raw is None:
            process_pid = None
        elif isinstance(process_pid_raw, int) and not isinstance(process_pid_raw, bool) and process_pid_raw > 0:
            process_pid = int(process_pid_raw)
        else:
            errors.append(f"host_action_process_pid_invalid:{index}")
            process_pid = None

        process_exit_code: int | None
        if process_exit_raw is None:
            process_exit_code = None
        elif isinstance(process_exit_raw, int) and not isinstance(process_exit_raw, bool):
            process_exit_code = int(process_exit_raw)
        else:
            errors.append(f"host_action_process_exit_code_invalid:{index}")
            process_exit_code = None

        try:
            command_sha = _sha(raw.get("command_sha256"), field="command_sha256")
            result_sha = _sha(raw.get("result_sha256"), field="result_sha256")
        except ValueError as exc:
            errors.append(f"host_action_{exc}:{index}")
            command_sha = None
            result_sha = None

        if process_created and process_pid is None:
            errors.append(f"host_action_process_pid_required:{index}")
        if process_created and process_exit_code is None:
            errors.append(f"host_action_process_exit_code_required:{index}")
        if process_exit_code not in {None, 0} and not error_type:
            errors.append(f"host_action_error_type_required_for_failure:{index}")
        if not command_sha:
            errors.append(f"host_action_command_sha256_required:{index}")

        canonical = {
            "schema_version": SCHEMA_VERSION,
            "turn_id": turn_id,
            "trace_id": trace_id,
            "host_request_contract_hash": request_hash,
            "surface": surface,
            "operation": operation,
            "process_created": bool(process_created),
            "process_pid": process_pid,
            "process_exit_code": process_exit_code,
            "error_type": error_type,
            "command_sha256": command_sha,
            "result_sha256": result_sha,
        }
        canonical["action_id"] = _canonical_action_id(canonical)
        canonical["successful_process_action"] = bool(
            canonical["process_created"]
            and canonical["process_exit_code"] == 0
            and canonical["error_type"] is None
        )
        normalized.append(canonical)

    return {
        "ok": bool(normalized) and not errors,
        "evidence": normalized,
        "errors": errors,
        "schema_version": SCHEMA_VERSION,
        "binding": {
            "turn_id": expected_turn,
            "trace_id": expected_trace,
            "host_request_contract_hash": expected_hash,
        },
        "truth_boundary": (
            "Accepted entries are bounded host-local attestations bound to one phase-2 request. "
            "They do not prove that the Jaźń runtime itself executed the host process."
        ),
    }


def host_action_attestations_to_epistemic_evidence(
    attestations: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    action_ids: list[str] = []
    actions: list[str] = []
    successful_action_ids: list[str] = []
    successful_actions: list[str] = []
    for raw in attestations or ():
        action_id = _bounded(raw.get("action_id"), 160)
        operation = _bounded(raw.get("operation"), 64).lower()
        surface = _bounded(raw.get("surface"), 64).lower()
        if not action_id.startswith("host_action:") or operation not in _ALLOWED_OPERATIONS or not surface:
            continue
        descriptor = f"{surface}:{operation}"[:160]
        if action_id not in action_ids:
            action_ids.append(action_id)
        if descriptor not in actions:
            actions.append(descriptor)
        if bool(raw.get("successful_process_action")):
            if action_id not in successful_action_ids:
                successful_action_ids.append(action_id)
            if descriptor not in successful_actions:
                successful_actions.append(descriptor)
        if len(action_ids) >= _MAX_ITEMS:
            break
    return {
        "host_action_count": len(action_ids),
        "host_action_ids": action_ids,
        "host_actions": actions[:_MAX_ITEMS],
        "host_successful_action_ids": successful_action_ids[:_MAX_ITEMS],
        "host_successful_actions": successful_actions[:_MAX_ITEMS],
        "host_attested": bool(action_ids),
        "runtime_independently_verified_execution": False,
    }


def merge_epistemic_external_evidence(*items: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        for key, value in item.items():
            if isinstance(value, list):
                existing = merged.setdefault(key, [])
                if not isinstance(existing, list):
                    merged[key] = list(value)
                    continue
                for element in value:
                    if element not in existing:
                        existing.append(element)
            elif key in {"host_attested"}:
                merged[key] = bool(merged.get(key)) or bool(value)
            elif key == "runtime_independently_verified_execution":
                merged[key] = bool(merged.get(key)) and bool(value) if key in merged else bool(value)
            else:
                merged[key] = value
    return merged
