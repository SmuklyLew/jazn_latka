"""TPA triage is read-only; historical PASS is never promoted."""
from copy import deepcopy

from tools.jazn_run_studio.tpa_triage import (
    NOWE, DO_POWTORZENIA, NIEAKTUALNE, ZALICZONE,
    local_queue_text, triage_cases, triage_summary,
)

CASES = [{"id": "chat-resume"}, {"id": "daemon-restart"}]
SOURCE = {"version": ".35", "version_sha256": "hash-current", "git_sha": "sha-current", "git_dirty": False}


def run(case="chat-resume", *, version=".35", sha="sha-current", version_hash="hash-current",
        result="PASS", full_gate="NOT_RUN", started="2026-10-30T01:00:00Z"):
    return {"started_utc": started,
            "source": {"version": version, "git_sha": sha, "version_sha256": version_hash,
                       "git_dirty": False},
            "results": [{"case_id": case, "status": result, "full_gate": full_gate}]}


def test_new_scenarios_are_not_claimed_passed():
    report = triage_cases(CASES, [], SOURCE)
    assert all(x["state"] == NOWE for x in report.values())


def test_passed_subtest_without_human_gate_needs_repeat():
    source = [run()]
    original = deepcopy(source)
    report = triage_cases(CASES, source, SOURCE)
    assert report["chat-resume"]["state"] == DO_POWTORZENIA
    assert source == original


def test_stale_sha_version_and_file_hash_do_not_reuse_pass():
    for fields in ({"sha": "sha-old"}, {"version": ".34"}, {"version_hash": "other"}):
        report = triage_cases(CASES, [run(full_gate="PASS", **fields)], SOURCE)
        assert report["chat-resume"]["state"] == NIEAKTUALNE


def test_missing_source_evidence_is_not_false_pass():
    current = {**SOURCE, "git_sha": None}
    assert triage_cases(CASES, [run(full_gate="PASS")], current)["chat-resume"]["state"] == DO_POWTORZENIA
    assert triage_cases(CASES, [run(full_gate="PASS", sha=None)], SOURCE)["chat-resume"]["state"] == DO_POWTORZENIA


def test_only_confirmed_human_gate_on_same_source_is_received():
    received = triage_cases(CASES, [run(full_gate="PASS"), run(case="daemon-restart", result="BLOCKED")], SOURCE)
    assert received["chat-resume"]["state"] == ZALICZONE
    assert received["daemon-restart"]["state"] == DO_POWTORZENIA
    assert triage_summary(received) == {ZALICZONE: 1, DO_POWTORZENIA: 1}


def test_local_queue_is_instructional_not_executable():
    txt = local_queue_text({"chat-resume": {"state": DO_POWTORZENIA, "reason": "ack"}})
    assert "PTY Windows" in txt
    assert "Do powtórzenia" in txt
    assert "Nieaktualne" in txt
    assert "full_gate PASS" in txt
