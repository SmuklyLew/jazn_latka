"""TPA regression-subcheck boundaries (not a claim of full manual acceptance)."""
from __future__ import annotations

from pathlib import Path
import pytest

pytest.importorskip("PySide6")

from tools.jazn_run_studio import local_acceptance
from tools.jazn_run_studio.tpa_runner import AUTOMATED_CASES, allowed_files


def test_all_22_operator_cases_remain_manual_gates() -> None:
    catalog = local_acceptance.catalog(Path("."), local_acceptance._empty())
    assert len(catalog) == 22
    ids = {item["id"] for item in catalog}
    assert set(AUTOMATED_CASES) <= ids
    assert "ollama-two-turns" not in AUTOMATED_CASES
    assert "chat-resume" not in AUTOMATED_CASES
    assert len(local_acceptance.STUDIO_CATALOG) == 12


def test_allowlist_only_permits_existing_bounded_regression_files(tmp_path: Path) -> None:
    for files in AUTOMATED_CASES.values():
        for relative in files:
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def test_example(): assert True\n", encoding="utf-8")
    names = tuple(AUTOMATED_CASES)
    result = allowed_files(tmp_path, names)
    assert len(result) == len(set(result))
    assert all(name.startswith("tests/") and name.endswith(".py") for name in result)
    with pytest.raises(ValueError, match="ręcznego"):
        allowed_files(tmp_path, ("daemon-restart",))
    with pytest.raises(ValueError, match="ręcznego"):
        allowed_files(tmp_path, ("../../outside.py",))


def test_symlink_or_missing_subcheck_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="nie jest dostępny"):
        allowed_files(tmp_path, ("smoke-isolation",))
    outside = tmp_path.parent / ("outside-" + tmp_path.name + ".py")
    outside.write_text("pass\n", encoding="utf-8")
    link = tmp_path / "tests" / "test_package_smoke_workspace_isolation.py"
    link.parent.mkdir()
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Host nie pozwala utworzyć symlinków testowych")
    with pytest.raises(ValueError, match="nie jest dostępny"):
        allowed_files(tmp_path, ("smoke-isolation",))


def test_qt_runner_rejects_invalid_python_before_spawning(tmp_path: Path) -> None:
    from tools.jazn_run_studio.tpa_runner import SafeTPARunner
    selected = tmp_path / "tests" / "test_package_smoke_workspace_isolation.py"
    selected.parent.mkdir()
    selected.write_text("def test_foo(): assert True\n", encoding="utf-8")
    runner = SafeTPARunner(tmp_path, "")
    with pytest.raises(ValueError, match="interpreter"):
        runner.start_cases(("smoke-isolation",))
    assert runner.active is False
    assert runner.process.processId() == 0
