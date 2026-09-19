from __future__ import annotations
import importlib.util, sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools/local_runtime_preflight.py"
SPEC = importlib.util.spec_from_file_location("local_runtime_preflight", TOOL)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

def fixture_root(tmp_path: Path) -> Path:
    for rel in ("run.py", "main.py", "AGENTS.md", "latka_jazn/version.py"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# fixture\n", encoding="utf-8")
    return tmp_path

def test_required_files_pass_without_live_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(MOD, "_ollama", lambda *_: {"ok": False})
    r = MOD.build_report(fixture_root(tmp_path), run_diagnostics=False)
    assert r["ok"] is True
    assert r["ollama"]["ok"] is False

def test_missing_agents_fails_closed(tmp_path, monkeypatch):
    root = fixture_root(tmp_path)
    (root / "AGENTS.md").unlink()
    monkeypatch.setattr(MOD, "_ollama", lambda *_: {"ok": True})
    r = MOD.build_report(root, run_diagnostics=False)
    assert r["ok"] is False
    assert r["files"]["agents_md"] is False

def test_diagnostics_can_be_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(MOD, "_ollama", lambda *_: {"ok": True})
    r = MOD.build_report(fixture_root(tmp_path), run_diagnostics=False)
    assert r["run_py"]["skipped"] is True


