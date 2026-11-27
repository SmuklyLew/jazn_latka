"""Keep the Stage 05 deterministic remediation suite in the Windows release gate."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_stage05_windows_release_gate_runs_each_remediation_module_and_keeps_failure_report() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release-hardening.yml").read_text(encoding="utf-8")
    windows = workflow.split("\n  verify_windows:\n", 1)[1].split("\n  dependency_contract_matrix:", 1)[0]
    step = windows.split("- name: Stage 05 F01-F06 Windows deterministic regressions", 1)[1].split("- name:", 1)[0]
    assert "shell: pwsh" in step
    assert "python -X utf8 -m pytest" in step
    assert 'continue-on-error:' not in step
    assert "\n        if:" not in step
    assert '--junitxml="${{ runner.temp }}/pytest-windows-stage05.xml"' in step
    for module in (
        "tests/test_stage05_f01_admission_ledger_guard.py",
        "tests/test_stage05_f01_durable_write_and_poll.py",
        "tests/test_stage05_f01_terminal_request_retention.py",
        "tests/test_stage05_f02_diagnostic_authority_binding.py",
        "tests/test_stage05_f02_local_model_failure.py",
        "tests/test_stage05_f02_null_executor_failure.py",
        "tests/test_stage05_f03_runtime_poll_completion.py",
        "tests/test_stage05_f04_ollama_output_limit.py",
        "tests/test_stage05_f05_exact_response_transport.py",
        "tests/test_stage05_f05_tcp_disconnect.py",
        "tests/test_stage05_f06_sqlite_maintenance_boundaries.py",
        "tests/test_stage05_f06_verified_restore_quiescence.py",
        "tests/test_stage05_windows_regression_gate.py",
    ):
        assert (ROOT / module).is_file()
        assert step.count(module) == 1
    failure_upload = windows.split("- name: Upload Windows pytest report on failure", 1)[1].split("- name:", 1)[0]
    assert "if: failure()" in failure_upload
    assert "${{ runner.temp }}/pytest-windows-stage05.xml" in failure_upload
    assert "needs: [manifest_sync, verify_ubuntu, verify_windows]" in workflow
