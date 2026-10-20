"""The host, not the Jaźń daemon, must supply the expected message set."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from latka_jazn.mcp.turn_coverage import audit_turn_coverage


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record(message_id: str, message: str, turn: str) -> dict:
    return {
        "message_id": message_id,
        "gate": {
            "host_pre_response_gate": True,
            "runtime_turn_invoked": True,
            "turn_ingress_gate_enforced": True,
            "host_route_bound": True,
            "host_routing_bypass_detected": False,
            "presentation_action": "generate_then_finalize",
            "user_text_sha256": _hash(message),
            "runtime_turn_id": turn,
            "trace_id": f"trace-{turn}",
        },
        "final": {
            "structuredContent": {
                "ok": True,
                "accepted": True,
                "action": "display_exact",
                "must_display_exactly": True,
                "turn_id": turn,
                "trace_id": f"trace-{turn}",
                "host_request_contract_hash": _hash(f"contract-{turn}"),
                "final_text_sha256": _hash("visible text"),
            },
        },
    }


def test_two_distinct_host_messages_are_accepted() -> None:
    expected = [
        {"message_id": "host-1", "user_text_sha256": _hash("Cześć")},
        {"message_id": "host-2", "user_text_sha256": _hash("Jak tam?")},
    ]
    observed = [_record("host-2", "Jak tam?", "turn-2"), _record("host-1", "Cześć", "turn-1")]
    result = audit_turn_coverage(expected, observed)
    assert result["ok"] is True
    assert result["accepted_count"] == 2
    assert result["chatgpt_platform_auto_routing_verified"] is False
    assert result["current_message_toolset_verified"] is False


def test_unseen_chatgpt_message_fails_coverage() -> None:
    expected = [
        {"message_id": "host-1", "user_text_sha256": _hash("hello")},
        {"message_id": "host-2", "user_text_sha256": _hash("follow-up")},
    ]
    result = audit_turn_coverage(expected, [_record("host-1", "hello", "turn-1")])
    assert not result["ok"]
    assert result["missing_message_ids"] == ["host-2"]


def test_no_host_manifest_never_promotes_daemon_turns() -> None:
    assert audit_turn_coverage([], [_record("host-1", "hi", "t1")])["reason_code"] == "expected_host_manifest_missing"


def test_host_digest_mismatch_rejected() -> None:
    expected = [{"message_id": "a", "user_text_sha256": _hash("original")}]
    assert audit_turn_coverage(expected, [_record("a", "paraphrased", "t1")])["unaccepted_message_ids"] == ["a"]


def test_host_route_bound_cannot_be_inferred_from_a_live_daemon() -> None:
    record = _record("a", "hello", "t1")
    record["gate"]["host_route_bound"] = False
    expected = [{"message_id": "a", "user_text_sha256": _hash("hello")}]
    assert not audit_turn_coverage(expected, [record])["ok"]


def test_pending_or_rejected_final_never_counts_as_accepted() -> None:
    record = _record("a", "hello", "t1")
    expected = [{"message_id": "a", "user_text_sha256": _hash("hello")}]
    record["final"]["structuredContent"]["action"] = "generate_then_finalize"
    assert not audit_turn_coverage(expected, [record])["ok"]
    record["final"]["structuredContent"]["action"] = "display_exact"
    record["final"]["structuredContent"]["accepted"] = False
    assert not audit_turn_coverage(expected, [record])["ok"]


def test_mismatched_lineage_cannot_be_reused_between_turns() -> None:
    expected = [
        {"message_id": "a", "user_text_sha256": _hash("a")},
        {"message_id": "b", "user_text_sha256": _hash("b")},
    ]
    rec1, rec2 = _record("a", "a", "one"), _record("b", "b", "one")
    result = audit_turn_coverage(expected, [rec1, rec2])
    assert not result["ok"]
    assert result["unaccepted_message_ids"] == ["b"]
    rec2["gate"]["runtime_turn_id"] = "two"
    assert not audit_turn_coverage(expected, [rec1, rec2])["ok"]


def test_replay_or_duplicate_record_rejected() -> None:
    expected = [{"message_id": "a", "user_text_sha256": _hash("hello")}]
    r = _record("a", "hello", "one")
    result = audit_turn_coverage(expected, [r, r])
    assert not result["ok"]
    assert result["reason_code"] == "duplicate_observed_message_id"


def test_unexpected_runtime_turn_rejected() -> None:
    expected = [{"message_id": "a", "user_text_sha256": _hash("hello")}]
    result = audit_turn_coverage(expected, [_record("a", "hello", "one"), _record("b", "hi", "two")])
    assert not result["ok"]
    assert result["unexpected_message_ids"] == ["b"]


def test_bad_receipt_without_hash_rejected() -> None:
    expected = [{"message_id": "a", "user_text_sha256": _hash("hello")}]
    r = _record("a", "hello", "one")
    r["final"]["structuredContent"]["host_request_contract_hash"] = ""
    assert not audit_turn_coverage(expected, [r])["ok"]


def test_cli_returns_nonzero_for_dropped_message(tmp_path: Path) -> None:
    expected = tmp_path / "expected.json"
    observed = tmp_path / "observed.json"
    expected.write_text(json.dumps([{"message_id": "a", "user_text_sha256": _hash("hello")}]), encoding="utf-8")
    observed.write_text("[]", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "latka_jazn.mcp.turn_coverage", "--expected", str(expected), "--observed", str(observed)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["missing_message_ids"] == ["a"]


def test_cli_success_for_complete_host_manifest(tmp_path: Path) -> None:
    expected = tmp_path / "expected.json"
    observed = tmp_path / "observed.json"
    expected.write_text(json.dumps([{"message_id": "a", "user_text_sha256": _hash("hello")}]), encoding="utf-8")
    observed.write_text(json.dumps([_record("a", "hello", "one")]), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "latka_jazn.mcp.turn_coverage", "--expected", str(expected), "--observed", str(observed)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["supplied_host_manifest_coverage_verified"] is True
