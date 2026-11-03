"""A passing call cannot seal PASS when pytest teardown is interrupted."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.jazn_run_studio.test_evidence_archive import history


@pytest.mark.parametrize("call", ["assert True", "assert False, 'call failed'"])
def test_keyboard_interrupt_in_teardown_preserves_incomplete_evidence(tmp_path, call):
    root = tmp_path / "SYSTEM"
    (root / "tests").mkdir(parents=True)
    (root / "latka_jazn").mkdir()
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths=["tests"]\n', encoding="utf-8")
    (root / "tests/test_interrupt.py").write_text(
        'import pytest\n@pytest.fixture\ndef interrupted():\n'
        '    yield\n    raise KeyboardInterrupt("controlled teardown interruption")\n'
        f'def test_case(interrupted):\n    {call}\n', encoding="utf-8")
    output = tmp_path / "evidence"
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("JAZN_", "PYTEST_", "PYTHONPATH"))}
    env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]),
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1",
               PYTHONUTF8="1", JAZN_TEST_EVIDENCE_DIR=str(output))
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "-p", "tools.jazn_run_studio.test_evidence_plugin",
         "--junitxml=" + str(tmp_path / "pytest.xml")],
        cwd=root, env=env, capture_output=True, timeout=60, check=False)
    assert result.returncode == 2, result.stdout.decode("utf-8", errors="replace")
    runs, errors = history(output)
    assert not errors and len(runs) == 1
    run = runs[0]
    row = next(row for row in run["results"]
               if row.get("name", "").endswith("::test_case"))
    assert row["execution_status"] == ("INTERRUPTED" if call == "assert True" else "FAIL")
    assert row["full_gate_status"] == "NOT_RUN"
    assert run["summary"]["release_status"] == "RELEASE_NOT_ACCEPTED"
    assert run["summary"]["finished_utc"]
