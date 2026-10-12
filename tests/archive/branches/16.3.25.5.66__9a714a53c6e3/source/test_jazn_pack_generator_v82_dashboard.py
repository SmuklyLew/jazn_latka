from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"


def _load_generator():
    module_name = "jazn_pack_generator_v101860111_ui_boundary_test"
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_prompt_toolkit_dashboard_is_retired_in_clean_rewrite() -> None:
    generator = _load_generator()
    assert generator.UI_MODE_CHOICES == ("text", "tui", "studio")
    assert not hasattr(generator, "cursor_dashboard")
    assert not hasattr(generator, "_dashboard_available")
    tui = (ROOT / "tools" / "jazn_pack_generator_app" / "ui_tui.py").read_text(encoding="utf-8")
    assert "prompt_toolkit" not in tui


def test_native_studio_is_separate_from_small_public_launcher() -> None:
    generator = _load_generator()
    launcher = GENERATOR_PATH.read_text(encoding="utf-8")
    studio = (ROOT / "tools" / "jazn_pack_generator_app" / "ui_studio.py").read_text(encoding="utf-8")
    assert callable(generator.run_studio_ui)
    assert "import tkinter" not in launcher
    assert "tkinter" in studio
