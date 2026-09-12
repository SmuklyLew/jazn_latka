from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core import bridge_discovery as bridge_discovery_module
from latka_jazn.core.conversation_entrypoint_contract import (
    AUTO_ROUTE_PRIORITY,
    CANONICAL_CHAT_COMMAND,
    CANONICAL_CHATGPT_COMMAND,
    ROUTE_CHATGPT_HOST,
    ROUTE_NULL_FALLBACK,
    ROUTE_OLLAMA_LOCAL,
    ROUTE_OPENAI_PAID,
    auto_route_priority_text,
    conversation_entrypoint_contract,
)
from latka_jazn.core.llm_route_resolver import build_llm_route_status
from latka_jazn.core.runtime_environment import (
    CHATGPT_ADAPTER,
    detect_runtime_environment,
)
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


def test_v59_canonical_auto_route_priority_is_shared_and_truthful() -> None:
    assert AUTO_ROUTE_PRIORITY == (
        ROUTE_CHATGPT_HOST,
        ROUTE_OLLAMA_LOCAL,
        ROUTE_OPENAI_PAID,
        ROUTE_NULL_FALLBACK,
    )
    assert auto_route_priority_text() == (
        "chatgpt_host_bridge -> ollama_local -> openai_api_paid -> null_fallback"
    )


def test_v59_universal_chat_contract_keeps_runtime_as_owner() -> None:
    contract = conversation_entrypoint_contract(CANONICAL_CHAT_COMMAND)

    assert contract.role == "universal_conversation"
    assert contract.route_mode == "auto"
    assert contract.route_priority == AUTO_ROUTE_PRIORITY
    assert contract.operator_command == "run.py chat"
    assert contract.persistent_runtime_preferred is True
    assert contract.host_finalization_policy == "required_only_when_chatgpt_host_route_selected"
    assert "własnością runtime" in contract.truth_boundary


def test_v59_chatgpt_entrypoint_is_host_bridge_not_openai_api() -> None:
    contract = conversation_entrypoint_contract(CANONICAL_CHATGPT_COMMAND)

    assert contract.role == "chatgpt_host_bridge"
    assert contract.route_priority == (ROUTE_CHATGPT_HOST,)
    assert contract.requires_api_key is False
    assert contract.uses_openai_api is False
    assert contract.host_finalization_policy == "two_phase_action_first"


def test_v59_universal_chat_detects_chatgpt_visible_host_before_terminal_default(tmp_path: Path) -> None:
    config = JaznConfig(root=tmp_path)
    environment = detect_runtime_environment(
        config,
        command=CANONICAL_CHAT_COMMAND,
        env={"JAZN_VISIBLE_CHANNEL": "chatgpt"},
        infer_host_environment=True,
    )

    assert environment.is_chatgpt_host_bridge is True
    assert environment.visible_channel_adapter == CHATGPT_ADAPTER
    assert environment.environment_host == "chatgpt_env_marker"


def test_v59_auto_route_behavior_matches_declared_priority(tmp_path: Path) -> None:
    config = JaznConfig(
        root=tmp_path,
        llm_route_mode="auto",
        allow_paid_openai_api=False,
        local_model_name="",
    )

    chatgpt = build_llm_route_status(
        config,
        command=CANONICAL_CHAT_COMMAND,
        env={"JAZN_VISIBLE_CHANNEL": "chatgpt", "JAZN_LOCAL_LLM_MODEL": "local-model"},
        infer_host_environment=True,
        probe_local=False,
    )
    assert chatgpt.selected_route == ROUTE_CHATGPT_HOST

    local = build_llm_route_status(
        config,
        command=CANONICAL_CHAT_COMMAND,
        env={"JAZN_LOCAL_LLM_MODEL": "local-model"},
        infer_host_environment=True,
        probe_local=False,
    )
    assert local.selected_route == ROUTE_OLLAMA_LOCAL

    paid = build_llm_route_status(
        config,
        command=CANONICAL_CHAT_COMMAND,
        env={"OPENAI_API_KEY": "test-key", "JAZN_ALLOW_PAID_OPENAI": "1"},
        infer_host_environment=True,
        probe_local=False,
    )
    assert paid.selected_route == ROUTE_OPENAI_PAID

    fallback = build_llm_route_status(
        config,
        command=CANONICAL_CHAT_COMMAND,
        env={},
        infer_host_environment=True,
        probe_local=False,
    )
    assert fallback.selected_route == ROUTE_NULL_FALLBACK


def test_v59_bridge_discovery_exposes_universal_conversation_and_legacy_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        bridge_discovery_module,
        "status_daemon",
        lambda *_args, **_kwargs: {"active_state": "inactive"},
    )

    payload = bridge_discovery_module.discover_runtime_bridges(JaznConfig(root=tmp_path))

    assert payload["conversation"]["command"].startswith("python -X utf8 run.py chat")
    assert payload["conversation"]["backend_selection"] == "auto"
    assert tuple(payload["conversation"]["route_priority"]) == AUTO_ROUTE_PRIORITY
    assert payload["local_chat"]["compatibility_alias_of"] == "conversation"
    assert payload["chatgpt_bridge"]["uses_openai_api"] is False


def test_v59_chatgpt_project_loader_requires_fresh_runtime_turn_before_host_text() -> None:
    root = Path(__file__).resolve().parents[1]
    loader = (root / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")
    runbook = (root / "AGENTS.chatgpt.md").read_text(encoding="utf-8")

    assert len(loader) <= 5000
    assert "raz na sesję wykonawczą" in loader
    assert "python -X utf8 run.py chat-gpt --session-id" in loader
    assert "Nie uruchamiaj nowego procesu CLI" in loader
    assert "Każdą kolejną wiadomość" in loader
    assert "Ta reguła obowiązuje dla każdej kolejnej tury" in runbook
    assert "świeże związanie tury nie oznacza świeżego procesu CLI" in runbook


def test_release_identity_supersedes_v60_with_accepted_visible_turn_convergence() -> None:
    assert tuple(int(part) for part in PACKAGE_VERSION.split(".")) >= (16, 3, 25, 5, 61)
    assert PACKAGE_RELEASE_NAME
