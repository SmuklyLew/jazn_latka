from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "package-distribution-cleanroom.yml"


def _handoff_step() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: Dependency-empty run.py performs verified offline handoff")
    end = text.index("      - name: Preserve cleanroom startup evidence on failure", start)
    return text[start:end]


def test_dependency_empty_preflight_and_poststart_doctor_reports_release_readiness() -> None:
    step = _handoff_step()
    assert '"$BARE_PYTHON" run.py host-preflight --json' in step
    assert 'preflight_rc=$?' in step
    assert 'test "$preflight_rc" -eq 0' in step
    assert step.index('"$BARE_PYTHON" run.py start --json') < step.index('"$BARE_PYTHON" "$RUNNER_TEMP/verified_managed_cli.py" doctor --json')
    assert 'doctor_rc=$?' in step
    assert 'test "$doctor_rc" -eq 0' in step
    assert 'assert p.get("gate_passed") is True' in step
    assert 'assert p.get("bootstrap_allowed") is True' in step
    assert step.index('"$BARE_PYTHON" run.py host-preflight --json') < step.index('"$BARE_PYTHON" run.py start --json')
    assert 'assert p.get("ok") is True' in step
    assert 'assert p.get("installation_ok") is True' in step
    assert 'assert p.get("activation_ready") is True' in step
    assert 'assert p.get("release_ready") is True' in step
    assert 'assert p.get("live_runtime_ready") is True' in step
    assert 'assert checks.get("verification_ok") is True' in step


def test_activation_checks_capture_exit_code_then_fail_closed() -> None:
    step = _handoff_step()
    start_index = step.index('"$BARE_PYTHON" run.py start --json > "$RUNNER_TEMP/start.json"')
    activation = step[start_index:]
    before_start = step[:start_index]
    assert before_start.rstrip().endswith("set +e")
    assert 'start_rc=$?' in activation
    assert 'set -e' in activation
    assert 'test "$start_rc" -eq 0' in activation
    assert 'assert p.get("ok") is True' in activation
    assert 'assert p.get("daemon_instance_id")' in activation
    assert 'status_after_rc=$?' in activation
    assert 'test "$status_after_rc" -eq 0' in activation
    assert 'assert p.get("runtime_core_ready") is True' in activation
    assert 'assert p.get("runtime_write_ready") is True' in activation
    assert 'd.get("active_state") == "active_trusted"' in activation
    assert 'd.get("endpoint_reachable") is True' in activation
    assert 'd.get("heartbeat_fresh") is True' in activation
    assert 'assert st.get("voice_live_ready") is True' in activation
    assert activation.index('test "$start_rc" -eq 0') < activation.index('status_after_rc=$?')


def test_cleanroom_uses_isolated_bootstrap_python_without_site_packages() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "python -m venv --without-pip" in text
    assert 'BARE_PYTHON: ${{ steps.bare_python.outputs.path }}' in text
    assert 'for name in ("packaging", "tzdata", "pypdf", "py7zr", "pyzipper"):' in text
    assert '"$BARE_PYTHON" "$RUNNER_TEMP/verified_managed_cli.py" doctor --json' in text
    assert '"$BARE_PYTHON" run.py start --json' in text
