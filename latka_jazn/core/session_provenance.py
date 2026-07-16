from __future__ import annotations

from typing import Any, Mapping
import hashlib
import re

from latka_jazn.version import schema_version
from latka_jazn.core.visible_integrity import validate_result_integrity

SCHEMA_VERSION = schema_version("session_provenance")

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
        "background_process_claim_allowed": False,
        "truth_boundary": truth_boundary,
        **save_status,
    }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _body(text: str, timestamp_header: str) -> str:
    value = str(text or "").strip()
    if timestamp_header and value.startswith(timestamp_header):
        value = value[len(timestamp_header):].lstrip()
        if "\n" in value:
            envelope_line, remainder = value.split("\n", 1)
            if len(envelope_line.strip()) <= 8:
                value = remainder
    return re.sub(r"\s+", " ", value.strip())


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
        and contract_text.startswith(timestamp_header)
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
    trace = repaired.get("trace") if isinstance(repaired.get("trace"), dict) else {}
    timestamp_header = str((trace or {}).get("timestamp_header") or "")
    if not timestamp_header:
        return repaired, audit

    final_text = str(repaired.get("final_visible_text") or "").strip()
    contract = repaired.get("final_response_contract") if isinstance(repaired.get("final_response_contract"), dict) else {}
    contract_text = str((contract or {}).get("final_visible_text") or "").strip()
    provenance = repaired.get("runtime_provenance") if isinstance(repaired.get("runtime_provenance"), dict) else {}
    provenance_hash_before = str(provenance.get("visible_answer_hash") or "")
    body_unchanged = bool(final_text and _body(final_text, timestamp_header) == _body(contract_text, timestamp_header))
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
