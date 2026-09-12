from __future__ import annotations

import pytest

from latka_jazn.core.chatgpt_host_executor_contract import (
    HostEnvironmentState,
    HostExecutorObservation,
    HostFilesystemState,
    HostRecoveryAction,
    aggregate_host_executor_observations,
)
from latka_jazn.core.chatgpt_host_recovery import plan_host_capability_recovery


def test_python_bridge_failure_plus_terminal_success_is_degraded_not_unavailable() -> None:
    snapshot = aggregate_host_executor_observations(
        [
            HostExecutorObservation(
                process_created=False,
                error_class="ClientError",
                alternative_surface_available=True,
                alternative_probe_count=0,
                surface="python_tool",
            ),
            HostExecutorObservation(
                process_created=True,
                command_completed=True,
                returncode=0,
                filesystem_probe_succeeded=True,
                surface="terminal",
            ),
        ]
    )

    assert snapshot.environment_state is HostEnvironmentState.DEGRADED
    assert snapshot.filesystem_state is HostFilesystemState.OBSERVED
    assert snapshot.next_action is HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
    assert snapshot.canonical_resume_entrypoint == "run.py"
    assert snapshot.retry_allowed is False
    assert snapshot.reason_code == "usable_executor_surface_with_other_surface_failure"
    assert [item["surface"] for item in snapshot.surfaces] == ["python_tool", "terminal"]


def test_single_failed_surface_with_unused_alternative_keeps_global_state_unknown() -> None:
    snapshot = aggregate_host_executor_observations(
        [
            HostExecutorObservation(
                process_created=False,
                error_class="ClientError",
                alternative_surface_available=True,
                alternative_probe_count=0,
                surface="python_tool",
            )
        ]
    )

    assert snapshot.environment_state is HostEnvironmentState.UNKNOWN
    assert snapshot.next_action is HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
    assert snapshot.retry_allowed is True
    assert snapshot.retry_budget_remaining == 1
    assert snapshot.canonical_resume_entrypoint is None


def test_exhausted_failed_surfaces_are_globally_unavailable() -> None:
    snapshot = aggregate_host_executor_observations(
        [
            HostExecutorObservation(
                process_created=False,
                error_class="ClientError",
                alternative_surface_available=True,
                alternative_probe_count=1,
                surface="python_tool",
            ),
            HostExecutorObservation(
                process_created=False,
                error_class="InvalidArgumentError",
                alternative_surface_available=False,
                surface="terminal",
            ),
        ]
    )

    assert snapshot.environment_state is HostEnvironmentState.UNAVAILABLE
    assert snapshot.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert snapshot.retry_allowed is False
    assert snapshot.filesystem_state is HostFilesystemState.UNKNOWN


def test_all_observed_surfaces_available_produces_available_environment() -> None:
    snapshot = aggregate_host_executor_observations(
        [
            HostExecutorObservation(
                process_created=True,
                command_completed=True,
                returncode=0,
                surface="python_tool",
            ),
            HostExecutorObservation(
                process_created=True,
                command_completed=True,
                returncode=0,
                filesystem_probe_succeeded=True,
                surface="terminal",
            ),
        ]
    )

    assert snapshot.environment_state is HostEnvironmentState.AVAILABLE
    assert snapshot.next_action is HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
    assert snapshot.filesystem_state is HostFilesystemState.OBSERVED


def test_usable_surface_with_failed_local_command_requires_diagnosis() -> None:
    snapshot = aggregate_host_executor_observations(
        [
            HostExecutorObservation(
                process_created=False,
                error_class="ClientError",
                alternative_surface_available=False,
                surface="python_tool",
            ),
            HostExecutorObservation(
                process_created=True,
                command_completed=True,
                returncode=2,
                error_class="CalledProcessError",
                surface="terminal",
            ),
        ]
    )

    assert snapshot.environment_state is HostEnvironmentState.DEGRADED
    assert snapshot.next_action is HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND
    assert snapshot.canonical_resume_entrypoint is None


def test_duplicate_surface_observation_is_rejected() -> None:
    observation = HostExecutorObservation(
        process_created=True,
        command_completed=True,
        returncode=0,
        surface="terminal",
    )
    with pytest.raises(ValueError, match="duplicate_executor_surface:terminal"):
        aggregate_host_executor_observations([observation, observation])


def test_surface_identifier_is_normalized_and_validated() -> None:
    observation = HostExecutorObservation(
        process_created=True,
        command_completed=True,
        returncode=0,
        surface="  PYTHON_TOOL  ",
    )
    assert observation.surface == "python_tool"

    with pytest.raises(ValueError, match="invalid_executor_surface"):
        HostExecutorObservation(
            process_created=False,
            error_class="ClientError",
            surface="python tool",
        )


def test_recovery_module_aggregates_same_cross_surface_snapshot() -> None:
    snapshot = plan_host_capability_recovery(
        [
            HostExecutorObservation(
                process_created=False,
                error_class="ClientError",
                alternative_surface_available=True,
                surface="python_tool",
            ),
            HostExecutorObservation(
                process_created=True,
                command_completed=True,
                returncode=0,
                filesystem_probe_succeeded=True,
                surface="terminal",
            ),
        ]
    )

    payload = snapshot.to_dict()
    assert payload["environment_state"] == "degraded"
    assert payload["filesystem_state"] == "observed"
    assert payload["next_action"] == "resume_canonical_discovery"
    assert payload["canonical_resume_entrypoint"] == "run.py"
