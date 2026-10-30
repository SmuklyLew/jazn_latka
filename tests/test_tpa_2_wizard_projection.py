"""P3 queue is derived from durable, source-current human observations."""
from tools.jazn_run_studio.tpa_catalog import LIVE_CASES, execution_map
from tools.jazn_run_studio.tpa_wizard import pending_cases, wizard_counts


def test_premerge_wizard_defers_live_and_never_invents_pass():
    rows = execution_map()
    pending = pending_cases(rows, {})
    assert len(rows) == 22
    assert len(pending) == 22 - len(LIVE_CASES)
    assert not (set(pending) & LIVE_CASES)
    assert wizard_counts(rows, {}) == (0, 22 - len(LIVE_CASES), len(LIVE_CASES))


def test_current_verified_acceptance_only_is_skipped():
    rows = execution_map()
    state = {
        "smoke-isolation": {"full": {"status": "PASS", "source_relation": "same"}},
        "config-persistence": {"full": {"status": "PASS", "source_relation": "stale"}},
        "ui-accessibility": {"full": {"status": "BLOCKED", "source_relation": "same"}},
    }
    pending = pending_cases(rows, state)
    assert "smoke-isolation" not in pending
    assert "config-persistence" in pending
    assert "ui-accessibility" in pending
    assert wizard_counts(rows, state)[0] == 1


def test_explicit_live_option_only_changes_queue_not_evidence():
    rows = execution_map()
    assert set(LIVE_CASES).issubset(set(pending_cases(rows, {}, include_live=True)))
    assert wizard_counts(rows, {}, include_live=True) == (0, 22, 0)
