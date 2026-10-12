from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation_runner import ConversationRunner
from latka_jazn.core.chatgpt_host_pending_store import read_committed_host_request, HostRequestStoreError
from latka_jazn.core.epistemic_decision_ledger import EpistemicDecisionLedger
from latka_jazn.core.finalization_projection_recovery import append_epistemic_projection_once
from latka_jazn.memory.event_ledger import RuntimeEventLedger
from test_finalization_crash_atomicity import _request, _finalize


def _records(root: Path):
    records = []
    for path in root.rglob("*.jsonl"):
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return records


def _recover(root: Path, turn_id: str):
    return ConversationRunner.recover_projection(config=JaznConfig(root=root), turn_id=turn_id)


def test_restart_repairs_accepted_unpublished_capture_without_refinalizing_or_duplicates(tmp_path: Path, monkeypatch):
    reply = _request(tmp_path)
    with monkeypatch.context() as fault:
        fault.setattr(RuntimeEventLedger, "append_final_visible_reply", lambda *args, **kwargs: None)
        result, errors = _finalize(tmp_path, reply)
    assert not errors and result is not None
    assert result["host_visible_reply_capture"]["projection_status"] == "pending_recovery"
    committed_before = read_committed_host_request(tmp_path, turn_id=reply["turn_id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        recovered = list(pool.map(lambda _: _recover(tmp_path, reply["turn_id"]), range(2)))
    for value in recovered:
        assert value["acceptance_state"] == "already_committed"
        assert value["recovery_only"] is True
        assert value["capture"]["projection_status"] == "published"
    records = _records(tmp_path)
    assert len([row for row in records if row.get("event_type") == "final_visible_assistant_reply"]) == 1
    assert len([row for row in records if row.get("role") == "assistant"]) == 1
    assert read_committed_host_request(tmp_path, turn_id=reply["turn_id"]) == committed_before
    replay, errors = _finalize(tmp_path, reply)
    assert replay is None and errors == ["host_request:host_request_replay_detected"]


def test_crash_between_assistant_and_event_repairs_only_missing_projection(tmp_path: Path, monkeypatch):
    reply = _request(tmp_path)
    original = RuntimeEventLedger.append_event
    def fail_event(ledger, event_type, **kwargs):
        return None if event_type == "final_visible_assistant_reply" else original(ledger, event_type, **kwargs)
    with monkeypatch.context() as fault:
        fault.setattr(RuntimeEventLedger, "append_event", fail_event)
        result, errors = _finalize(tmp_path, reply)
    assert result is not None and not errors
    assert result["host_visible_reply_capture"]["projection_status"] == "pending_recovery"
    before = _records(tmp_path)
    assert len([row for row in before if row.get("role") == "assistant"]) == 1
    assert not [row for row in before if row.get("event_type") == "final_visible_assistant_reply"]
    assert _recover(tmp_path, reply["turn_id"])["capture"]["projection_status"] == "published"
    assert _recover(tmp_path, reply["turn_id"])["capture"]["projection_status"] == "published"
    after = _records(tmp_path)
    assert len([row for row in after if row.get("role") == "assistant"]) == 1
    assert len([row for row in after if row.get("event_type") == "final_visible_assistant_reply"]) == 1


def test_recovery_refuses_missing_commit_wrong_identity_and_tampered_capture(tmp_path: Path):
    with pytest.raises(HostRequestStoreError, match="committed_host_request_missing"):
        _recover(tmp_path, "missing")
    reply = _request(tmp_path)
    result, errors = _finalize(tmp_path, reply)
    assert result is not None and not errors
    with pytest.raises(ValueError, match="recovery_request_binding_mismatch"):
        ConversationRunner.recover_projection(config=JaznConfig(root=tmp_path), turn_id=reply["turn_id"], request_id="foreign")
    path = next(tmp_path.rglob("consumed/*.json"))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["final_visible_capture"]["final_visible_text"] += " forged text"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(HostRequestStoreError, match="capture_binding_mismatch"):
        _recover(tmp_path, reply["turn_id"])


def test_epistemic_projection_reuses_exact_entries_and_preserves_chain(tmp_path: Path):
    capture = {"turn_id": "accepted", "trace_id": "trace", "epistemic_claims": [
        {"kind": "runtime_state", "status": "grounded", "matched_text": "accepted fact", "reason": "runtime_evidence",
         "required_evidence": ["runtime"], "evidence_snapshot": {"available": True}}]}
    with EpistemicDecisionLedger(tmp_path / "epistemic.sqlite3") as ledger:
        first = append_epistemic_projection_once(ledger, capture)
        second = append_epistemic_projection_once(ledger, capture)
        assert first[0]["entry_sha256"] == second[0]["entry_sha256"]
        assert ledger.con.execute("SELECT COUNT(*) FROM epistemic_decisions").fetchone()[0] == 1
        assert ledger.validate_chain()["ok"] is True
        capture["epistemic_claims"][0]["matched_text"] = "substituted claim"
        with pytest.raises(ValueError, match="epistemic_projection_binding_conflict"):
            append_epistemic_projection_once(ledger, capture)
        assert ledger.con.execute("SELECT COUNT(*) FROM epistemic_decisions").fetchone()[0] == 1


def test_mcp_resume_repairs_committed_pending_projection_and_keeps_exact_display(tmp_path: Path, monkeypatch):
    from latka_jazn.mcp.tools import jazn_resume_visible_reply

    reply = _request(tmp_path)
    with monkeypatch.context() as fault:
        fault.setattr(RuntimeEventLedger, "append_final_visible_reply", lambda *args, **kwargs: None)
        result, errors = _finalize(tmp_path, reply)
    assert result is not None and not errors
    result["chatgpt_host_presentation"] = {
        "action": "display_exact", "final_visible_text": result["final_visible_text"],
        "turn_id": reply["turn_id"], "trace_id": reply["trace_id"], "must_display_exactly": True,
    }
    class Gateway:
        def result(self, request_id):
            assert request_id == reply["turn_id"]
            return result
    visible = jazn_resume_visible_reply.run(root=tmp_path, gateway=Gateway(), daemon_request_id=reply["turn_id"])
    assert visible["isError"] is False
    assert visible["structuredContent"]["action"] == "display_exact"
    assert visible["structuredContent"]["final_visible_text"] == result["final_visible_text"]
    assert visible["_meta"]["projection_recovery"]["capture"]["projection_status"] == "published"


def test_resume_rejects_shallow_acceptance_flags():
    from latka_jazn.mcp.tools.jazn_resume_visible_reply import _display_exact
    shallow = {"final_visible_text": "unproved", "final_visible_integrity": {"valid": True},
               "runtime_truth_gate": {"ok": True, "normal_response_allowed": True}}
    shown = {"final_visible_text": "unproved", "runtime_checks": {
        "final_visible_integrity_valid": True, "runtime_truth_gate_ok": True}}
    assert _display_exact(shallow, shown)["isError"] is True


def test_resume_rejects_substitution_of_accepted_final_text(tmp_path: Path):
    from latka_jazn.mcp.tools.jazn_resume_visible_reply import _display_exact
    reply = _request(tmp_path)
    result, errors = _finalize(tmp_path, reply)
    assert result is not None and not errors
    assert _display_exact(result, {"final_visible_text": result["final_visible_text"]})["isError"] is False
    assert _display_exact(result, {"final_visible_text": result["final_visible_text"] + " forged"})["isError"] is True
