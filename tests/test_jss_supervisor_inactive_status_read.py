"""Inactive supervisor is not a ready service or a failed status read."""
from tools.jazn_run_studio.status_summary import (
    inactive_supervisor_status_read, supervisor_summary,
)


def _inactive():
    return {
        "schema_version": "persistent_runtime_supervisor/v1",
        "ok": False, "supervisor_active": False,
        "supervisor_pid_alive": False, "supervisor_identity_state": "not_alive",
    }


def test_inactive_optional_supervisor_read_is_not_a_failed_operation():
    state = _inactive()
    assert inactive_supervisor_status_read(state, returncode=1, error="process_exit:1")
    assert supervisor_summary(state)["ready"] is False


def test_supervisor_json_and_transport_failures_stay_errors():
    state = _inactive()
    for sample, rc, reason in (
        ({**state, "schema_version": "unknown"}, 1, "process_exit:1"),
        ({**state, "supervisor_pid_alive": True}, 1, "process_exit:1"),
        ({**state, "supervisor_identity_state": "unknown"}, 1, "process_exit:1"),
        (state, 2, "process_exit:2"),
        (state, 1, "timeout"),
        ({}, 1, "process_exit:1"),
    ):
        assert not inactive_supervisor_status_read(sample, returncode=rc, error=reason)
