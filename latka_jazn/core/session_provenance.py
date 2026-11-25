from __future__ import annotations

from typing import Any, Mapping
import hashlib

from latka_jazn.core.json_types import json_object
from latka_jazn.version import schema_version
from latka_jazn.core.visible_integrity import validate_result_integrity
from latka_jazn.core.message_envelope import normalize_newlines

SCHEMA_VERSION = schema_version("session_provenance")

def project_turn_session_load(
    *,
    session_id: str,
    initial_load_metadata: Mapping[str, Any],
    conversation_history: Mapping[str, Any],
    last_locally_accepted_turn_id: str | None,
    previous_user_text: str | None,
    previous_visible_text: str | None,
    history_allowed: bool,
    checkpoint_state_unchanged: bool = False,
) -> dict[str, Any]:
    """Project pre-turn continuity evidence without mutating load metadata.

    The canonical history store, not the session ID, process flag, counter,
    caller-supplied text or the current turn's save, supplies accepted history.
    A checkpoint's integrity alone does not prove that it contains the latest
    accepted turn. Historical worker initialization is reported separately.
    """
    initial_source = str(initial_load_metadata.get("session_loaded_from") or "new")
    initial_disk = initial_load_metadata.get("session_resurrected_from_disk") is True
    turns = conversation_history.get("turns")
    history_verified = bool(
        history_allowed
        and conversation_history.get("session_id") == session_id
        and conversation_history.get("invalid_record_count") == 0
        and conversation_history.get("projection_sha256")
        and isinstance(turns, list)
    )
    latest = (
        turns[-1]
        if history_verified and isinstance(turns, list) and turns
        and isinstance(turns[-1], Mapping)
        else {}
    )
    prior_turn_id = str(latest.get("turn_id") or "") or None
    prior_trace_id = str(latest.get("trace_id") or "") or None
    checkpoint_sha = initial_load_metadata.get("continuity_checkpoint_sha256")
    checkpoint_count = initial_load_metadata.get("continuity_turn_count")
    current_state_matches = (
        previous_user_text is not None
        and previous_visible_text is not None
        and latest.get("user_text") == previous_user_text
        and latest.get("assistant_text") == previous_visible_text
    )
    checkpoint_verified = bool(
        checkpoint_state_unchanged
        and isinstance(checkpoint_count, int)
        and not isinstance(checkpoint_count, bool)
        and checkpoint_count > 0
        and checkpoint_count == conversation_history.get("total_turn_count")
        and initial_disk
        and initial_load_metadata.get("session_checkpoint_integrity_verified") is True
        and initial_load_metadata.get("session_carryover_blocked") is not True
        and isinstance(checkpoint_sha, str)
        and len(checkpoint_sha) == 64
    )
    source = "new" if initial_source == "new" and not last_locally_accepted_turn_id else "carryover_unverified"
    evidence = "none"
    disk_used = False
    input_checkpoint_sha = None
    if not history_allowed:
        if source != "new":
            source = "carryover_disabled"
    elif prior_turn_id and prior_trace_id:
        if last_locally_accepted_turn_id == prior_turn_id and current_state_matches:
            source = "in_process"
            evidence = "previous_locally_accepted_turn"
        elif (
            checkpoint_verified
            and current_state_matches
            and initial_source in {"session_checkpoint", "latest_session_pointer"}
        ):
            source = initial_source
            evidence = "checkpoint_matches_accepted_history"
            disk_used = True
            input_checkpoint_sha = checkpoint_sha
        else:
            source = "accepted_session_history"
            evidence = "verified_accepted_history_projection"
    return {
        "session_loaded_from": source,
        "session_reused": evidence != "none",
        "session_resurrected_from_disk": disk_used,
        "session_initial_loaded_from": initial_source,
        "session_initial_resurrected_from_disk": initial_disk,
        "session_reuse_evidence": evidence,
        "session_prior_accepted_turn_id": prior_turn_id,
        "session_prior_accepted_trace_id": prior_trace_id,
        "session_history_verified_before_turn": history_verified,
        "session_history_count_before_turn": (
            conversation_history.get("total_turn_count", 0) if history_verified else None
        ),
        "session_input_checkpoint_sha256": input_checkpoint_sha,
    }


