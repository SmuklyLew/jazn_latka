"""Stage 05 CLI orchestration: runtime readiness precedes Ollama discovery."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core.daemon_autostart import DaemonEnsureResult


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        message=[], ollama_model=None, ollama_api_base=None,
        ollama_timeout=None, ollama_max_output_tokens=None,
    )


def test_ollama_model_probe_is_not_attempted_if_daemon_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = JaznConfig(root=tmp_path)
    events: list[str] = []

    def ensure(*args: object, **kwargs: object) -> tuple[DaemonEnsureResult, int]:
        events.append("daemon")
        return DaemonEnsureResult(
            ok=False, ensured=False, active_state="inactive",
            reason="daemon_start_failed", decision={},
        ), 1

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("model probe or conversation before verified daemon")

    monkeypatch.setattr(main_module, "_ensure_daemon_or_error", ensure)
    monkeypatch.setattr(main_module, "resolve_ollama_cli_settings", forbidden)
    monkeypatch.setattr(main_module, "run_jsonl_chat_bridge", forbidden)
    monkeypatch.setattr(main_module, "_run_chat_command_one_shot", forbidden)
    monkeypatch.setattr(main_module.sys, "stdin", io.StringIO())
    assert main_module._run_chat_ollama_command(_args(), cfg) == 1
    assert events == ["daemon"]


@pytest.mark.parametrize("reason", ["ollama_unavailable", "ollama_has_no_models", "configured_model_not_installed", "ollama_model_ambiguous"])
def test_ollama_unavailable_is_a_route_failure_after_runtime_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], reason: str,
) -> None:
    cfg = JaznConfig(root=tmp_path)
    events: list[str] = []

    def ensure(*args: object, **kwargs: object) -> tuple[DaemonEnsureResult, None]:
        events.append("daemon")
        return DaemonEnsureResult(
            ok=True, ensured=True, active_state="active_trusted",
            reason="daemon_already_active", decision={},
            selected_transport="persistent_daemon",
            daemon_reused=True, daemon_identity_verified=True,
        ), None

    def probe(*args: object, **kwargs: object) -> tuple[JaznConfig, dict[str, object]]:
        events.append("model")
        return cfg, {"available": False, "reason": reason}

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("an unavailable explicit model must not submit a turn or fallback")

    monkeypatch.setattr(main_module, "_ensure_daemon_or_error", ensure)
    monkeypatch.setattr(main_module, "resolve_ollama_cli_settings", probe)
    monkeypatch.setattr(main_module, "run_jsonl_chat_bridge", forbidden)
    monkeypatch.setattr(main_module, "_run_chat_command_one_shot", forbidden)
    monkeypatch.setattr(main_module.sys, "stdin", io.StringIO())
    assert main_module._run_chat_ollama_command(_args(), cfg) == 3
    assert events == ["daemon", "model"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error_code"] == reason
    assert payload["daemon_preflight"]["active_state"] == "active_trusted"
    assert payload["daemon_preflight"]["daemon_reused"] is True
