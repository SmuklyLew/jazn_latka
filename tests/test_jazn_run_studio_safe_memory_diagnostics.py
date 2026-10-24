"""MEMORY Qt must not render raw private paths in operator error diagnostics."""

import pytest

pytest.importorskip("PySide6")

from tests.test_jazn_run_studio_memory_view import window
from tools.jazn_run_studio.memory_view import evidence_rows, safe_reason


@pytest.mark.parametrize("raw", [
    "C:\\Users\\private\\memory.sqlite3: token=example",
    "/home/private/memory.sqlite3",
    "Traceback (most recent call last): ...",
    "a" * 1000,
    None,
])
def test_raw_errors_are_not_displayable_reason_codes(raw: object) -> None:
    assert safe_reason(raw) == "observation_failed"


def test_short_stable_reason_code_is_preserved() -> None:
    assert safe_reason("runtime_not_ready_for_pinned_provenance") == "runtime_not_ready_for_pinned_provenance"
    assert safe_reason("timeout") == "timeout"


def test_layout_blockers_do_not_echo_private_path() -> None:
    rows = evidence_rows("layout", {"readiness": {"blockers": ["/home/private/source.json"]}})
    blockers = [details for name, _state, details in rows if name == "Blokada inspekcji"]
    assert blockers == ["inspection_blocked"]


def test_comparison_issue_does_not_echo_private_path() -> None:
    rows = evidence_rows("comparison", {"comparisons": {
        "target": {"fingerprint_equal": None, "state": "blocked", "issue": "/private/db.sqlite3"}}})
    details = [note for name, _state, note in rows if name == "target: zgodność zawartości"]
    assert details == ["comparison_blocked"]


def test_qt_failed_job_uses_safe_status_instead_of_exception(window) -> None:
    panel = window.memory_panel
    panel.pending["layout"] = 1.0
    panel.receive_state("memory:p1:layout", {"started": 1.0, "state": "failed",
                                            "error": "C:\\Users\\private\\secrets.json"})
    assert panel.tables["layout"].item(0, 1).text() == "blocked"
    assert panel.tables["layout"].item(0, 2).text() == "failed"
    assert panel.pending == {}


def test_qt_failed_report_uses_safe_reason(window) -> None:
    panel = window.memory_panel
    panel.pending["layout"] = 1.0
    panel.receive("memory:p1:layout", {"started": 1.0, "report": {
        "ok": False, "issue": "/home/private/memory.sqlite3"}})
    assert panel.tables["layout"].item(0, 2).text() == "observation_failed"
