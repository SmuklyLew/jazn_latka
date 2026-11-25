"""External SYSTEM-side final validator; never instantiate a conversation owner."""
from __future__ import annotations

import io
import json
import re
import sys
from datetime import datetime
from hashlib import sha256
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


def _verified_live_status(root: Path, daemon_url: str, instance: str | None = None) -> tuple[Any, int, str]:
    """One authority gate for admission, accepted results and terminal failures."""
    from latka_jazn.config import JaznConfig
    from latka_jazn.core.daemon_autostart import status_allows_runtime_turn
    from latka_jazn.core.runtime_daemon import status_daemon, validate_expected_daemon_instance

    endpoint = urlsplit(daemon_url)
    port = endpoint.port
    if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1"
            or port is None or not 1 <= port <= 65535
            or endpoint.username is not None or endpoint.password is not None
            or endpoint.path not in {"", "/"} or endpoint.query or endpoint.fragment):
        raise ValueError("daemon_endpoint_invalid")
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
        and (instance is None or status.get("daemon_instance_id") == instance)
        and status.get("active_root")
        and Path(str(status["active_root"])).resolve() == root
    ):
        raise ValueError("daemon_authority_not_verified")
    observed = validate_expected_daemon_instance(status.get("daemon_instance_id"))
    return cfg, port, observed


def _verified_live_job(root: Path, daemon_url: str, instance: str, request_id: str) -> dict[str, Any]:
    from latka_jazn.core.runtime_daemon import chat_daemon_result
    cfg, port, _observed = _verified_live_status(root, daemon_url, instance)
    return chat_daemon_result(cfg, request_id, host="127.0.0.1", port=port, timeout=2.0)


def prepare_admission(message: str, *, root: Path, daemon_url: str) -> dict[str, Any]:
    """Read-only pre-submit evidence; no inference or job creation."""
    from latka_jazn.core.chat_command_contract import guard_cli_flags_in_user_text
    try:
        original = message.strip()
        if not original or len(message.encode("utf-8")) > 65536:
            raise ValueError("invalid_message")
        effective, _warning = guard_cli_flags_in_user_text(original)
        _, _, instance = _verified_live_status(root, daemon_url)
        return {"admission_verified": True, "daemon_instance_id": instance,
                "user_text_sha256": sha256((effective or original).encode("utf-8")).hexdigest()}
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
        return {"admission_verified": False, "error": "daemon_admission_authority_unverified"}


def _terminal_failure_proof(job: dict[str, Any], request_id: str, session_id: str,
                            daemon_url: str) -> dict[str, str] | None:
    result = job.get("result")
    if not isinstance(result, dict):
        return None
    code = result.get("error_code")
    instance = job.get("daemon_instance_id")
    completed = job.get("completed_at_utc")
    user_hash = job.get("user_text_sha256")
    if not (
        job.get("accepted") is True and job.get("ok") is False
        and job.get("request_id") == request_id and job.get("session_id") == session_id
        and job.get("job_status") == "failed" and job.get("done") is True
        and job.get("awaiting_host_finalization") is False
        and job.get("phase_result_ready") is False and result.get("ok") is False
        and result.get("request_id", request_id) == request_id
        and not any(job.get(key) for key in
                    ("host_turn_id", "host_trace_id", "host_request_contract_hash"))
        and isinstance(instance, str) and 0 < len(instance) <= 256
        and isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_]{1,100}", code)
        and isinstance(user_hash, str) and re.fullmatch(r"[0-9a-f]{64}", user_hash)
        and isinstance(completed, str)
    ):
        return None
    try:
        if datetime.fromisoformat(completed.replace("Z", "+00:00")).utcoffset() is None:
            return None
    except ValueError:
        return None
    return {"request_id": request_id, "session_id": session_id, "error_code": code,
            "daemon_url": daemon_url, "daemon_instance_id": instance,
            "completed_at_utc": completed, "user_text_sha256": user_hash}


def validate_terminal_failure(
    payload: dict[str, Any], request_id: str, session_id: str,
    *, root: Path, daemon_url: str, expected_proof: dict[str, str] | None = None,
) -> dict[str, Any]:
    """A transport failure is never sufficient to release a pending request."""
    from latka_jazn.core.turn_settlement import resolve_durable_turn_settlement

    def deny(code: str) -> dict[str, Any]:
        return {"accepted": False, "terminal_failure_verified": False,
                "error": code, "must_not_replay": True}

    received = expected_proof if expected_proof is not None else _terminal_failure_proof(
        _job_snapshot(payload), request_id, session_id, daemon_url)
    if not received or any(received.get(k) != v for k, v in (
        ("request_id", request_id), ("session_id", session_id), ("daemon_url", daemon_url)
    )):
        return deny("terminal_failure_binding_missing")
    try:
        instance = received["daemon_instance_id"]
        if not isinstance(instance, str) or not instance:
            return deny("daemon_instance_missing")
        live = _verified_live_job(root, daemon_url, instance, request_id)
        proof = _terminal_failure_proof(live, request_id, session_id, daemon_url)
        if proof is None or proof != received:
            return deny("terminal_failure_independent_result_mismatch")
        settlement = resolve_durable_turn_settlement(
            root, daemon_request_id=request_id, expected_user_text_sha256=proof["user_text_sha256"])
        # A recoverable host settlement may supersede an execution rejection.
        # Missing is the only safe outcome here; invalid/ambiguous is not missing.
        if settlement.get("found") is not False or settlement.get("state") != "missing":
            return deny("terminal_failure_durable_settlement_unresolved")
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
        return deny("terminal_failure_authority_unavailable")
    return {"accepted": False, "terminal_failure_verified": True,
            "failure_proof": proof, "must_not_replay": True}


def validate_live(
    payload: dict[str, Any], request_id: str, session_id: str,
    *, root: Path, daemon_url: str,
) -> dict[str, Any]:
    """Independent read-only authority gate used by the Studio subprocess."""
    from latka_jazn.core.conversation_state_store import ConversationStateStore
    from latka_jazn.core.message_envelope import MessageEnvelope

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
        live = _verified_live_job(root, daemon_url, instance, request_id)
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
            "user_text_sha256": live["user_text_sha256"],
            "record_sha256": persistence["record_sha256"], "live_authority_verified": True}


def main() -> int:
    raw = sys.stdin.buffer.read(2097153)
    if len(raw) > 2097152:
        raise ValueError("Final validation input limit")
    data = json.loads(raw)
    if not isinstance(data.get("daemon_url"), str) or not isinstance(data.get("session_id"), str):
        result = {"accepted": False, "error": "live_authority_parameters_missing", "must_not_replay": True}
    elif data.get("mode") == "prepare_admission":
        message = data.get("message")
        result = (prepare_admission(message, root=Path.cwd(), daemon_url=data["daemon_url"])
                  if isinstance(message, str) else {"admission_verified": False})
    elif data.get("mode") == "terminal_failure":
        proof = data.get("expected_proof")
        if proof is not None and (not isinstance(proof, dict)
                                  or any(not isinstance(v, str) for v in proof.values())):
            result = {"accepted": False, "terminal_failure_verified": False,
                      "error": "terminal_failure_proof_invalid", "must_not_replay": True}
        else:
            result = validate_terminal_failure(
                data["payload"], data["request_id"], data["session_id"],
                root=Path.cwd(), daemon_url=data["daemon_url"], expected_proof=proof)
    else:
        result = validate_live(data["payload"], data["request_id"], data["session_id"],
                               root=Path.cwd(), daemon_url=data["daemon_url"])
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
