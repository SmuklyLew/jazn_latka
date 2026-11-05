"""Shutdown requires positive inactive supervisor evidence, not absence of a PID."""
from tools.jazn_run_studio.status_summary import supervisor_summary


def test_confirmed_inactive_requires_full_supervisor_status() -> None:
    assert supervisor_summary({}, command_ok=False)["inactive_confirmed"] is False
    data = {
        "schema_version": "persistent_runtime_supervisor/v1",
        "supervisor_active": False,
        "supervisor_pid_alive": False,
        "supervisor_identity_state": "not_alive",
    }
    assert supervisor_summary(data, command_ok=False)["inactive_confirmed"] is True
    assert supervisor_summary({**data, "supervisor_pid_alive": True})["inactive_confirmed"] is False
    assert supervisor_summary({**data, "supervisor_active": True})["inactive_confirmed"] is False
