from __future__ import annotations

from pathlib import Path


def test_windows_cmd_launcher_is_root_relative_and_venv_independent() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "JAZN.cmd").read_text(encoding="utf-8")

    assert "%~dp0" in text
    assert '"%JAZN_ROOT%run.py"' in text
    assert "py.exe -3" in text
    assert ".venv" not in text.lower() or "nie jest wymagane" in text.lower()

