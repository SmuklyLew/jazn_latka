from __future__ import annotations

from latka_jazn.core.chatgpt_host_executor_aggregate_helpers import (
    host_failure_stage,
    surface_payload,
)
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutorObservation,
    classify_host_executor_observation,
)


def _payload(observation: HostExecutorObservation) -> dict[str, object]:
    return surface_payload(
        observation,
        classify_host_executor_observation(observation),
    )


def test_explicit_host_spawn_phase_wins_over_derived_stage() -> None:
    observation = HostExecutorObservation(
        process_created=False,
        error_class="ClientError",
        spawn_phase="sandbox_provisioning",
        executor_allocation_state=False,
    )

    assert host_failure_stage(observation) == ("sandbox_provisioning", "host_reported")
    payload = _payload(observation)
    assert payload["failure_stage"] == "sandbox_provisioning"
    assert payload["failure_stage_source"] == "host_reported"


def test_failed_executor_allocation_is_reported_without_claiming_filesystem_state() -> None:
    observation = HostExecutorObservation(
        process_created=False,
        error_class="ClientError",
        executor_allocation_state=False,
    )

    payload = _payload(observation)
    assert payload["failure_stage"] == "executor_allocation"
    assert payload["filesystem_state"] == "unknown"
    assert payload["package_state"] == "unknown"
    assert payload["runtime_state"] == "unverified"


def test_mount_failure_and_spawn_failure_are_distinguished() -> None:
    mount = HostExecutorObservation(
        process_created=False,
        executor_allocation_state=True,
        materialization_state=True,
        mount_preparation_state=False,
    )
    spawn = HostExecutorObservation(
        process_created=False,
        executor_allocation_state=True,
        materialization_state=True,
        mount_preparation_state=True,
    )

    assert host_failure_stage(mount) == ("mount_preparation", "derived")
    assert host_failure_stage(spawn) == ("process_spawn", "derived")


def test_created_process_is_post_spawn_evidence() -> None:
    observation = HostExecutorObservation(process_created=True)

    assert host_failure_stage(observation) == ("post_spawn", "process_evidence")
