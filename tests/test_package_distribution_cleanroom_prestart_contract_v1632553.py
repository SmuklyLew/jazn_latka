from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "package-distribution-cleanroom.yml"


def _handoff_step() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: Ambient run.py performs verified offline handoff")
    end = text.index("      - name: Reject package when dependency sidecar is absent", start)
    return text[start:end]


def test_prestart_status_and_doctor_accept_only_expected_inactive_exit_code() -> None:
    step = _handoff_step()
    assert 'status_rc=$?' in step
    assert 'test "$status_rc" -eq 1' in step
    assert 'doctor_rc=$?' in step
    assert 'test "$doctor_rc" -eq 1' in step
    assert 'assert p.get("ok") is False' in step
    assert 'assert d.get("active_state") == "inactive"' in step
    assert 'assert d.get("package_integrity_verified") is True' in step
    assert 'assert p.get("live_runtime_ready") is False' in step
    assert 'assert checks.get("verification_ok") is True' in step


def test_activation_checks_remain_fail_fast_after_prestart_diagnostics() -> None:
    step = _handoff_step()
    start_index = step.index('python run.py start --json > "$RUNNER_TEMP/start.json"')
    last_set_e = step.rfind("          set -e", 0, start_index)
    last_set_plus_e = step.rfind("          set +e", 0, start_index)
    assert last_set_e > last_set_plus_e
    assert 'assert p.get("ok") is True' in step[start_index:]
    assert 'assert p.get("runtime_core_ready") is True' in step[start_index:]
    assert 'assert p.get("runtime_write_ready") is True' in step[start_index:]
    assert 'assert st.get("voice_live_ready") is True' in step[start_index:]
