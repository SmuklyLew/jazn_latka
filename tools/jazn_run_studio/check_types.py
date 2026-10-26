"""Use the running interpreter's absolute path for the optional Qt type gate."""
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", "pyright", "--pythonpath", sys.executable,
         "tools/jazn_run_studio", "jazn_run_studio.py", "run_studio.py",
         "tests/test_heart_system_dashboard.py", "tests/test_heart_system_dashboard_qt.py", "tests/test_heart_system_diagnostics.py", "tests/test_heart_system_workspace_qt.py", "tests/test_heart_system_public_restart.py", "tests/test_jazn_run_studio.py",
         "tests/test_jazn_run_studio_integrations.py", "tests/test_jazn_run_studio_env_guard.py",
         "tests/test_jazn_run_studio_chat_contract.py", "tests/test_jazn_run_studio_lifecycle_results.py",
         "tests/test_jazn_run_studio_http_framing.py", "tests/test_jazn_run_studio_layout.py", "tests/test_jazn_run_studio_utf8.py",
         "tests/test_jazn_run_studio_memory_view.py", "tests/test_memory_operator_report.py",
         "tests/test_memory_evidence_compact_layout.py", "tests/test_memory_readiness_pin_diagnostics.py"],
        cwd=root, shell=False, check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
