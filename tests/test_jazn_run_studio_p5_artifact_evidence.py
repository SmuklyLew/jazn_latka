"""Synthetic P5 inspection regressions, no real EXE or private MEMORY."""
from hashlib import sha256
import json

import pytest

from tools.jazn_run_studio.p5_artifact_evidence import inspect_frozen_artifact

COMMIT = "a" * 40
PAYLOAD = b"synthetic-no-executable"
EXPECTED_SHA = sha256(PAYLOAD).hexdigest()


def inspect(exe, info, *, expected_sha=EXPECTED_SHA):
    return inspect_frozen_artifact(
        exe, info, expected_sha256=expected_sha,
        expected_source_commit=COMMIT,
    )


def test_quarantined_or_missing_exe_cannot_be_promoted(tmp_path):
    exe = tmp_path / "confidential-home" / "JaznRunStudio.exe"
    info = tmp_path / "BUILD_INFO.json"
    info.write_text(json.dumps({"source_commit": COMMIT, "layout": "onedir"}))
    actual = inspect(exe, info)
    assert not actual["exe_exists"]
    assert not actual["current_integrity_match"]
    assert actual["observed_exe_sha256"] is None
    assert actual["security_review"] == "HOLD"
    assert actual["offline_acceptance"] == "NOT_RUN"
    assert actual["independent_system_acceptance"] == "NOT_RUN"
    assert str(tmp_path) not in json.dumps(actual)
    assert "confidential-home" not in json.dumps(actual)


def test_current_bytes_can_match_without_av_clearance(tmp_path):
    exe, info = tmp_path / "Studio.exe", tmp_path / "BUILD_INFO.json"
    exe.write_bytes(PAYLOAD)
    info.write_text(json.dumps({"source_commit": COMMIT, "layout": "onedir"}))
    actual = inspect(exe, info)
    assert actual["current_integrity_match"]
    assert actual["observed_exe_sha256"] == EXPECTED_SHA
    assert actual["security_review"] == "HOLD"
    assert not actual["antivirus_false_positive_confirmed"]


@pytest.mark.parametrize("metadata", [
    {"source_commit": "b" * 40, "layout": "onedir"},
    {"source_commit": COMMIT, "layout": "onefile"},
    {"source_commit": COMMIT},
])
def test_incomplete_build_metadata_fails_closed(tmp_path, metadata):
    exe, info = tmp_path / "Studio.exe", tmp_path / "BUILD_INFO.json"
    exe.write_bytes(PAYLOAD)
    info.write_text(json.dumps(metadata))
    assert not inspect(exe, info)["current_integrity_match"]


def test_wrong_hash_and_malformed_metadata_are_not_success(tmp_path):
    exe, info = tmp_path / "Studio.exe", tmp_path / "BUILD_INFO.json"
    exe.write_bytes(PAYLOAD)
    info.write_text("malformed")
    assert not inspect(exe, info)["current_integrity_match"]
    info.write_text(json.dumps({"source_commit": COMMIT, "layout": "onedir"}))
    assert not inspect(exe, info, expected_sha="f" * 64)["current_integrity_match"]


def test_invalid_expected_identifiers_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="invalid_expected_sha256"):
        inspect(tmp_path / "app", tmp_path / "info", expected_sha="bad")
    with pytest.raises(ValueError, match="invalid_source_commit"):
        inspect_frozen_artifact(
            tmp_path / "app", tmp_path / "info",
            expected_sha256=EXPECTED_SHA, expected_source_commit="../bad"
        )
