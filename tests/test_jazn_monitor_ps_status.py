"""Newer Monitor Jaźni: installed and loaded Ollama models are different facts."""
from __future__ import annotations

from tools.jazn_monitor import probe


def test_monitor_loaded_models_only_from_explicit_ps(monkeypatch):
    calls = []

    def read(port: int, endpoint: str, timeout: float = 1.5):
        calls.append((port, endpoint))
        if endpoint == "/api/tags":
            return {"models": [{"name": "gemma3:latest"}, {"name": "other"}]}
        if endpoint == "/api/ps":
            return {"models": [{"name": "gemma3:latest"}]}
        return None

    monkeypatch.setattr(probe, "_http_json", read)
    monkeypatch.setattr(probe, "process_snapshot", lambda *_args: {"state": "unavailable", "items": []})
    monkeypatch.setattr(probe, "jobs_snapshot", lambda *_args: {"state": "unavailable", "items": [], "finalization": {}})
    report = probe.snapshot(None, ollama_port=11434)
    assert report["services"]["Ollama"]["state"] == "reachable"
    assert "modeli: 2" in report["services"]["Ollama"]["detail"]
    assert "załadowanych: 1" in report["services"]["Ollama"]["detail"]
    assert "generacja niesprawdzona" in report["services"]["Ollama"]["detail"]
    assert report["services"]["MCP HTTPS"]["state"] == "unknown"
    assert (11434, "/api/tags") in calls and (11434, "/api/ps") in calls


def test_missing_ps_does_not_claim_no_loaded_models(monkeypatch):
    monkeypatch.setattr(
        probe, "_http_json",
        lambda _port, endpoint, timeout=1.5: (
            {"models": [{"name": "gemma3:latest"}]}
            if endpoint == "/api/tags" else None
        ),
    )
    monkeypatch.setattr(probe, "process_snapshot", lambda *_args: {"state": "unavailable", "items": []})
    monkeypatch.setattr(probe, "jobs_snapshot", lambda *_args: {"state": "unavailable", "items": [], "finalization": {}})
    report = probe.snapshot(None)
    ollama = report["services"]["Ollama"]
    assert ollama["state"] == "reachable"
    assert "brak zweryfikowanego odczytu /api/ps" in ollama["detail"]
    assert "załadowanych: 0" not in ollama["detail"]
