"""Launchers preserve verified portable bundles and prefer checkout .venv."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_prefers_private_venv_before_host_python() -> None:
    source = (ROOT / "JAZN.cmd").read_text(encoding="utf-8")
    assert source.index("JAZN_PYTHON_RUNTIME_SET.json") < source.index('if exist "%JAZN_ROOT%.venv"')
    assert source.index('if exist "%JAZN_ROOT%.venv"') < source.index("where py.exe")
    assert "Niekompletne ROOT\\.venv" in source
    assert 'exit /b 78' in source


def test_posix_launcher_prefers_private_venv_before_host_python() -> None:
    source = (ROOT / "jazn").read_text(encoding="utf-8")
    assert source.index('SET="$ROOT/JAZN_PYTHON_RUNTIME_SET.json"') < source.index('if [ -e "$ROOT/.venv" ]')
    assert source.index('if [ -e "$ROOT/.venv" ]') < source.index("for PYTHON in python3 python")
    assert 'exec "$ROOT/.venv/bin/python" -X utf8' in source
    assert 'exit 78' in source


def test_optional_mcp_and_tk_probes_never_promote_core_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = ROOT / "tools" / "local_runtime_preflight.py"
    spec = importlib.util.spec_from_file_location("jazn_private_preflight_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    for rel in ("run.py", "main.py", "AGENTS.md", "latka_jazn/version.py"):
        entry = tmp_path / rel
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(module, "_ollama", lambda *_: {"ok": False})
    monkeypatch.setattr(module, "_private_environment_report",
                        lambda _root: {"present": False, "ready": False, "state": "absent"})
    monkeypatch.setattr(module, "_optional_tk_probe",
                        lambda *_: {"status": "not_checked"})
    monkeypatch.setattr(module, "_optional_mcp_probe",
                        lambda *_: {"status": "imports_missing"})
    report = module.build_report(tmp_path, run_diagnostics=False)
    assert report["ok"] is True
    assert report["mcp_imports"]["status"] == "imports_missing"
    assert report["tk_gui"]["status"] == "not_checked"
    assert report["run_py"]["skipped"] is True
