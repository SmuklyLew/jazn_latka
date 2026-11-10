from __future__ import annotations

from pathlib import Path


def test_windows_cmd_launcher_is_root_relative_and_venv_independent() -> None:
    """A complete ROOT-local venv wins; an incomplete one must fail closed."""
    root = Path(__file__).resolve().parents[1]
    text = (root / "JAZN.cmd").read_text(encoding="utf-8")
    folded = text.lower()

    assert "%~dp0" in text
    assert '"%JAZN_ROOT%run.py"' in text
    assert "py.exe -3" in text
    assert 'if exist "%jazn_root%.venv"' in folded
    assert 'if not exist "%jazn_root%.venv\\pyvenv.cfg"' in folded
    assert 'if not exist "%jazn_root%.venv\\scripts\\python.exe"' in folded
    assert '"%jazn_root%.venv\\scripts\\python.exe" -x utf8' in folded
    assert "exit /b 78" in folded
    assert folded.index('if exist "%jazn_root%.venv"') < folded.index("where py.exe")
