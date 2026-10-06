from __future__ import annotations

"""Idempotent projections of a candidate already accepted by the durable store."""

from pathlib import Path
from typing import Any, TYPE_CHECKING
import hashlib
import json

from latka_jazn.db.runtime_sqlite import runtime_sqlite_write_guard
from latka_jazn.memory.event_ledger import LedgerAppendResult, jsonl_shard_paths, RUNTIME_EVENTS_PREFIX

if TYPE_CHECKING:
    from latka_jazn.memory.event_ledger import RuntimeEventLedger
    from latka_jazn.core.epistemic_decision_ledger import EpistemicDecisionLedger
    from latka_jazn.core.finalization_service import FinalizationService
    from latka_jazn.core.host_finalization_transaction import HostFinalizationPorts


def _find_projection(paths: list[Path], *, turn_id: str, trace_id: str,
                     text: str, source: str, event: bool) -> LedgerAppendResult | None:
    found: LedgerAppendResult | None = None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    for path in paths:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("projection_record_not_object")
                if event:
                    if record.get("event_type") != "final_visible_assistant_reply":
                        continue
                    binding = record.get("payload") or {}
                    actual_text = record.get("exact_text")
                    actual_hash = binding.get("final_text_sha256")
                else:
                    if record.get("role") != "assistant":
                        continue
                    binding = record.get("metadata") or {}
                    if binding.get("entrypoint") != "append_final_visible_reply":
                        continue
                    actual_text = record.get("text")
                    actual_hash = record.get("text_sha256")
                if binding.get("turn_id") != turn_id:
                    continue
                if binding.get("trace_id") != trace_id or actual_text != text or actual_hash != digest or record.get("source") != source:
                    raise ValueError("committed_projection_binding_conflict")
                if found is not None:
                    raise ValueError("duplicate_committed_projection_detected")
                found = LedgerAppendResult(str(path), str(record.get("event_id") or ""),
                                           str(record.get("event_type") or ""),
                                           str(record.get("payload_sha256") or ""), 0)
    return found


def append_visible_projection_once(ledger: RuntimeEventLedger, envelope: dict[str, Any], *,
                                   final_text: str, source: str, client_context: dict[str, Any],
                                   timestamp_header: str) -> LedgerAppendResult:
    trace = dict(envelope.get("trace") or {})
    turn_id, trace_id = str(trace.get("turn_id") or ""), str(trace.get("trace_id") or "")
    if not turn_id or not trace_id:
        raise ValueError("committed_projection_lineage_missing")
    # Reuse the existing cross-process file guard. It opens no SQLite connection
    # for this JSONL path and serializes first publication with restart recovery.
    with runtime_sqlite_write_guard(ledger.conversation_turns_path):
        assistant = _find_projection([ledger.conversation_turns_path], turn_id=turn_id,
                                     trace_id=trace_id, text=final_text, source=source, event=False)
        event = _find_projection(jsonl_shard_paths(ledger.runtime_events_dir, RUNTIME_EVENTS_PREFIX),
                                 turn_id=turn_id, trace_id=trace_id, text=final_text, source=source, event=True)
        if assistant is None and event is None:
            result = ledger.append_final_visible_reply(
                envelope, final_text=final_text, source=source,
                client_context=client_context, local_time_label=timestamp_header,
            )
            if result is None:
                raise RuntimeError("final_visible_reply_ledger_write_failed")
            # The legacy append can return its event receipt even if append_turn
            # failed. Require both projections before reporting publication.
            if _find_projection([ledger.conversation_turns_path], turn_id=turn_id,
                                trace_id=trace_id, text=final_text, source=source, event=False) is None:
                raise RuntimeError("final_visible_assistant_projection_missing")
            return result
        if assistant is None:
            assistant = ledger.append_turn("assistant", final_text, source=source,
                client_context=client_context, local_time_label=timestamp_header,
                metadata={"entrypoint": "append_final_visible_reply", "turn_id": turn_id,
                          "trace_id": trace_id, "schema_version": envelope.get("schema_version")})
            if assistant is None:
                raise RuntimeError("final_visible_assistant_projection_failed")
        if event is not None:
            return event
        executor = str(client_context.get("generation_executor") or "runtime")
        payload = {"turn_id": turn_id, "trace_id": trace_id,
                   "schema_version": envelope.get("schema_version"),
                   "final_response_contract": envelope.get("final_response_contract") or {},
                   "dialogue_state": envelope.get("dialogue_state") or {},
                   "affect_mix": envelope.get("affect_mix") or {},
                   "final_text_sha256": hashlib.sha256(final_text.encode("utf-8")).hexdigest(),
                   "client_context": client_context, "generation_executor": executor}
        result = ledger.append_event("final_visible_assistant_reply",
            actor="chatgpt_host" if executor == "chatgpt_host" else "latka_runtime", source=source,
            payload=payload, tags=["final_visible_reply", "cognitive_turn_envelope", "timestamp_contract", ledger.version],
            importance=0.78, emotional_weight=0.45, canonical_impact=1,
            exact_text=final_text, local_time_label=timestamp_header)
        if result is None:
            raise RuntimeError("final_visible_event_projection_failed")
        return result


