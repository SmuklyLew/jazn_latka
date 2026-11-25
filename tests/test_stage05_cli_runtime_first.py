"""Stage 05: public conversation commands establish runtime before model discovery."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import main as control
from latka_jazn.core.daemon_autostart import DaemonEnsureResult


@pytest.mark.parametrize("flags", [
    ["--chat"], ["--chat-open-ai"],
    ["--daemon-send", "--daemon-channel", "ollama"],
    ["--daemon-submit", "--daemon-channel", "ollama"],
])
def test_runtime_gate_precedes_model_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: list[str]) -> None:
    events: list[str] = []

    def ensure(*_a: Any, **_k: Any) -> tuple[DaemonEnsureResult, int]:
        events.append("daemon")
        return DaemonEnsureResult(ok=False, ensured=False, active_state="inactive",
                                  reason="unavailable", decision={}), 1

    def forbidden(*_a: Any, **_k: Any) -> None:
        pytest.fail("model discovery or submission before daemon verification")

    monkeypatch.setattr(control, "_ensure_daemon_or_error", ensure)
    monkeypatch.setattr(control, "build_llm_route_status", forbidden)
    monkeypatch.setattr(control, "_daemon_cli_channel_settings", forbidden)
    monkeypatch.setattr(control, "_run_chat_command_one_shot", forbidden)
    monkeypatch.setattr(control, "run_jsonl_chat_bridge", forbidden)
    assert control.legacy_main(["--root", str(tmp_path), "--no-runtime-preflight", *flags, "--", "Hej."]) == 1
    assert events == ["daemon"]


def test_auto_route_checks_daemon_once_before_discovery_and_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def ensure(*_a: Any, **_k: Any) -> tuple[DaemonEnsureResult, None]:
        events.append("daemon")
        return DaemonEnsureResult(ok=True, ensured=True, active_state="active_trusted",
                                  reason="verified", decision={}, selected_transport="persistent_daemon",
                                  daemon_identity_verified=True), None

    def route(*_a: Any, **_k: Any) -> Any:
        events.append("model")
        return SimpleNamespace(selected_route="null_fallback")

    def submit(**_k: Any) -> int:
        events.append("submit")
        return 0

    monkeypatch.setattr(control, "_ensure_daemon_or_error", ensure)
    monkeypatch.setattr(control, "build_llm_route_status", route)
    monkeypatch.setattr(control, "apply_llm_route_to_config", lambda *_a: None)
    monkeypatch.setattr(control, "_run_chat_command_one_shot", submit)
    assert control.legacy_main(["--root", str(tmp_path), "--no-runtime-preflight", "--chat", "--", "Hej."]) == 0
    assert events == ["daemon", "model", "submit"]
