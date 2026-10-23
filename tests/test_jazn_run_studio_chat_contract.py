"""Real canonical result shapes, strict binding and bounded transport parsing."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json

import pytest

from latka_jazn.core.runtime_daemon import _unwrap_daemon_chat_job
from tools.jazn_run_studio.chat_protocol import MAX_FRAME, frames
from tools.jazn_run_studio.validation_worker import validate


def completed_job() -> dict:
    text = "🕒 2026-10-23 00:00:00\n🙂 Łatka\n\nZaakceptowana tura testowa."
    result = {"ok": True, "answer_ok": True, "execution_state": "final_visible_answer",
        "host_finalization_pending": False, "session": {"session_id": "s"},
        "trace": {"turn_id": "t", "trace_id": "x"}, "final_visible_text": text,
        "final_visible_integrity": {"valid": True, "consensus": True,
                                    "text_sha256": sha256(text.encode()).hexdigest()},
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": True},
        "final_response_contract": {"author_source": "jazn_runtime", "turn_id": "t", "trace_id": "x"}}
    return {"request_id": "r", "session_id": "s", "done": True,
            "job_status": "completed", "result": result}


def test_canonical_live_bridge_and_poll_results_share_strict_binding() -> None:
    job = completed_job()
    direct = _unwrap_daemon_chat_job(job)
    assert "request_id" not in direct  # The live daemon shape which failed before.
    for payload in (direct, job):
        outcome = validate(payload, "r", "s")
        assert outcome["accepted"] is True
        assert (outcome["request_id"], outcome["session_id"], outcome["turn_id"], outcome["trace_id"]) == ("r", "s", "t", "x")
        assert outcome["text"] == job["result"]["final_visible_text"]
        assert validate(payload, "other", "s")["accepted"] is False
        assert validate(payload, "r", "other")["accepted"] is False


@pytest.mark.parametrize("damage", ["top_request", "job_session", "not_done", "failed_job",
    "trace", "contract_turn", "body", "truth_gate", "pending_finalization"])
def test_conflicting_or_unaccepted_result_never_exposes_text(damage: str) -> None:
    payload = deepcopy(_unwrap_daemon_chat_job(completed_job()))
    if damage == "top_request":
        payload["request_id"] = "other"
    elif damage == "job_session":
        payload["daemon_job"]["session_id"] = "other"
    elif damage == "not_done":
        payload["daemon_job"]["done"] = False
    elif damage == "failed_job":
        payload["daemon_job"]["job_status"] = "failed"
    elif damage == "trace":
        payload["trace_id"] = "other"
    elif damage == "contract_turn":
        payload["final_response_contract"]["turn_id"] = "other"
    elif damage == "body":
        payload["final_visible_text"] = "Unaccepted text"
    elif damage == "truth_gate":
        payload["runtime_truth_gate"]["normal_response_allowed"] = False
    else:
        payload["host_finalization_pending"] = True
    outcome = validate(payload, "r", "s")
    assert outcome["accepted"] is False
    assert "text" not in outcome


def test_transport_reads_jsonl_and_pretty_startup_error_without_releasing_raw_text() -> None:
    startup = {"ok": False, "error_code": "daemon_ensure_failed"}
    body = (json.dumps(startup, indent=2) + "\n\n" + json.dumps({"request_id": "r"}) + "\n").encode()
    assert list(frames(BytesIO(body))) == [startup, {"request_id": "r"}]


@pytest.mark.parametrize("raw", [b"[1]\n", b"not a protocol\n", b'{"partial":', b"{oops}\n"])
def test_invalid_or_truncated_transport_fails_closed(raw: bytes) -> None:
    with pytest.raises(ValueError):
        list(frames(BytesIO(raw)))


def test_transport_bounds_single_frame_even_without_newline() -> None:
    with pytest.raises(ValueError, match="chat_output_limit"):
        list(frames(BytesIO(b"{" + b" " * MAX_FRAME)))
