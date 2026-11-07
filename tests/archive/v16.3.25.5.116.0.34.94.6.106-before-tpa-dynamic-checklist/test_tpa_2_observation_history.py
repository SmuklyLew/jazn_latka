"""A later operator failure cannot erase an earlier verified full acceptance."""
from tools.jazn_run_studio.tpa_current_state import current_state
from tools.jazn_run_studio.tpa_guidance import record_observation
from tests.test_tpa_2_current_state import store, completed


def test_last_confirmed_full_success_survives_a_later_observation(store):
    report = completed(store)
    row = report["results"][0]
    first = record_observation(store, report, "config-persistence", [0, 1, 2, 3], "Synthetic accepted review", [row["junit"]], "PASS")
    record_observation(store, report, "config-persistence", [0], "New problem observed", [row["junit"]], "BLOCKED")
    state = current_state(store, report["source"])["config-persistence"]
    assert state["full"]["status"] == "BLOCKED"
    assert state["last_full_success"]["status"] == "PASS"
    assert state["last_full_success"]["time"] == first["observed_utc"]
