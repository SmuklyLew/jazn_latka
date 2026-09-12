from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "package-distribution-cleanroom.yml"


def test_cleanroom_prints_each_activation_payload_before_asserting() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for filename in (
        "status.json",
        "doctor.json",
        "start.json",
        "status-after-start.json",
        "start-again.json",
        "stop.json",
    ):
        assert f'cat "$RUNNER_TEMP/{filename}"' in text
    for variable in (
        "status_rc",
        "doctor_rc",
        "start_rc",
        "status_after_rc",
        "start_again_rc",
        "stop_rc",
    ):
        assert f'{variable}=$?' in text


def test_missing_sidecar_case_resets_canonical_host_dependency_state() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "from latka_jazn.core.runtime_root import workspace_runtime_path" in text
    assert 'workspace_runtime_path(Path.cwd()) / "local_resources" / "python"' in text
    assert 'rm -rf "$dependency_state"' in text
    assert 'rm -rf "${{ steps.extract.outputs.runtime_dir }}/latka_jazn/local_resources/python"' not in text
