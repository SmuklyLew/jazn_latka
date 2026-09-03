from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "package-distribution-cleanroom.yml"


def _handoff_step() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: Ambient run.py performs verified offline handoff")
    end = text.index("      - name: Reject package when dependency sidecar is absent", start)
    return text[start:end]


def test_prestart_status_is_inactive_while_doctor_reports_release_readiness() -> None:
    step = _handoff_step()
    assert 'status_rc=$?' in step
    assert 'test "$status_rc" -eq 1' in step
    assert 'doctor_rc=$?' in step
    assert 'test "$doctor_rc" -eq 0' in step
    assert 'assert p.get("ok") is False' in step
    assert 'assert d.get("active_state") == "inactive"' in step
    assert 'assert d.get("package_integrity_verified") is True' in step
    assert 'assert p.get("ok") is True' in step
    assert 'assert p.get("installation_ok") is True' in step
    assert 'assert p.get("activation_ready") is True' in step
    assert 'assert p.get("release_ready") is True' in step
    assert 'assert p.get("live_runtime_ready") is False' in step
    assert 'assert checks.get("verification_ok") is True' in step


def test_activation_checks_capture_exit_code_then_fail_closed() -> None:
    step = _handoff_step()
    start_index = step.index('python run.py start --json > "$RUNNER_TEMP/start.json"')
    activation = step[start_index:]
    before_start = step[:start_index]
    assert before_start.rstrip().endswith("set +e")
    assert 'start_rc=$?' in activation
    assert 'set -e' in activation
    assert 'test "$start_rc" -eq 0' in activation
    assert 'assert p.get("ok") is True' in activation
    assert 'assert p.get("runtime_core_ready") is True' in activation
    assert 'assert p.get("runtime_write_ready") is True' in activation
    assert 'assert st.get("voice_live_ready") is True' in activation