def build_session_provenance(
    *,
    session_id: str,
    client: str,
    lifecycle: str,
    process_reused: bool,
    engine_reused_between_turns: bool,
    load_metadata: dict[str, Any] | None = None,
    save_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    load_metadata = dict(load_metadata or {})
    save_status = dict(save_status or {})
    save_truth_boundary = save_status.pop("truth_boundary", None)
    truth_boundary = (
        "Sesja oznacza stan rozmowy w tym procesie i ewentualny zapis runtime_session_state. "
        "Nie oznacza, że po EOF, /exit albo zakończeniu batcha działa proces w tle."
    )
    if save_status and not save_status.get("session_state_saved", False):
        truth_boundary += " Zapis stanu sesji nie został potwierdzony; trwałość jest ograniczona do pamięci procesu."
    if save_truth_boundary:
        truth_boundary += f" {save_truth_boundary}"
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "client": client,
        "lifecycle": lifecycle,
        "process_reused": bool(process_reused),
        "engine_reused_between_turns": bool(engine_reused_between_turns),
        "session_reused": bool(load_metadata.get("session_reused", False)),
        "session_resurrected_from_disk": bool(load_metadata.get("session_resurrected_from_disk", False)),
        "session_loaded_from": str(load_metadata.get("session_loaded_from") or "new"),
        **{
            key: load_metadata[key]
            for key in (
                "session_initial_loaded_from",
                "session_initial_resurrected_from_disk",
                "session_reuse_evidence",
                "session_prior_accepted_turn_id",
                "session_prior_accepted_trace_id",
                "session_history_verified_before_turn",
                "session_history_count_before_turn",
                "session_input_checkpoint_sha256",
            )
            if key in load_metadata
        },
        "background_process_claim_allowed": False,
        "truth_boundary": truth_boundary,
        **save_status,
    }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _body(text: str, timestamp_header: str) -> str | None:
    value = normalize_newlines(text)
    if not timestamp_header or not value.startswith(timestamp_header + "\n"):
        return None
    remainder = value[len(timestamp_header) + 1:]
    if "\n\n" not in remainder:
        return None
    _author_line, body = remainder.split("\n\n", 1)
    return body


def _verified_contract_source(
    contract: Mapping[str, Any],
    provenance: Mapping[str, Any],
    timestamp_header: str,
) -> bool:
    contract_text = str(contract.get("final_visible_text") or "").strip()
    contract_body = str(contract.get("body") or contract.get("runtime_exact_text") or "").strip()
    provenance_text = str(provenance.get("visible_answer_text") or "").strip()
    provenance_hash = str(provenance.get("visible_answer_hash") or "").strip()
    runtime_text = str(provenance.get("exact_runtime_text") or "").strip()
    runtime_hash = str(provenance.get("runtime_text_hash") or "").strip()
    integrity = contract.get("final_visible_integrity")
    return bool(
        isinstance(integrity, Mapping)
        and integrity.get("valid") is True
        and contract_text.startswith(timestamp_header + "\n")
        and all(str(contract.get(field) or "").strip() for field in ("author_id", "author_label", "author_source", "state_emoticon"))
        and provenance_text == contract_text
        and provenance_hash == _sha(contract_text)
        and str(contract.get("visible_answer_hash") or provenance_hash) == provenance_hash
        and contract_body == runtime_text
        and runtime_hash == _sha(runtime_text)
        and str(contract.get("runtime_text_hash") or runtime_hash) == runtime_hash
    )


def repair_final_visible_integrity(result: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Restore only a missing envelope from an already verified final contract.

    Provenance text and hashes are evidence created before this boundary. They
    are never synchronized, recalculated, or replaced here.
    """
    repaired = dict(result or {})
    audit: list[dict[str, Any]] = []
    trace = json_object(repaired.get("trace"))
    timestamp_header = str(trace.get("timestamp_header") or "")
    if not timestamp_header:
        return repaired, audit

    final_text = str(repaired.get("final_visible_text") or "").strip()
    contract = json_object(repaired.get("final_response_contract"))
    contract_text = str(contract.get("final_visible_text") or "").strip()
    provenance = json_object(repaired.get("runtime_provenance"))
    provenance_hash_before = str(provenance.get("visible_answer_hash") or "")
    contract_body = str(contract.get("body") or contract.get("runtime_exact_text") or "")
    final_body = _body(final_text, timestamp_header) if final_text.startswith(timestamp_header + "\n") else final_text
    body_unchanged = bool(final_text and normalize_newlines(final_body) == normalize_newlines(contract_body))
    contract_verified = _verified_contract_source(contract, provenance, timestamp_header)
    missing_envelope_only = bool(
        final_text
        and not final_text.startswith(timestamp_header)
        and body_unchanged
        and contract_verified
    )
    if final_text != contract_text:
        applied = missing_envelope_only
        repaired_text = contract_text if applied else final_text
        if applied:
            repaired["final_visible_text"] = repaired_text
        audit.append({
            "schema_version": schema_version("final_visible_integrity_repair_audit"),
            "applied": applied,
            "original_visible_text_sha256": _sha(final_text),
            "repaired_visible_text_sha256": _sha(repaired_text),
            "repair_reason": "missing_timestamp_envelope" if applied else "repair_rejected",
            "repair_source": "verified_final_response_contract",
            "body_unchanged": body_unchanged,
            "provenance_hash_preserved": (
                provenance_hash_before == str(provenance.get("visible_answer_hash") or "")
            ),
            "contract_source_verified": contract_verified,
        })
    return repaired, audit


def validate_final_visible_integrity(result: dict[str, Any]) -> dict[str, Any]:
    return validate_result_integrity(result)