def append_epistemic_projection_once(ledger: EpistemicDecisionLedger, capture: dict[str, Any]) -> list[dict[str, Any]]:
    from latka_jazn.core.epistemic_decision_ledger import _bounded

    turn_id, trace_id = capture["turn_id"], capture["trace_id"]
    assessments = list(capture.get("epistemic_claims") or [])
    with runtime_sqlite_write_guard(ledger.path):
        rows = ledger.con.execute("SELECT * FROM epistemic_decisions WHERE turn_id=? AND trace_id=? ORDER BY seq",
                                  (turn_id, trace_id)).fetchall()
        if not rows:
            return [entry.to_dict() for entry in ledger.append_assessments(
                turn_id=turn_id, trace_id=trace_id, assessments=assessments)]
        if len(rows) != len(assessments):
            raise ValueError("epistemic_projection_count_conflict")
        output = []
        for row, claim in zip(rows, assessments):
            evidence = _bounded(claim.get("evidence_snapshot") or {})
            required = [str(item)[:160] for item in claim.get("required_evidence") or ()][:32]
            expected = (str(claim.get("kind") or "unknown")[:96], str(claim.get("status") or "unknown")[:96],
                        hashlib.sha256(str(claim.get("matched_text") or "").encode("utf-8")).hexdigest(),
                        str(claim.get("reason") or "unknown")[:256], required, evidence if isinstance(evidence, dict) else {})
            actual = (row["claim_kind"], row["claim_status"], row["matched_text_sha256"], row["reason"],
                      json.loads(row["required_evidence_json"]), json.loads(row["evidence_snapshot_json"]))
            if actual != expected:
                raise ValueError("epistemic_projection_binding_conflict")
            output.append({key: row[key] for key in ("turn_id", "trace_id", "claim_kind", "claim_status",
                          "matched_text_sha256", "reason", "previous_entry_sha256", "entry_sha256",
                          "created_at_unix", "schema_version")} | {"required_evidence": required, "evidence_snapshot": actual[-1]})
        return output


def recover_committed_projection(service: FinalizationService, *, turn_id: str,
                                request_id: str | None = None, ports: HostFinalizationPorts | None = None) -> dict[str, Any]:
    from latka_jazn.core.chatgpt_host_pending_store import read_committed_host_request
    from latka_jazn.core.finalization_service import FinalizationState

    record = read_committed_host_request(service.config.root, turn_id=turn_id)
    binding, capture = record["binding"], record["final_visible_capture"]
    if request_id and request_id != str(binding.get("daemon_request_id") or binding.get("turn_id") or ""):
        raise ValueError("recovery_request_binding_mismatch")
    if service.history:
        raise RuntimeError("recovery_requires_fresh_finalization_service")
    # Restore a proved durable commit, not a fresh validation/finalization run.
    service.history.append(FinalizationState.COMMIT_ACCEPTED)
    projected = service.publish_committed_capture(capture)
    result: dict[str, Any] = {"acceptance_state": "already_committed", "recovery_only": True,
                            "settlement_authority": "durable_host_request_store", "capture": projected}
    if ports is not None:
        for name, commit in (("conversation", ports.commit_conversation), ("session", ports.commit_session)):
            try:
                result[name] = commit(config=service.config, pending=record, binding=binding,
                                      final_visible_text=capture["final_visible_text"])
            except Exception as exc:
                result[name] = {"ok": False, "status": "projection_failed", "error_type": type(exc).__name__}
    return result
