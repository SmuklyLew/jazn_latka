from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "jazn_pack_generator.py"
CURRENT_CORE = ROOT / "tools" / "pack_generator_sources" / "jazn_pack_generator_core.py"
CURRENT_UI = ROOT / "tools" / "pack_generator_sources" / "jazn_pack_generator_ui.py"
LEGACY_HELPERS = (
    "_jazn_pack_generator_core.py",
    "_jazn_pack_generator_memory_v2.py",
    "_jazn_pack_generator_v1601_policy.py",
    "_jazn_pack_generator_v1638_archive_io.py",
    "_jazn_pack_generator_v16311_profiles.py",
)


def test_v1001_generator_has_no_legacy_helper_files() -> None:
    for filename in LEGACY_HELPERS:
        assert not (ROOT / "tools" / filename).exists(), filename


def test_v101860_launcher_embeds_only_current_runtime_sources() -> None:
    launcher = GENERATOR.read_text(encoding="utf-8")
    core = CURRENT_CORE.read_text(encoding="utf-8")
    ui = CURRENT_UI.read_text(encoding="utf-8")

    assert "_BUNDLED_MODULES" in launcher
    assert "b85decode" in launcher
    assert "zlib" not in launcher
    assert "pack_generator_sources" not in launcher
    assert "jazn_pack_generator_v89.py" not in launcher
    assert "jazn_pack_generator_v88.py" not in launcher
    assert "tkinter" not in launcher
    assert "tkinter" not in ui
    assert "GENERATOR_VERSION = \"10.1.86.0\"" in core


def test_v1001_generator_imports_from_public_launcher() -> None:
    module = importlib.import_module("tools.jazn_pack_generator")

    assert module.GENERATOR_VERSION == "10.1.86.0"
    assert module.GENERATOR_TITLE == "Generator dystrybucji Jaźni"
    assert module.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v10.1.86.0"
    assert callable(module.main)


def test_v101860_two_file_copy_runs_without_source_modules(tmp_path: Path) -> None:
    launcher = tmp_path / "jazn_pack_generator.py"
    settings = tmp_path / "jazn_pack_generator_settings.json"
    shutil.copy2(GENERATOR, launcher)
    settings.write_text(
        json.dumps({"source": str(ROOT)}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(launcher), "config"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["generator_version"] == "10.1.86.0"
    assert Path(payload["settings_path"]) == settings
    assert not (tmp_path / "pack_generator_sources").exists()
