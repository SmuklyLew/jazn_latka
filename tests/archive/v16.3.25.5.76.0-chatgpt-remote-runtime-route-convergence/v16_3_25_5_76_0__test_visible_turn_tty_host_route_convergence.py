from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation_entrypoint_contract import CANONICAL_CHATGPT_COMMAND, CANONICAL_CHAT_COMMAND
from latka_jazn.core.host_tool_turn_policy import build_host_tool_turn_policy
from latka_jazn.core.runtime_chat import LatkaRuntimeShell
from latka_jazn.core.runtime_environment import CHATGPT_ADAPTER, TERMINAL_ADAPTER, detect_runtime_environment
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_non_tty_chatgpt_host_bridge_is_valid_and_does_not_infer_persistence(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    environment = detect_runtime_environment(
        cfg,
        command=CANONICAL_CHATGPT_COMMAND,
        env={},
        stdin=io.StringIO(),
        stdout=io.StringIO(),
    )

    assert environment.is_chatgpt_host_bridge is True
    assert environment.visible_channel_adapter == CHATGPT_ADAPTER
    assert environment.stdin_isatty is False
    assert environment.stdout_isatty is False
    assert environment.io_surface == "chatgpt_host_bridge"
    assert environment.terminal_ui_mode == "host_managed_graphical_or_tool_channel"
    assert environment.tty_controls_enabled is False
    assert environment.tty_required_for_transport is False
    assert environment.process_persistence_inferred_from_tty is False


def test_tty_controls_are_terminal_ui_capability_not_persistence_proof(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    environment = detect_runtime_environment(
        cfg,
        command=CANONICAL_CHAT_COMMAND,
        env={"JAZN_VISIBLE_CHANNEL": "terminal"},
        stdin=_TtyStringIO(),
        stdout=_TtyStringIO(),
    )

    assert environment.visible_channel_adapter == TERMINAL_ADAPTER
    assert environment.is_terminal_chat_loop is True
    assert environment.io_surface == "terminal_tty"
    assert environment.terminal_ui_mode == "interactive_terminal"
    assert environment.tty_controls_enabled is True
    assert environment.tty_required_for_transport is False
    assert environment.process_persistence_inferred_from_tty is False


def test_runtime_shell_redirected_stdin_is_not_called_ephemeral() -> None:
    runtime = SimpleNamespace(engine=object(), state=SimpleNamespace(session_id="v64-test"))
    shell = LatkaRuntimeShell(runtime, stdin=io.StringIO(), stdout=io.StringIO())

    assert shell.lifecycle.stdin_is_tty is False
    assert shell.lifecycle.io_surface == "redirected_stdin_stream"
    assert shell.lifecycle.terminal_ui_mode == "redirected_stream"
    assert shell.lifecycle.tty_controls_enabled is False
    assert shell.lifecycle.process_persistence == "process_lifetime_bound"
    assert shell.lifecycle.process_persistence_inferred_from_tty is False
    assert "ephemeral_stdin_pipe" not in shell.lifecycle.to_dict().values()


def test_url_media_lookup_requires_web_but_keeps_same_turn_finalization() -> None:
    policy = build_host_tool_turn_policy(
        user_text="Posłuchaj https://youtu.be/3H62fsUm7_4 i powiedz, co o tym myślisz.",
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
        nlg_plan={"source_policy": "runtime_only"},
    )

    assert "web.run" in policy["allowed_tools"]
    assert "web.run" in policy["required_tools"]
    assert policy["runtime_owns_turn"] is True
    assert policy["tool_result_is_intermediate"] is True
    assert policy["same_turn_resume_required"] is True
    assert policy["finalization_required_after_tool_use"] is True
    assert policy["tool_output_may_be_visible_without_runtime_finalization"] is False
    assert policy["accepted_visible_turn_required"] is True
    assert policy["message_envelope_required"] is True


def test_music_lookup_without_url_allows_web_capability() -> None:
    policy = build_host_tool_turn_policy(
        user_text="Delerium Ritual muzyka",
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
        nlg_plan={"source_policy": "runtime_only"},
    )

    assert "web.run" in policy["allowed_tools"]


def test_chatgpt_loader_binds_tool_results_back_to_same_turn() -> None:
    root = Path(__file__).resolve().parents[1]
    loader = (root / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")
    assert len(loader) <= 5000
    assert "każdą zwykłą wiadomość użytkownika najpierw przekaż do runtime" in loader
    assert "Wynik narzędzia jest pośrednim evidence" in loader
    assert "action=display_exact" in loader
    assert "MessageEnvelope" in loader
    assert "Nie utożsamiaj TTY z rozmową ani trwałością" in loader


