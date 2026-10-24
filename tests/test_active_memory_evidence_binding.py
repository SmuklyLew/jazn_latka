"""Signed synthetic observations cannot bypass independent runtime bindings."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from latka_jazn.core import active_memory_evidence as evidence
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.tools.memory_rebuild_app.p1_active_memory_readiness import assess_active_memory_readiness
from latka_jazn.version import PACKAGE_VERSION_FULL


@pytest.fixture
def observation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "system"
    root.mkdir()
    memory = tmp_path / "synthetic-memory"
    database = memory / "sqlite/memory_jazn.sqlite3"
    marker = tmp_path / "marker.json"
    pid = os.getpid()
    fingerprint = {"pid": pid, "synthetic_generation": 1}
    marker_payload = {"daemon_instance_id": "synthetic-instance", "daemon_pid": pid,
                      "runtime_version_full": PACKAGE_VERSION_FULL, "process_fingerprint": fingerprint}
    marker.write_text(json.dumps(marker_payload), encoding="utf-8")
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory))
    monkeypatch.setattr(evidence, "resolve_active_runtime_marker_path", lambda _: marker)
    monkeypatch.setattr(daemon, "status_daemon", lambda *a, **k: {
        "marker_valid": True, "resolved_active_root": str(root), "pid": pid,
        "package_integrity_verified": True, "source_provenance_verified": True,
        "runtime_version_full": PACKAGE_VERSION_FULL})
    monkeypatch.setattr(daemon, "read_daemon_auth_token", lambda _: "synthetic-token")
    monkeypatch.setattr(evidence, "process_fingerprint", lambda _: dict(fingerprint))
    monkeypatch.setattr(evidence, "process_fingerprint_matches", lambda a, b: a == b)
    monkeypatch.setattr(evidence, "_observe_process_command", lambda *_: True)
    monkeypatch.setattr(LivingMemoryGateway, "_candidate_native_database", staticmethod(lambda _: database))
    monkeypatch.setattr(evidence, "inspect_memory_database", lambda _: {"kind": "native_unified", "compatible": True})
    metadata = {"database_uuid": "synthetic-uuid", "trust_state": "trusted"}
    monkeypatch.setattr(evidence, "_database_metadata", lambda _: dict(metadata))
    options = {"damage": ""}

    def fetch(url: str, *, token: str) -> dict:
        response = {"schema_version": evidence.SCHEMA,
            "nonce": parse_qs(urlsplit(url).query)["nonce"][0],
            "identity": {"daemon_instance_id": "synthetic-instance", "daemon_pid": pid,
                "active_root": str(root), "runtime_process_active": True,
                "runtime_version": PACKAGE_VERSION_FULL, "process_fingerprint": fingerprint,
                "last_heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
                "heartbeat_interval_seconds": 1},
            "memory_root": str(memory), "database_path": str(database),
            "database_observation": "observed", "database_metadata": metadata}
        damage = options["damage"]
        if damage == "pid":
            response["identity"]["daemon_pid"] = pid + 1
        elif damage == "instance":
            response["identity"]["daemon_instance_id"] = "other-instance"
        elif damage == "root":
            response["identity"]["active_root"] = str(tmp_path / "other")
        elif damage == "heartbeat":
            response["identity"]["last_heartbeat_at_utc"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        elif damage == "generation":
            marker.write_text(json.dumps({**marker_payload, "daemon_instance_id": "restarted"}), encoding="utf-8")
        elif damage == "nonce":
            response["nonce"] = "f" * 32
        response["proof"] = evidence._signature(response, token) if damage != "proof" else "invalid"
        return response

    monkeypatch.setattr(evidence, "_fetch_attestation", fetch)
    return root, options


def test_signed_observation_still_cannot_prove_recall_or_activation(observation) -> None:
    root, _ = observation
    report = assess_active_memory_readiness(root)
    assert report["runtime_ready"] is True
    assert report["memory_recall_ready"] is None
    assert report["memory_continuity_ready"] is None
    assert report["activation_preflight_passed"] is False
    assert report["activation_authorized"] is False
    assert str(root.parent) not in json.dumps(report)


@pytest.mark.parametrize("damage,check,state", [
    ("pid", "endpoint", "conflict"), ("instance", "endpoint", "conflict"),
    ("root", "endpoint", "conflict"), ("proof", "endpoint", "conflict"),
    ("nonce", "endpoint", "conflict"), ("generation", "endpoint", "conflict"),
    ("heartbeat", "heartbeat", "unverified"),
])
def test_authenticated_claims_do_not_override_failed_binding(observation, damage: str, check: str, state: str) -> None:
    root, options = observation
    options["damage"] = damage
    report = assess_active_memory_readiness(root)
    assert report["runtime_ready"] is False
    assert report["checks"][check]["state"] == state
    assert report["activation_authorized"] is False


def test_wrong_process_command_blocks_readiness(observation, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = observation
    monkeypatch.setattr(evidence, "_observe_process_command", lambda *_: False)
    report = assess_active_memory_readiness(root)
    assert report["runtime_ready"] is False
    assert report["checks"]["process"]["state"] == "conflict"


def test_missing_authentication_blocks_readiness(observation, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = observation
    monkeypatch.setattr(daemon, "read_daemon_auth_token", lambda _: None)
    report = assess_active_memory_readiness(root)
    assert report["runtime_ready"] is False
    assert report["checks"]["endpoint"]["state"] == "unverified"
