"""Use the running interpreter's absolute path for the optional Qt type gate."""
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", "pyright", "--pythonpath", sys.executable,
         "tools/jazn_run_studio", "jazn_run_studio.py", "tests/test_jazn_run_studio.py",
         "tests/test_jazn_run_studio_integrations.py", "tests/test_jazn_run_studio_secrets.py",
         "tests/test_jazn_run_studio_chat_contract.py", "tests/test_jazn_run_studio_lifecycle_results.py",
         "tests/test_jazn_run_studio_http_framing.py", "tests/test_jazn_run_studio_layout.py", "tests/test_jazn_run_studio_utf8.py",
         "tests/test_jazn_run_studio_memory_view.py", "tests/test_memory_operator_report.py"],
        cwd=root, shell=False, check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
