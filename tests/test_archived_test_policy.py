from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from latka_jazn.tools.current_line_archive_audit import _is_active_path
from latka_jazn.tools.update_history_audit import find_test_evidence
from latka_jazn.tools.version_consistency_audit import _is_scannable


ROOT = Path(__file__).resolve().parents[1]


def _run_pytest(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pytest", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _make_policy_project(tmp_path: Path) -> Path:
    project = tmp_path / "policy_project"
    tests = project / "tests"
    archive = tests / "archive"
    archive.mkdir(parents=True)
    (project / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
    (tests / "conftest.py").write_bytes((ROOT / "tests" / "conftest.py").read_bytes())
    (tests / "test_active.py").write_text(
        "def test_active():\n    assert True\n",
        encoding="utf-8",
    )
    (archive / "test_retired.py").write_text(
        "from pathlib import Path\n"
        "import os\n\n"
        "def test_retired_keeps_runtime_isolated(tmp_path):\n"
        "    configured = Path(os.environ['JAZN_RUNTIME_WORKSPACE_DIR'])\n"
        "    assert configured == tmp_path / 'workspace_runtime'\n",
        encoding="utf-8",
    )
    return project


def test_repository_pytest_config_excludes_archive_by_default() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "archive" in config["tool"]["pytest"]["ini_options"]["norecursedirs"]


def test_default_collection_skips_archive_but_explicit_run_is_isolated(tmp_path: Path) -> None:
    project = _make_policy_project(tmp_path)

    collected = _run_pytest(project, "--collect-only", "-q")
    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert "test_active.py::test_active" in collected.stdout
    assert "test_retired.py" not in collected.stdout

    explicit = _run_pytest(project, "-q", "tests/archive/test_retired.py")
    assert explicit.returncode == 0, explicit.stdout + explicit.stderr
    assert "1 passed" in explicit.stdout


def test_active_line_and_evidence_audits_ignore_archived_tests(tmp_path: Path) -> None:
    archived = tmp_path / "tests" / "archive" / "test_retired.py"
    archived.parent.mkdir(parents=True)
    archived.write_text(
        "def test_archived_feature_token():\n    assert True\n",
        encoding="utf-8",
    )

    assert _is_active_path("tests/archive/test_retired.py") is False
    assert _is_scannable(archived, tmp_path) is False
    assert find_test_evidence(tmp_path, "archived_feature_token") == []

    active = tmp_path / "tests" / "test_active.py"
    active.write_text(
        "def test_archived_feature_token():\n    assert True\n",
        encoding="utf-8",
    )
    assert find_test_evidence(tmp_path, "archived_feature_token") == [
        "tests/test_active.py"
    ]
