"""External SYSTEM-side final validator; never instantiate a conversation owner."""
from __future__ import annotations

import io
import json
import sys
from typing import Any


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


def main() -> int:
    raw = sys.stdin.buffer.read(2097153)
    if len(raw) > 2097152:
        raise ValueError("Final validation input limit")
    data = json.loads(raw)
    result = validate(data["payload"], data["request_id"], data.get("session_id"))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
