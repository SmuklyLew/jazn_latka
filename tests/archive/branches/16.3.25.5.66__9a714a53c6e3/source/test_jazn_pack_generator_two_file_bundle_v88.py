from __future__ import annotations

import importlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def test_v101860111_launcher_is_small_source_launcher_not_embedded_bundle() -> None:
    launcher = (ROOT / "tools/jazn_pack_generator.py").read_text(encoding="utf-8")
    assert "_BUNDLED_MODULES" not in launcher
    assert "b85decode" not in launcher
    assert "jazn_pack_generator_app" in launcher
    assert "package_distribution" not in launcher
    assert (ROOT / "tools/jazn_pack_generator_app/service.py").is_file()
    assert (ROOT / "tools/jazn_pack_generator_app/ui_studio.py").is_file()

def test_v101860111_source_layout_validator_passes() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "tools/build_jazn_pack_generator_bundle.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "source_layout_valid=true" in result.stdout

def test_v101860111_settings_live_with_tool_app() -> None:
    module = importlib.import_module("tools.jazn_pack_generator")
    path = Path(module.load_settings.__module__.replace(".", "/"))
    del path
    from tools.jazn_pack_generator_app.settings import settings_path
    assert settings_path().name == "jazn_pack_generator_settings.json"
    assert settings_path().parent.name == "jazn_pack_generator_app"
