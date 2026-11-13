"""V105 Windows TPA uses the original 22 gates and preserves historical evidence."""
from __future__ import annotations

from copy import deepcopy

from tools.jazn_run_studio.local_acceptance import CATALOG, STUDIO_CATALOG
from tools.jazn_run_studio.tpa_catalog import WINDOWS_V105_CHECKS, execution_map
from tools.jazn_run_studio.tpa_triage import NIEAKTUALNE, NOWE, triage_cases


def test_v105_windows_instructions_cover_each_existing_gate_without_new_case() -> None:
    cases = execution_map()
    assert len(CATALOG) == 10
    assert len(STUDIO_CATALOG) == 12
    assert len(cases) == 22
    assert set(WINDOWS_V105_CHECKS) == {case["id"] for case in cases}
    assert len({case["id"] for case in cases}) == 22
    for case in cases:
        assert case["full_gate"] == "NOT_RUN"
        assert case["coverage"] == "regression_subset"
        assert len([line for line in case["guide"] if line.startswith("Windows V105 / TPA: ")]) == 1
        assert "Windows" in WINDOWS_V105_CHECKS[case["id"]]
        assert case["files"]


def test_previous_version_pass_is_displayed_as_stale_without_rewriting_history() -> None:
    original = [{
        "started_utc": "2026-11-06T00:00:00Z",
        "source": {"version": "V74", "git_sha": "sha-v74", "version_sha256": "file-v74",
                   "git_dirty": False},
        "results": [{"case_id": "ollama-two-turns", "status": "PASS", "full_gate": "PASS"}],
    }]
    history = deepcopy(original)
    current = {"version": "V105", "git_sha": "sha-v105",
               "version_sha256": "file-v105", "git_dirty": False}
    cases = [{"id": case["id"]} for case in execution_map()]
    triage = triage_cases(cases, history, current)
    assert triage["ollama-two-turns"]["state"] == NIEAKTUALNE
    assert triage["studio-dependencies"]["state"] == NOWE
    assert history == original


def test_windows_preflight_steps_are_guidance_not_pass_receipts() -> None:
    by_id = {case["id"]: case for case in execution_map()}
    for name in ("studio-python-runtime", "studio-dependencies", "offline-exe",
                 "ollama-two-turns", "chat-reconnect", "chat-resume", "daemon-restart"):
        case = by_id[name]
        assert case["full_gate"] == "NOT_RUN"
        assert case["mode"] != "automatic" or case["coverage"] == "regression_subset"
        assert "Windows V105 / TPA:" in "\n".join(case["guide"])
