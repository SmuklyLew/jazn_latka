"""Pure isolation, output integrity and privacy invariants for JSS visual CI."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.jazn_run_studio.visual_ci import (
    PROFILES, SCREENS, emit_reports, isolate_environment, prepare_output,
)


def test_profile_matrix_covers_all_three_visual_systems_and_core_pages() -> None:
    assert PROFILES == ("technical-workbench", "operations-studio", "fluent-studio")
    assert {title for _, title in SCREENS} >= {
        "Pulpit", "Usługi i procesy", "Katalog testów", "TPA",
        "Ustawienia", "Połączenie z ChatGPT",
    }


def test_visual_output_refuses_checkout_or_preexisting_target(tmp_path: Path) -> None:
    checkout = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="outside_checkout"):
        prepare_output(checkout / "_do_not_create", checkout)
    with pytest.raises(ValueError, match="outside_checkout"):
        prepare_output(checkout, checkout)
    target = tmp_path / "new"
    assert prepare_output(target, checkout) == target
    with pytest.raises(FileExistsError, match="output_must_be_new"):
        prepare_output(target, checkout)


def test_visual_run_scrubs_host_environment_and_creates_only_synthetic_files(tmp_path: Path) -> None:
    with patch.dict(os.environ, {"JAZN_TOKEN": "must_not_survive",
                                "JAZN_RUNTIME_WORKSPACE_DIR": "C:/production"}, clear=False):
        root = isolate_environment(tmp_path)
        assert os.environ.get("JAZN_TOKEN") is None
        assert os.environ["JAZN_MEMORY_MODE"] == "off"
        assert os.environ["QT_QPA_PLATFORM"] == "offscreen"
        assert os.environ["JAZN_RUNTIME_WORKSPACE_DIR"].startswith(str(tmp_path))
        assert os.environ["JAZN_MEMORY_ROOT"].startswith(str(tmp_path))
        assert (root / "run.py").is_file()
        assert (root / "main.py").is_file()
        assert (root / "latka_jazn" / "version.py").is_file()
        assert not (root / "memory").exists()
        assert not (root / "workspace_runtime").exists()


def test_reports_are_fail_closed_and_contain_no_private_environment(tmp_path: Path) -> None:
    report = {"status": "FAIL", "qt_platform": "offscreen", "checks": {"x": False},
              "captures": [], "errors": ["AssertionError:visual_ci_failure"]}
    with patch.dict(os.environ, {"JAZN_TOKEN": "do-not-leak"}, clear=False):
        emit_reports(tmp_path, report)
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8")) == report
    assert "FAIL" in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "do-not-leak" not in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "do-not-leak" not in (tmp_path / "report.md").read_text(encoding="utf-8")
