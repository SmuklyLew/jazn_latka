from __future__ import annotations

from latka_jazn.core.readiness import evaluate_runtime_readiness


def _package_integrity_ok() -> dict[str, bool]:
    return {
        "present": True,
        "parse_ok": True,
        "version_matches": True,
        "primary_present": True,
        "legacy_alias_absent": True,
        "canonical_source_name": True,
        "verification_ok": True,
    }


def test_filesystem_snapshot_can_activate_without_becoming_release_ready() -> None:
    readiness = evaluate_runtime_readiness(
        required_checks={"runtime_files": True, "startup_contract": True},
        package_integrity_checks=_package_integrity_ok(),
        provenance={
            "status": "verified_export_without_git_history",
            "version_matches_runtime": True,
            "generation_mode": "filesystem_snapshot",
        },
        daemon={
            "active_state": "active_trusted",
            "pid_alive": True,
            "endpoint_reachable": True,
            "heartbeat_fresh": True,
        },
        transactional_memory={"ready": False, "exists": False},
    )

    assert readiness.installation_ok is True
    assert readiness.activation_prerequisites_ready is True
    assert readiness.live_runtime_ready is True
    assert readiness.release_metadata_current is False
    assert readiness.release_ready is False


def test_release_export_without_git_history_keeps_release_readiness_compatibility() -> None:
    readiness = evaluate_runtime_readiness(
        required_checks={"runtime_files": True},
        package_integrity_checks=_package_integrity_ok(),
        provenance={
            "status": "verified_export_without_git_history",
            "version_matches_runtime": True,
            "generation_mode": "release",
        },
        daemon={},
        transactional_memory={"ready": False},
    )

    assert readiness.activation_prerequisites_ready is True
    assert readiness.release_metadata_current is True
    assert readiness.release_ready is True


def test_clean_git_checkout_remains_release_ready() -> None:
    readiness = evaluate_runtime_readiness(
        required_checks={"runtime_files": True},
        package_integrity_checks=_package_integrity_ok(),
        provenance={
            "status": "clean_checkout_verified",
            "version_matches_runtime": True,
            "generation_mode": "release_metadata",
        },
        daemon={},
        transactional_memory={"ready": False},
    )

    assert readiness.release_metadata_current is True
    assert readiness.release_ready is True
