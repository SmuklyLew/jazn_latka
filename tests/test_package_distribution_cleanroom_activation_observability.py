from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "package-distribution-cleanroom.yml"


def test_cleanroom_prints_each_activation_payload_before_asserting() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for filename in (
        "preflight.json",
        "doctor.json",
        "start.json",
        "status-after-start.json",
        "start-again.json",
        "stop.json",
    ):
        assert f'cat "$RUNNER_TEMP/{filename}"' in text
    for variable in (
        "preflight_rc",
        "doctor_rc",
        "start_rc",
        "status_after_rc",
        "start_again_rc",
        "stop_rc",
    ):
        assert f'{variable}=$?' in text


def test_missing_sidecar_case_refuses_fresh_unprovisioned_system() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    negative = text.split(
        "- name: Reject fresh unprovisioned package when dependency sidecar is absent", 1
    )[1].split("- name: Dependency-empty run.py performs verified offline handoff", 1)[0]
    # Test absence of dependency evidence before installation, without erasing
    # a valid managed environment or mutating the immutable SYSTEM package.
    assert 'test ! -e ".venv"' in negative
    assert 'mv "$sidecar" "$sidecar.hidden"' in negative
    assert '''trap 'mv "$sidecar.hidden" "$sidecar"' EXIT''' in negative
    assert negative.index('mv "$sidecar" "$sidecar.hidden"') < negative.index(
        '"$BARE_PYTHON" run.py start --json'
    )
    assert 'rc=$?' in negative
    assert 'test "$rc" -ne 0' in negative
    assert 'no_compatible_verified_dependency_bundle' in negative
    assert 'dependencies_missing_no_verified_wheelhouse' in negative
    assert 'rm -rf "$dependency_state"' not in negative
    assert 'rm -rf "${{ steps.extract.outputs.runtime_dir }}/latka_jazn/local_resources/python"' not in text


def test_cleanroom_uses_dependency_free_preflight_before_managed_activation() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    preflight_command = '"$BARE_PYTHON" run.py host-preflight --json > "$RUNNER_TEMP/preflight.json"'
    activation_command = '"$BARE_PYTHON" run.py start --json > "$RUNNER_TEMP/start.json"'
    assert preflight_command in text
    assert activation_command in text
    before_activation = text[text.index(preflight_command):text.index(activation_command)]
    assert 'cat "$RUNNER_TEMP/preflight.json"' in before_activation
    assert "preflight_rc=$?" in before_activation
    assert 'test "$preflight_rc" -eq 0' in before_activation
    assert 'gate_passed' in before_activation
    assert 'bootstrap_allowed' in before_activation
    assert 'run.py doctor --json' not in before_activation
    assert 'run.py status --json' not in before_activation
    assert 'status_rc=$?' not in text
