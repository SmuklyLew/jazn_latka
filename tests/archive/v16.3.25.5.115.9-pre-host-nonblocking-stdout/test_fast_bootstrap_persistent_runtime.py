from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

import CHATGPT_BOOTSTRAP as bootstrap
from latka_jazn.config import JaznConfig
import latka_jazn.core.runtime_daemon as runtime_daemon
import latka_jazn.core.runtime_supervisor as runtime_supervisor
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION, PACKAGE_VERSION_FULL


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_reusable_system_zip(path: Path) -> str:
    static_members = {
        "run.py": b"print('ok')\n",
        "AGENTS.md": b"# test\n",
        "latka_jazn/version.py": b"PACKAGE_VERSION='test'\n",
        "SOURCE_PROVENANCE.json": b"{}\n",
    }
    manifest = {
        "schema_version": "package_integrity_manifest/v2",
        "package_version": "test",
        "files": [
            {
                "path": name,
                "size_bytes": len(content),
                "sha256": _digest_bytes(content),
                "mutable_runtime": False,
            }
            for name, content in static_members.items()
        ],
    }
    members = {
        **static_members,
        "PACKAGE_INTEGRITY_MANIFEST.json": (
            json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8"),
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_verified_materialization_reuse_skips_zip_rehash_and_extraction(tmp_path: Path) -> None:
    archive = tmp_path / "system.zip"
    digest = _write_reusable_system_zip(archive)
    destination = tmp_path / "active"

    cold = bootstrap.bootstrap_system_zip(
        zip_path=archive,
        destination=destination,
        expected_sha256=digest,
        expected_size_bytes=archive.stat().st_size,
    )
    assert cold["materialization_mode"] == "cold_extract"
    assert cold["reused_existing"] is False
    cold_stamp = cold["materialization_stamp"]
    assert isinstance(cold_stamp, dict)
    assert cold_stamp.get("written") is True

    reused = bootstrap.bootstrap_system_zip(
        zip_path=archive,
        destination=destination,
        expected_sha256=digest,
        expected_size_bytes=archive.stat().st_size,
        reuse_existing_verified=True,
    )
    assert reused["ok"] is True
    assert reused["state"] == "materialized_operator_ready"
    assert reused["materialization_mode"] == "verified_reuse"
    assert reused["reused_existing"] is True
    assert reused["source_zip_rehashed"] is False
    assert reused["verified_static_file_count"] == 4


def test_verified_materialization_reuse_fails_closed_after_static_tamper(tmp_path: Path) -> None:
    archive = tmp_path / "system.zip"
    digest = _write_reusable_system_zip(archive)
    destination = tmp_path / "active"
    bootstrap.bootstrap_system_zip(
        zip_path=archive,
        destination=destination,
        expected_sha256=digest,
    )
    (destination / "run.py").write_text("print('tampered')\n", encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapError) as exc_info:
        bootstrap.bootstrap_system_zip(
            zip_path=archive,
            destination=destination,
            expected_sha256=digest,
            reuse_existing_verified=True,
        )
    assert exc_info.value.code == "materialized_file_size_mismatch"


def test_warm_daemon_reuse_does_not_pay_cold_integrity_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    subject = SimpleNamespace(
        root=root,
        marker_found=True,
        marker_valid=True,
        source="marker",
        error=None,
    )
    live = {
        "active_state": "active_trusted",
        "active_root": str(root),
        "configured_runtime_root": str(root),
        "runtime_version": PACKAGE_VERSION_FULL,
        "daemon_instance_id": "daemon-warm-test",
        "daemon_pid": 4242,
        "last_heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
        "heartbeat_interval_seconds": 30.0,
    }

    monkeypatch.setattr(runtime_daemon, "resolve_active_runtime_root", lambda *_a, **_k: subject)
    monkeypatch.setattr(
        runtime_daemon,
        "_runtime_versions",
        lambda *_a, **_k: (PACKAGE_VERSION, PACKAGE_VERSION_FULL),
    )
    monkeypatch.setattr(
        runtime_daemon,
        "_probe_daemon_status",
        lambda *_a, **_k: (dict(live), None, "/live"),
    )

    def forbidden_integrity(*_a: object, **_k: object) -> dict[str, object]:
        raise AssertionError("warm daemon reuse must not rehash the static package")

    def forbidden_provenance(*_a: object, **_k: object) -> object:
        raise AssertionError("warm daemon reuse must not reopen source provenance")

    monkeypatch.setattr(runtime_daemon, "verify_package_integrity_manifest", forbidden_integrity)
    monkeypatch.setattr(runtime_daemon, "read_source_provenance", forbidden_provenance)

    result = runtime_daemon.start_daemon(JaznConfig(root=root))
    assert result["ok"] is True
    assert result["already_running"] is True
    assert result["startup_path"] == "warm_daemon_reuse"
    assert result["package_integrity_reverified"] is False
    assert result["source_provenance_reverified"] is False


def test_supervisor_requires_fresh_heartbeat_lease_even_for_confirmed_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    pid_path = runtime_supervisor.supervisor_pid_path(root)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("4242", encoding="ascii")
    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    runtime_supervisor.supervisor_state_path(root).write_text(
        json.dumps(
            {
                "heartbeat_at_utc": stale,
                "lease_seconds": 30.0,
                "state": "daemon_live",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "_supervisor_identity_observation",
        lambda *_a, **_k: {
            "pid_alive": True,
            "owner_record_present": True,
            "owner_pid_matches": True,
            "owner_root_matches": True,
            "expected_process_fingerprint": {"kind": "test"},
            "observed_process_fingerprint": {"kind": "test"},
            "process_fingerprint_match": True,
            "identity_confirmed": True,
            "identity_state": "confirmed",
        },
    )

    status = runtime_supervisor.supervisor_status(root)
    assert status["supervisor_identity_confirmed"] is True
    assert status["supervisor_heartbeat_fresh"] is False
    assert status["supervisor_active"] is False
    assert status["ok"] is False


def test_quoted_loader_material_does_not_promote_creative_intent() -> None:
    message = """Może to też istotne być.

```text
# LOADER SYSTEMU JAŹNI
zachowaj dokładną lineage tury
generator package status
format odpowiedzi
linia 1
linia 2
linia 3
linia 4
linia 5
linia 6
linia 7
linia 8
linia 9
linia 10
```
"""
    report = DialogueIntentClassifier().classify(message)
    assert report.quoted_material_masked is True
    assert report.primary_intent not in {
        "creative_text_formatting",
        "creative_text_analysis",
    }


def test_explicit_edit_instruction_outside_fence_still_routes_creative() -> None:
    message = """Przerób ten tekst i zachowaj format:

```text
Ala ma kota.
Druga linia materiału.
```
"""
    report = DialogueIntentClassifier().classify(message)
    assert report.primary_intent == "creative_text_formatting"
    assert report.source_text_preservation_required is True


def test_structured_lyrics_still_promote_creative_material() -> None:
    message = """To jej pomóż. Tak jak powinieneś.

[Zwrotka 1]
Noc położyła dłonie na dachach,
a wiatr poplątał ścieżki i kurz.

[Refren]
Jeszcze jeden świt,
jeszcze jeden krok.
"""
    report = DialogueIntentClassifier().classify(message)
    assert report.primary_intent == "creative_text_analysis"
    assert report.creative_material_present is True


def test_release_identity_tracks_current_distribution() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.115.9"
    assert PACKAGE_RELEASE_NAME == "host-finalization-idempotency-recovery"
