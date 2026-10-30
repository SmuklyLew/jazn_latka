"""Immutable RC source evidence never trusts a bare provenance JSON claim."""
from __future__ import annotations
from tools.jazn_run_studio.tpa_triage import triage_cases, ZALICZONE, DO_POWTORZENIA, NIEAKTUALNE


def identity(sha: str, verified: bool = True) -> dict:
    return {
        "version": ".37", "version_sha256": "same-version-py",
        "git_sha": None, "release_verified": verified,
        "release_manifest_sha256": sha,
        "release_source_commit": "a" * 40,
        "release_runtime_version": "release-v37",
    }


def classify(current: dict, previous: dict) -> str:
    result = {
        "source": previous, "started_utc": "2026-10-30T08:00:00Z",
        "results": [{"case_id": "chat-resume", "status": "PASS", "full_gate": "PASS"}],
    }
    return triage_cases([{"id": "chat-resume"}], [result], current)["chat-resume"]["state"]


def test_verified_identical_export_can_be_received_without_git():
    assert classify(identity("a" * 64), identity("a" * 64)) == ZALICZONE


def test_missing_verified_manifest_cannot_prove_old_full_gate():
    assert classify(identity("a" * 64, False), identity("a" * 64)) == DO_POWTORZENIA


def test_changed_manifest_cannot_reuse_operator_approval():
    assert classify(identity("a" * 64), identity("b" * 64)) == NIEAKTUALNE


def test_forged_release_flag_alone_is_not_enough():
    suspicious = identity("a" * 64)
    suspicious.pop("release_manifest_sha256")
    assert classify(identity("a" * 64), suspicious) == NIEAKTUALNE
