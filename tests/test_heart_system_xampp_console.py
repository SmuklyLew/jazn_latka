"""Read-only supervisor projection refuses PID-only readiness."""
from tools.jazn_run_studio.core import ACTION_BY_KEY
from tools.jazn_run_studio.status_summary import supervisor_summary


def test_supervisor_uses_only_the_canonical_readonly_command():
    action = ACTION_BY_KEY["supervisor"]
    assert action.args == ("supervisor-status", "--json")
    assert not action.mutates


def test_supervisor_needs_identity_heartbeat_and_successful_status():
    payload = {"ok": True, "supervisor_active": True, "supervisor_pid": 4321,
               "supervisor_identity_confirmed": True, "supervisor_heartbeat_fresh": True,
               "secret": "private", "root": "/private/owner"}
    clean = supervisor_summary(payload)
    assert clean["ready"] is True and clean["pid"] == 4321
    assert "root" not in clean and "secret" not in clean
    assert clean["accepted_visible_turn"] is False
    assert supervisor_summary(payload, command_ok=False)["ready"] is False
    for field in ("ok", "supervisor_active", "supervisor_identity_confirmed", "supervisor_heartbeat_fresh"):
        assert supervisor_summary({**payload, field: False})["ready"] is False
    assert supervisor_summary({"supervisor_pid": "4321"})["pid"] is None
