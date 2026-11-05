"""An optional Windows onedir executable is labelled without touching python.exe."""
from pathlib import Path


def test_windows_studio_branding_is_for_the_frozen_app_only() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "tools/jazn_run_studio/build.py").read_text(encoding="utf-8")
    resource = (root / "tools/jazn_run_studio/windows_version_info.txt").read_text(encoding="utf-8")
    assert 'if os.name == "nt":' in script
    assert "--version-file" in script
    assert "Jaźń — Serce Systemu / JSS" in resource
    assert "JaznRunStudio.exe" in resource
    assert "python.exe" not in resource
