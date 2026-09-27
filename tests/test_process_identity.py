from __future__ import annotations

import os

from latka_jazn.core.process_identity import (
    PROCESS_FINGERPRINT_SCHEMA_VERSION,
    process_fingerprint,
    process_fingerprint_matches,
)


def test_process_fingerprint_binds_current_pid_to_creation_identity() -> None:
    observed = process_fingerprint(os.getpid())
    assert observed["schema_version"] == PROCESS_FINGERPRINT_SCHEMA_VERSION
    assert observed["pid"] == os.getpid()
    assert observed["state"] in {
        "observed",
        "alive_without_stable_token",
    }
    if observed["available"] is True:
        assert process_fingerprint_matches(observed, dict(observed)) is True


def test_process_fingerprint_rejects_forged_creation_identity() -> None:
    expected = {
        "schema_version": PROCESS_FINGERPRINT_SCHEMA_VERSION,
        "pid": 77,
        "platform": os.name,
        "available": True,
        "identity_token": "owner-token",
        "state": "observed",
    }
    observed = dict(expected)
    observed["identity_token"] = "reused-token"
    assert process_fingerprint_matches(expected, observed) is False


def test_process_fingerprint_reports_dead_pid_without_identity_probe() -> None:
    observed = process_fingerprint(
        999999,
        pid_is_alive=lambda _pid: False,
    )
    assert observed["available"] is False
    assert observed["state"] == "not_alive"
