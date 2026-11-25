"""External SYSTEM-side final validator; never instantiate a conversation owner."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def validate(payload: dict[str, Any], request_id: str, session_id: str | None = None) -> dict[str, Any]:
    from latka_jazn.core.chat_command_contract import write_local_ollama_visible_reply
    nested = payload.get("result")
    candidate = nested if isinstance(nested, dict) else payload
    job = candidate.get("daemon_job") or payload.get("daemon_job")
    job = job if isinstance(job, dict) else payload if isinstance(nested, dict) else {}
    # Completed canonical results keep request binding in daemon_job.
    bindings = [value for value in (candidate.get("request_id"), payload.get("request_id"),
                                   job.get("request_id")) if value is not None]
    if not bindings or any(value != request_id for value in bindings):
        return {"accepted": False, "error": "request_binding_mismatch"}
    if job and (job.get("done") is not True or job.get("job_status") != "completed"):
        return {"accepted": False, "error": "daemon_job_not_completed"}
    if session_id is not None:
        sessions = []
        for owner in (candidate.get("session"), candidate.get("conversation_session_authority"), job):
            if isinstance(owner, dict) and owner.get("session_id") is not None:
                sessions.append(owner["session_id"])
        if not sessions or any(value != session_id for value in sessions):
            return {"accepted": False, "error": "session_binding_mismatch"}
    output = io.StringIO()
    accepted = write_local_ollama_visible_reply(output, candidate)
    if not accepted:
        return {"accepted": False, "error": "local_runtime_final_not_accepted"}
    trace = candidate.get("trace")
    trace = trace if isinstance(trace, dict) else {}
    turn = candidate.get("turn_id") or trace.get("turn_id")
    trace_id = candidate.get("trace_id") or trace.get("trace_id")
    if not turn or not trace_id:
        return {"accepted": False, "error": "turn_lineage_missing"}
    contract = candidate.get("final_response_contract")
    contract = contract if isinstance(contract, dict) else {}
    for owner in (candidate, trace, contract):
        if ((owner.get("turn_id") is not None and owner["turn_id"] != turn)
                or (owner.get("trace_id") is not None and owner["trace_id"] != trace_id)):
            return {"accepted": False, "error": "turn_lineage_mismatch"}
    return {"accepted": True, "text": output.getvalue(), "request_id": request_id,
            "turn_id": turn, "trace_id": trace_id, "session_id": session_id}


def _job_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("result")
    candidate = nested if isinstance(nested, dict) else payload
    job = candidate.get("daemon_job") or payload.get("daemon_job")
    return job if isinstance(job, dict) else payload if isinstance(nested, dict) else {}


def validate_live(
    payload: dict[str, Any], request_id: str, session_id: str,
    *, root: Path, daemon_url: str,
) -> dict[str, Any]:
    """Independent read-only authority gate used by the Studio subprocess."""
    from latka_jazn.config import JaznConfig
    from latka_jazn.core.conversation_state_store import ConversationStateStore
    from latka_jazn.core.daemon_autostart import status_allows_runtime_turn
    from latka_jazn.core.message_envelope import MessageEnvelope
    from latka_jazn.core.runtime_daemon import chat_daemon_result, status_daemon

    def deny(code: str) -> dict[str, Any]:
        return {"accepted": False, "error": code, "must_not_replay": True}

    # The transport's claims must also pass the existing structural gate.
    received = validate(payload, request_id, session_id)
    if received.get("accepted") is not True:
        return received
    received_job = _job_snapshot(payload)
    instance = received_job.get("daemon_instance_id")
    if not isinstance(instance, str) or not instance:
        return deny("daemon_instance_missing")
    try:
        endpoint = urlsplit(daemon_url)
        port = endpoint.port
        if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1"
                or port is None or not 1 <= port <= 65535
                or endpoint.username is not None or endpoint.password is not None
                or endpoint.path not in {"", "/"} or endpoint.query or endpoint.fragment):
            return deny("daemon_endpoint_invalid")
        root = root.resolve()
        cfg = JaznConfig(root=root)
        status = status_daemon(cfg, host="127.0.0.1", port=port)
        if not (
            status_allows_runtime_turn(status)
            and status.get("endpoint_identity_matches") is True
            and status.get("endpoint_instance_matches") is True
            and status.get("heartbeat_fresh") is True
            and status.get("package_integrity_verified") is True
            and status.get("source_provenance_verified") is True
            and status.get("daemon_instance_id") == instance
            and status.get("active_root")
            and Path(str(status["active_root"])).resolve() == root
        ):
            return deny("daemon_authority_not_verified")
        live = chat_daemon_result(cfg, request_id, host="127.0.0.1", port=port, timeout=2.0)
        if not (
            live.get("accepted") is True
            and live.get("ok") is True
            and live.get("request_id") == request_id
            and live.get("session_id") == session_id
            and live.get("daemon_instance_id") == instance
            and live.get("done") is True
            and live.get("job_status") == "completed"
            and live.get("completed_at_utc")
            and live.get("awaiting_host_finalization") is False
        ):
            return deny("daemon_job_authority_not_verified")
        independent = validate(live, request_id, session_id)
        if independent.get("accepted") is not True or any(
            independent.get(key) != received.get(key)
            for key in ("request_id", "session_id", "turn_id", "trace_id", "text")
        ):
            return deny("independent_result_mismatch")
        candidate = live.get("result")
        if not isinstance(candidate, dict):
            return deny("daemon_result_missing")
        contract = candidate.get("final_response_contract")
        persistence = candidate.get("conversation_state_persistence")
        if not isinstance(contract, dict) or not isinstance(persistence, dict):
            return deny("finalization_evidence_missing")
        text = str(candidate.get("final_visible_text") or "")
        if (contract.get("turn_id") != independent["turn_id"]
                or contract.get("trace_id") != independent["trace_id"]
                or contract.get("final_visible_text") != text
                or contract.get("author_source") != "jazn_runtime"
                or not isinstance(contract.get("timestamp_trusted"), bool)):
            return deny("message_envelope_binding_mismatch")
        envelope = MessageEnvelope.build(
            timestamp_header=str(contract.get("timestamp_header") or ""),
            timezone=str(contract.get("timezone") or ""),
            timestamp_sample_iso=str(contract.get("timestamp_sample_iso") or ""),
            timestamp_source=str(contract.get("timestamp_source") or ""),
            timestamp_trusted=contract["timestamp_trusted"],
            author_id=str(contract.get("author_id") or ""),
            author_label=str(contract.get("author_label") or ""),
            author_source=str(contract.get("author_source") or ""),
            state_emoticon=str(contract.get("state_emoticon") or ""),
            body=str(contract.get("body") or contract.get("runtime_exact_text") or ""),
        )
        if envelope.render() != text or not envelope.timestamp_matches_sample():
            return deny("message_envelope_not_verified")
        if not (
            persistence.get("ok") is True
            and persistence.get("session_id") == session_id
            and persistence.get("turn_id") == independent["turn_id"]
            and persistence.get("trace_id") == independent["trace_id"]
            and ConversationStateStore(root).verify_turn_binding(
                session_id=session_id, turn_id=str(independent["turn_id"]),
                trace_id=str(independent["trace_id"]),
                user_text_sha256=str(live.get("user_text_sha256") or ""),
                assistant_text=text, record_sha256=str(persistence.get("record_sha256") or ""),
            )
        ):
            return deny("durable_turn_not_verified")
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
        return deny("authority_verification_unavailable")
    return {**independent, "daemon_instance_id": instance,
            "record_sha256": persistence["record_sha256"], "live_authority_verified": True}


def main() -> int:
    raw = sys.stdin.buffer.read(2097153)
    if len(raw) > 2097152:
        raise ValueError("Final validation input limit")
    data = json.loads(raw)
    if not isinstance(data.get("daemon_url"), str) or not isinstance(data.get("session_id"), str):
        result = {"accepted": False, "error": "live_authority_parameters_missing", "must_not_replay": True}
    else:
        result = validate_live(data["payload"], data["request_id"], data["session_id"],
                               root=Path.cwd(), daemon_url=data["daemon_url"])
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
