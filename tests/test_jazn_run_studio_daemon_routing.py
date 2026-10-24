"""Studio Jaźni GUI uses one safe daemon endpoint across lifecycle and chat."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from tools.jazn_run_studio.core import Controller, Settings, StudioError, daemon_cli_options
from tools.jazn_run_studio.chat import ChatClient


@pytest.fixture
def system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text("PACKAGE_VERSION='test'", encoding="utf-8")
    (tmp_path / "main.py").write_text("# isolated control plane", encoding="utf-8")
    (tmp_path / "run.py").write_text("# isolated public launcher", encoding="utf-8")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "isolated_workspace"))
    return tmp_path


def test_selected_daemon_endpoint_is_used_for_lifecycle_and_diagnostics(system: Path) -> None:
    controller = Controller(system)
    controller.settings = Settings(model="gemma3:latest", daemon_url="http://127.0.0.1:8877")
    target = ["--daemon-host", "127.0.0.1", "--daemon-port", "8877"]
    for key in ("status", "doctor"):
        assert controller.command(key)[-4:] == target
    for key in ("start", "stop", "restart"):
        assert controller.command(key)[-5:] == ["--", *target]
    assert "8787" not in " ".join(controller.command("start"))


def test_gui_chat_uses_canonical_command_and_pinned_endpoint(system: Path) -> None:
    controller = Controller(system)
    controller.settings = Settings(model="gemma3:latest", daemon_url="http://127.0.0.1:8877")
    client = ChatClient(controller)
    command = client.connection_command()
    assert "--chat-ollama" in command
    assert "chat-ollama" not in command
    assert command[-4:] == ["--ollama-model", "gemma3:latest", "--session-id", client.session_id]
    assert command[command.index("--daemon-port")+1] == "8877"
    assert client.resume_command("turn-1")[-4:] == ["--daemon-host", "127.0.0.1", "--daemon-port", "8877"]
    assert client.resume_command("turn-1")[client.resume_command("turn-1").index("--daemon-result")+1] == "turn-1"


def test_chat_checkpoint_keeps_session_request_and_daemon_target(system: Path) -> None:
    controller = Controller(system)
    controller.settings = Settings(model="gemma3:latest", daemon_url="http://127.0.0.1:8877")
    first = ChatClient(controller)
    first.pending = "pending-001"
    first._save()
    second = ChatClient(controller)
    assert second.session_id == first.session_id
    assert second.pending == "pending-001"
    assert second.resume_command(second.pending)[-1] == "8877"
    controller.settings = replace(controller.settings, daemon_url="http://127.0.0.1:8787")
    with pytest.raises(StudioError, match="endpoint"):
        second.resume_command("pending-001")
    with pytest.raises(StudioError, match="Checkpoint"):
        ChatClient(controller)


@pytest.mark.parametrize("endpoint", (
    "http://127.0.0.1:8877/live",
    "http://127.0.0.1:8877?token=bad",
    "http://localhost:8877",
    "http://127.0.0.1:99999",
    "https://127.0.0.1:8877",
))
def test_daemon_route_rejects_noncanonical_target(endpoint: str) -> None:
    with pytest.raises(StudioError):
        daemon_cli_options(Settings(daemon_url=endpoint))


def test_default_studio_route_remains_backward_compatible(system: Path) -> None:
    controller = Controller(system)
    assert controller.command("status")[-2:] == ["status", "--json"]
    assert controller.command("start")[-1] == "start"


def test_no_automatic_replay_after_pending_request(system: Path) -> None:
    controller = Controller(system)
    controller.settings = Settings(model="gemma3:latest", daemon_url="http://127.0.0.1:8877")
    client = ChatClient(controller)
    client.pending = "pending-002"
    with pytest.raises(StudioError, match="Najpierw odbierz"):
        client.send("nie wysyłaj ponownie")


def test_restart_reuses_selected_endpoint_and_does_not_fall_back_to_8787(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from latka_jazn import cli
    called: list[list[str]] = []
    def fake_legacy(args: list[str], **kwargs: object) -> int:
        called.append(args)
        return 0
    monkeypatch.setattr(cli, "_legacy_main", fake_legacy)
    monkeypatch.setattr(cli.diagnostics, "status_payload",
                        lambda root, **kwargs: {"ok": kwargs["daemon_port"] == 8877})
    (tmp_path / "run.py").write_text("", encoding="utf-8")
    assert cli.main(["restart", "--", "--daemon-host", "127.0.0.1",
                         "--daemon-port", "8877"]) == 0
    assert len(called) == 2
    assert all("--daemon-port" in args and "8877" in args for args in called)
    assert all("8787" not in args for args in called)
