"""Read-only supervisor status is not proof of readiness or process ownership."""
from __future__ import annotations

import pytest

from tools.jazn_run_studio.status_summary import supervisor_summary


def _stopped() -> dict:
    return {
        "schema_version": "persistent_runtime_supervisor/v1",
        "supervisor_active": False,
        "supervisor_pid_alive": False,
        "supervisor_identity_state": "not_alive",
        "supervisor_identity_confirmed": False,
        "supervisor_heartbeat_fresh": False,
        "ok": True,
    }


def test_confirmed_inactive_supervisor_is_not_ready() -> None:
    result = supervisor_summary(_stopped())
    assert result["inactive_confirmed"] is True
    assert result["active"] is False
    assert result["ready"] is False
    assert result["accepted_visible_turn"] is False


@pytest.mark.parametrize("change", [
    {"schema_version": "unexpected"},
    {"supervisor_active": True},
    {"supervisor_pid_alive": True},
    {"supervisor_identity_state": "unknown"},
    {"supervisor_identity_state": None},
])
def test_incomplete_inactive_evidence_never_confirms_stop(change: dict) -> None:
    result = supervisor_summary({**_stopped(), **change})
    assert result["inactive_confirmed"] is False


def test_active_supervisor_requires_identity_heartbeat_and_command_success() -> None:
    active = {
        **_stopped(),
        "supervisor_active": True,
        "supervisor_pid_alive": True,
        "supervisor_identity_state": "alive",
        "supervisor_identity_confirmed": True,
        "supervisor_heartbeat_fresh": True,
    }
    assert supervisor_summary(active)["ready"] is True
    assert supervisor_summary(active, command_ok=False)["ready"] is False
    assert supervisor_summary({**active, "supervisor_identity_confirmed": None})["ready"] is False
