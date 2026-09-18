from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from latka_jazn.cli import build_parser
from latka_jazn.bootstrap.chatgpt_host_preflight_parse import executor_observation_from_mapping
from latka_jazn.core.chatgpt_host_executor_aggregate import (
    aggregate_host_executor_observations,
)
from latka_jazn.core.chatgpt_host_executor_enums import (
    HostExecutionRoute,
    HostRecoveryAction,
)
from latka_jazn.core.chatgpt_host_executor_observation import HostExecutorObservation
from latka_jazn.core.host_operations import (
    HOST_OPERATION_ID_RE,
    generate_operation_id,
)


ROOT = Path(__file__).resolve().parents[1]


def _success(*, generation: int) -> HostExecutorObservation:
    return HostExecutorObservation(
        process_created=True,
        command_completed=True,
        returncode=0,
        filesystem_probe_succeeded=True,
        surface="primary",
        observation_generation=generation,
    )


def _pre_spawn_failure(*, generation: int) -> HostExecutorObservation:
    return HostExecutorObservation(
        process_created=False,
        error_class="TransportTimeoutError",
        surface="primary",
        observation_generation=generation,
    )


def test_canonical_operation_id_is_utc_safe_and_never_contains_plus_offset() -> None:
    local = timezone(timedelta(hours=2))
    operation_id = generate_operation_id(
        "daemon-start",
        now=datetime(2026, 9, 18, 6, 41, 13, 123456, tzinfo=local),
        entropy="abcdef123456",
    )

    assert operation_id == "daemon-start-20260918T044113123456Z-abcdef123456"
    assert "+" not in operation_id
    assert HOST_OPERATION_ID_RE.fullmatch(operation_id)


def test_canonical_operation_id_rejects_naive_timestamp_and_bad_entropy() -> None:
    with pytest.raises(ValueError, match="timestamp_must_be_timezone_aware"):
        generate_operation_id(
            "daemon-start",
            now=datetime(2026, 9, 18, 6, 41, 13),
            entropy="abcdef123456",
        )

    with pytest.raises(ValueError, match="entropy_invalid"):
        generate_operation_id(
            "daemon-start",
            now=datetime(2026, 9, 18, 4, 41, 13, tzinfo=timezone.utc),
            entropy="not-safe",
        )


def test_cli_exposes_preallocation_without_side_effecting_submit() -> None:
    ns = build_parser().parse_args(["host-op-id", "--kind", "daemon-start", "--json"])
    assert ns.command == "host-op-id"
    assert ns.kind == "daemon-start"
    assert ns.as_json is True


def test_newer_executor_generation_supersedes_stale_pre_spawn_failure() -> None:
    snapshot = aggregate_host_executor_observations(
        (
            _pre_spawn_failure(generation=1),
            _success(generation=2),
        )
    )

    assert snapshot.execution_route is HostExecutionRoute.LOCAL_EXECUTOR
    assert snapshot.next_action is HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
    assert len(snapshot.surfaces) == 1
    assert snapshot.surfaces[0]["observation_generation"] == 2
    assert snapshot.surfaces[0]["executor_state"] == "available"


def test_newer_failure_does_not_inherit_old_success_from_previous_generation() -> None:
    snapshot = aggregate_host_executor_observations(
        (
            _success(generation=1),
            _pre_spawn_failure(generation=2),
        )
    )

    assert snapshot.execution_route is not HostExecutionRoute.LOCAL_EXECUTOR
    assert snapshot.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert len(snapshot.surfaces) == 1
    assert snapshot.surfaces[0]["observation_generation"] == 2
    assert snapshot.surfaces[0]["executor_state"] == "host_executor_unavailable"


def test_preflight_parser_preserves_observation_generation() -> None:
    parsed = executor_observation_from_mapping(
        {
            "process_created": False,
            "error_class": "TransportTimeoutError",
            "surface": "primary",
            "observation_generation": 7,
        }
    )
    defaulted = executor_observation_from_mapping(
        {
            "process_created": False,
            "error_class": "TransportTimeoutError",
            "surface": "primary",
        }
    )

    assert parsed.observation_generation == 7
    assert defaulted.observation_generation == 0


def test_negative_observation_generation_is_rejected() -> None:
    with pytest.raises(ValueError, match="observation_generation_must_be_non_negative"):
        _pre_spawn_failure(generation=-1)


def test_runbook_and_thin_loader_make_executor_failure_generation_scoped() -> None:
    runbook = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")
    loader = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")

    assert "bieżącej generacji powierzchni wykonawczej" in runbook
    assert "stale evidence" in runbook
    assert "host-op-id --kind daemon-start" in runbook
    assert "host-op-id --kind runtime-bootstrap" in runbook
    assert "bieżącej generacji powierzchni wykonawczej" in loader
    assert "nie cache'uj go jako trwałego stanu rozmowy" in loader
    assert len(loader) <= 5000
    assert "run.py" not in loader
