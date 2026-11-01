"""Real pytest outcomes, including teardown errors, retain independent evidence."""
import os
from pathlib import Path
import subprocess
import sys

from tools.jazn_run_studio.test_evidence_archive import history


def invoke(tmp_path: Path, source: str, *, collection_error: bool = False):
    root = tmp_path / "SYSTEM"
    (root / "tests").mkdir(parents=True)
    (root / "latka_jazn").mkdir()
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths=["tests"]\n', encoding="utf-8")
    (root / "tests/test_cases.py").write_text(source, encoding="utf-8")
    if collection_error:
        (root / "tests/test_broken.py").write_text("def test_broken(:\n", encoding="utf-8")
    output = tmp_path / "reports"
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(("JAZN_", "PYTEST_", "PYTHONPATH"))}
    env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", JAZN_TEST_EVIDENCE_DIR=str(output))
    result = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                             "-p", "tools.jazn_run_studio.test_evidence_plugin", "--junitxml=" + str(tmp_path / "pytest.xml")],
                            cwd=root, env=env, capture_output=True, timeout=60, check=False)
    runs, errors = history(output)
    assert not errors and len(runs) == 1, result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
    return result, runs[0], output


def test_real_pytest_fail_skip_and_teardown_error_are_not_promoted(tmp_path):
    result, run, output = invoke(tmp_path, '''import pytest
def test_ok(): assert True
@pytest.mark.skip(reason="missing compatible executor")
def test_skip(): pass
def test_fail(): assert False, "synthetic failure"
@pytest.fixture
def broken_teardown():
    yield
    raise RuntimeError("synthetic teardown error")
def test_teardown(broken_teardown): assert True
''')
    assert result.returncode == 1
    definitions = {row["scenario_id"]: row for row in run["manifest"]["scenarios"]}
    by_name = {definitions[row["scenario_id"]]["name"].split("::")[-1]: row for row in run["results"]}
    assert by_name["test_ok"]["execution_status"] == "PASS"
    assert by_name["test_skip"]["execution_status"] == "SKIPPED"
    assert by_name["test_fail"]["execution_status"] == "FAIL"
    assert by_name["test_teardown"]["execution_status"] == "ERROR"
    assert all(row["full_gate_status"] == "NOT_RUN" for row in run["results"])
    by_id = {row["scenario_id"]: row for row in run["results"]}
    assert by_id["gui-daemon"]["execution_status"] == "NOT_RUN"
    assert by_id["terminal-powershell-unicode"]["execution_status"] == "NOT_RUN"
    assert "evidence/pytest.xml" in run["files"]
    assert run["summary"]["release_status"] == "RELEASE_NOT_ACCEPTED"
    receipts = list(output.glob("run-*/pytest-*-*.json"))
    assert receipts
    assert all(path.with_suffix(".txt").is_file() for path in receipts)


def test_no_collected_tests_is_error_with_persistent_report(tmp_path):
    result, run, _ = invoke(tmp_path, "# No tests available\n")
    assert result.returncode == 5
    assert next(row for row in run["results"] if row["scenario_id"] == "pytest-collection")["execution_status"] == "ERROR"
    assert run["summary"]["release_status"] == "RELEASE_NOT_ACCEPTED"


def test_partial_collection_error_blocks_execution_and_collection_gate(tmp_path):
    result, run, _ = invoke(tmp_path, "def test_valid(): assert True\n", collection_error=True)
    assert result.returncode == 2
    assert next(row for row in run["results"] if row["scenario_id"] == "pytest-collection")["execution_status"] == "ERROR"
    assert any(row["execution_status"] == "INTERRUPTED" for row in run["results"])
    assert not any(row["execution_status"] == "PASS" for row in run["results"])
