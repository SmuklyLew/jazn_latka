"""Live PASS requires identity, accepted turns, display ACK and durable resume."""
import json

import pytest

from tools.jazn_run_studio.tpa_current_state import evidence_errors
from tools.jazn_run_studio.tpa_reports import safe_child
from tests.test_tpa_2_current_state import store


@pytest.mark.parametrize("missing", ["identity", "accepted", "ack", "admission"])
def test_incomplete_live_evidence_is_not_confirmed_success(store, missing):
    report = store.create(("chat-resume",), "python", {})
    report["execution"] = "live"
    row = report["results"][0]
    row.update(status="PASS", exit_code=0)
    evidence = {"identity": {"root_matches": True, "version_matches": True, "process_identity_confirmed": True,
        "endpoint_identity_matches": True, "heartbeat_fresh": True, "instance_id": "synthetic-instance"},
        "session_id": "synthetic-session", "turns": [{"accepted": True, "request_id": "same-request", "turn_id": "turn", "trace_id": "trace", "text": "synthetic"}],
        "displayed_request_ids": ["same-request"], "admission": {"confirmed": True, "request_id": "same-request"}}
    if missing == "identity":
        evidence["identity"]["heartbeat_fresh"] = False
    elif missing == "accepted":
        evidence["turns"][0]["accepted"] = False
    elif missing == "ack":
        evidence["displayed_request_ids"] = []
    else:
        evidence["admission"]["request_id"] = "foreign-request"
    name = "chat-resume.live.json"
    report["artifacts"].append(name)
    safe_child(store.folder(report["run_id"]), name).write_text(json.dumps({"result": {"status": "PASS", "evidence": evidence}, "cleanup": {"ok": True}}), encoding="utf-8")
    assert evidence_errors(store, report, row)
