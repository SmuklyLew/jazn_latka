"""Redirected operator output preserves runtime Unicode under legacy locales."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.jazn_run_studio.external import environment


def test_redirected_headless_output_is_utf8(tmp_path: Path) -> None:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text('PACKAGE_VERSION="test"', encoding="utf-8")
    (tmp_path / "main.py").write_text("# isolated synthetic control plane", encoding="utf-8")
    expected = "🕒 Łatka — diagnostyka"
    (tmp_path / "run.py").write_text("print(" + repr(expected) + ")", encoding="utf-8")
    env = dict(os.environ, PYTHONUTF8="0", PYTHONIOENCODING="cp1250")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "jazn_run_studio.py"),
        "--root", str(tmp_path), "--run", "version"], cwd=root, env=env,
        capture_output=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout.decode("utf-8")


def test_child_output_encoding_overrides_inherited_legacy_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONIOENCODING", "cp1250")
    result = subprocess.run([sys.executable, "-c", "print(chr(0x1f552))"],
        env=environment(), capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode("utf-8").strip() == "🕒"
