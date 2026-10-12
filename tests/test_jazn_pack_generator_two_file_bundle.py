from __future__ import annotations

import importlib
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]

def test_launcher_is_small_source_launcher_not_embedded_bundle() -> None:
    launcher = (ROOT / "tools/jazn_pack_generator.py").read_text(encoding="utf-8")
    assert "_BUNDLED_MODULES" not in launcher
    assert "b85decode" not in launcher
    assert "jazn_pack_generator_app" in launcher
    assert "package_distribution" not in launcher
    assert (ROOT / "tools/jazn_pack_generator_app/service.py").is_file()
    assert (ROOT / "tools/jazn_pack_generator_app/ui_studio.py").is_file()

def test_source_layout_validator_passes() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "tools/build_jazn_pack_generator_bundle.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "source_layout_valid=true" in result.stdout

def test_settings_live_outside_verified_system(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = importlib.import_module("tools.jazn_pack_generator")
    assert callable(module.load_settings)

    monkeypatch.delenv("JAZN_PACK_GENERATOR_SETTINGS", raising=False)
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path))
    from tools.jazn_pack_generator_app.settings import settings_path

    target = settings_path()
    assert target == tmp_path.resolve() / "jazn-pack-generator" / "jazn_pack_generator_settings.json"
    assert not target.is_relative_to(ROOT.resolve())
    assert not target.exists()
    assert not target.parent.exists()
