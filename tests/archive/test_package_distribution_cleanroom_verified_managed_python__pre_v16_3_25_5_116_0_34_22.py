from __future__ import annotations

"""Cleanroom must verify, not guess, the managed interpreter after offline start."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/package-distribution-cleanroom.yml"


def test_cleanroom_uses_verified_managed_python_for_poststart_diagnostics() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    first_start = workflow.index('"$BARE_PYTHON" run.py start --json')
    marker_check = workflow.index('from latka_jazn.dependencies.environment import dependency_activation_status')
    doctor = workflow.index('"$BARE_PYTHON" "$RUNNER_TEMP/verified_managed_cli.py" doctor --json')
    assert first_start < marker_check < doctor
    assert 'status.get("required_ready") is True' in workflow
    assert 'status.get("managed_environment_covers_required_profiles") is True' in workflow
    assert 'managed.get("ready") is True' in workflow
    assert 'verified_managed_python_not_ready' in workflow
    assert 'raise SystemExit(78)' in workflow
    assert 'subprocess.call(command, cwd=root)' in workflow
    for args in ('doctor --json', 'host-diagnose --root . --json',
                 'status --json > "$RUNNER_TEMP/status-after-start.json"',
                 'start --json > "$RUNNER_TEMP/start-again.json"',
                 'stop --json > "$RUNNER_TEMP/stop.json"'):
        assert f'"$BARE_PYTHON" "$RUNNER_TEMP/verified_managed_cli.py" {args}' in workflow
    assert '"$BARE_PYTHON" run.py status --json > "$RUNNER_TEMP/status.json"' in workflow
    assert '"$BARE_PYTHON" run.py start --json > "$RUNNER_TEMP/start.json"' in workflow
