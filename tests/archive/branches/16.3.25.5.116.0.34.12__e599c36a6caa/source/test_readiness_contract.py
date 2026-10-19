from __future__ import annotations

from latka_jazn.core.readiness import (
    evaluate_runtime_readiness,
    evaluate_system_readiness_profile,
)


def _integrity_checks(*, verification_ok: bool = True) -> dict[str, bool]:
    return {
        "present": True,
        "parse_ok": True,
        "version_matches": True,
        "primary_present": True,
        "legacy_alias_absent": True,
        "canonical_source_name": True,
        "verification_ok": verification_ok,
    }


def _ready_dependencies() -> dict[str, object]:
    return {
        "required_ready": True,
        "selected_source": "deterministic_test_fixture",
        "missing_or_incompatible_distributions": [],
    }


def test_readiness_separates_activation_prerequisites_from_live_runtime() -> None:
    readiness = evaluate_runtime_readiness(
        required_checks={"root": True, "run": True},
        package_integrity_checks=_integrity_checks(),
        provenance={
            "status": "clean_checkout_verified",
            "version_matches_runtime": True,
        },
        daemon={
            "active_state": "inactive",
            "pid_alive": False,
            "endpoint_reachable": False,
            "heartbeat_fresh": False,
        },
        transactional_memory={"exists": False, "ready": False},
        dependency_evidence=_ready_dependencies(),
    )

    assert readiness.activation_prerequisites_ready is True
    assert readiness.activation_ready is True
    assert readiness.release_ready is True
    assert readiness.live_runtime_ready is False
    assert readiness.summary() == {
        "installation": "ready",
        "activation_prerequisites": "ready",
        "dependencies": "ready",
        "release": "ready",
        "runtime": "inactive",
        "transactional_memory": "missing",
    }


def test_readiness_requires_live_daemon_evidence_for_active_trusted() -> None:
    readiness = evaluate_runtime_readiness(
        required_checks={"root": True},
        package_integrity_checks=_integrity_checks(),
        provenance={
            "status": "verified_export_without_git_history",
            "version_matches_runtime": True,
        },
        daemon={
            "runtime_active_state": "active_trusted",
            "pid_alive": True,
            "endpoint_reachable": True,
            "heartbeat_fresh": True,
        },
        transactional_memory={"exists": True, "ready": True},
        dependency_evidence=_ready_dependencies(),
    )

    assert readiness.live_runtime_ready is True
    assert readiness.summary()["runtime"] == "active_trusted"
    assert readiness.summary()["transactional_memory"] == "ready"


def test_integrity_failure_blocks_activation_and_release() -> None:
    readiness = evaluate_runtime_readiness(
        required_checks={"root": True},
        package_integrity_checks=_integrity_checks(verification_ok=False),
        provenance={
            "status": "clean_checkout_verified",
            "version_matches_runtime": True,
        },
        daemon={},
        transactional_memory={},
        dependency_evidence=_ready_dependencies(),
    )

    assert readiness.installation_ok is True
    assert readiness.activation_prerequisites_ready is False
    assert readiness.release_metadata_current is False
    assert readiness.release_ready is False


def test_system_fully_ready_is_an_explicit_capability_profile() -> None:
    profile = evaluate_system_readiness_profile(
        profile="interactive_live_voice",
        capabilities={
            "runtime_core": {
                "classification": "required",
                "ready": True,
                "status": "ready",
            },
            "live_voice": {
                "classification": "required",
                "ready": True,
                "status": "ready",
            },
            "dictionary_lookup": {
                "classification": "optional",
                "ready": False,
                "status": "offline",
            },
            "memory_search": {
                "classification": "degraded_allowed",
                "ready": False,
                "status": "not_configured",
            },
            "rest_dream": {
                "classification": "not_applicable",
                "ready": None,
                "status": "not_applicable",
            },
            "cognitive_integration": {
                "classification": "unknown",
                "ready": None,
                "status": "not_probed",
            },
        },
    )

    assert profile["system_fully_ready"] is False
    assert profile["blocking_capabilities"] == ["cognitive_integration"]
    assert profile["optional_unavailable"] == ["dictionary_lookup"]
    assert profile["degraded_capabilities"] == ["memory_search"]
    assert profile["unknown_capabilities"] == ["cognitive_integration"]


def test_optional_degraded_and_not_applicable_capabilities_do_not_block_profile() -> None:
    profile = evaluate_system_readiness_profile(
        profile="minimal_explicit",
        capabilities={
            "runtime_core": {
                "classification": "required",
                "ready": True,
                "status": "ready",
            },
            "optional": {
                "classification": "optional",
                "ready": False,
                "status": "unavailable",
            },
            "degraded": {
                "classification": "degraded_allowed",
                "ready": False,
                "status": "degraded",
            },
            "irrelevant": {
                "classification": "not_applicable",
                "ready": None,
                "status": "not_applicable",
            },
        },
    )

    assert profile["system_fully_ready"] is True
    assert profile["blocking_capabilities"] == []
