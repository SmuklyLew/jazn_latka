"""External SYSTEM-side final validator; never instantiate a conversation owner."""
from __future__ import annotations

import io
import json
import sys
from typing import Any


def validate(payload: dict[str, Any], request_id: str) -> dict[str, Any]:
    from latka_jazn.core.chat_command_contract import write_local_ollama_visible_reply
    nested = payload.get("result")
    candidate = nested if isinstance(nested, dict) else payload
    actual = candidate.get("request_id") or payload.get("request_id")
    if actual != request_id:
        return {"accepted": False, "error": "request_binding_mismatch"}
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
    return {"accepted": True, "text": output.getvalue(), "request_id": request_id,
            "turn_id": turn, "trace_id": trace_id}


def main() -> int:
    raw = sys.stdin.buffer.read(2097153)
    if len(raw) > 2097152:
        raise ValueError("Final validation input limit")
    data = json.loads(raw)
    result = validate(data["payload"], data["request_id"])
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
