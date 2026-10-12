from __future__ import annotations

import ast
import json
from pathlib import Path

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core import bridge_discovery
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_run_py_is_structurally_thin_and_has_no_domain_dispatch() -> None:
    source = _read("run.py")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert imported_roots <= {"__future__", "pathlib", "runpy", "sys", "latka_jazn"}
    assert "runpy.run_path" in source
    assert 'with_name("main.py")' in source
    assert "argparse" not in source
    for token in (
        "restart_daemon",
        "reload_daemon",
        "runtime-bootstrap",
        "host-finalize",
        "chat-gpt",
        "chat-ollama",
        "latka_jazn.cli",
    ):
        assert token not in source


def test_main_is_single_control_plane_and_passes_live_legacy_handler() -> None:
    source = _read("main.py")
    cli_source = _read("latka_jazn/cli.py")

    assert "def legacy_main(" in source
    assert "def main(argv: list[str] | None = None)" in source
    assert "legacy_handler=legacy_main" in source
    assert 'command in {"restart", "reload"}' in source
    assert 'command == "runtime-bootstrap"' in source
    assert 'command == "host-finalize"' in source
    assert "handler: Callable[[list[str]], int] | None = None" in cli_source
    assert "if handler is not None" in cli_source


def test_main_no_args_routes_to_chat_through_service_layer(monkeypatch) -> None:
    import latka_jazn.cli as cli_module

    observed: dict[str, object] = {}

    def fake_cli(argv, *, legacy_handler=None):
        observed["argv"] = list(argv)
        observed["handler"] = legacy_handler
        return 17

    monkeypatch.setattr(cli_module, "main", fake_cli)
    assert main_module.main([]) == 17
    assert observed["argv"] == ["chat"]
    assert observed["handler"] is main_module.legacy_main


def test_chatgpt_active_docs_require_persistent_process_not_per_message_cli() -> None:
    runbook = _read("AGENTS.chatgpt.md")
    loader = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")
    combined = runbook + "\n" + loader

    assert "persistent ChatGPT bridge" in combined
    assert "nie uruchamiaj nowej komendy CLI" in runbook
    assert "Nie uruchamiaj nowego procesu CLI" in loader
    assert "ten sam otwarty kanał" in runbook
    assert 'run.py chat-gpt -- "<dokładna wiadomość użytkownika>"' not in combined
    assert 'run python -X utf8 run.py chat-gpt -- "<wiadomość>"' not in combined


def test_bridge_discovery_declares_persistent_stdio_and_no_paid_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        bridge_discovery,
        "status_daemon",
        lambda *_args, **_kwargs: {"active_state": "inactive"},
    )
    payload = bridge_discovery.discover_runtime_bridges(JaznConfig(root=tmp_path))
    chatgpt = payload["chatgpt_bridge"]

    assert chatgpt["transport"] == "persistent_stdio_jsonl"
    assert chatgpt["per_message_cli_required"] is False
    assert chatgpt["persistent_bridge_process_required_when_host_supports_it"] is True
    assert chatgpt["requires_api_key"] is False
    assert chatgpt["uses_openai_api"] is False


def test_machine_readable_bootstrap_uses_persistent_chatgpt_bridge() -> None:
    startup = json.loads(_read("latka_jazn/resources/startup_contract.json"))
    self_knowledge = json.loads(_read("latka_jazn/resources/canon/LATKA_SELF_KNOWLEDGE_CONTRACT.json"))

    startup_text = json.dumps(startup, ensure_ascii=False)
    checklist_text = "\n".join(self_knowledge["post_update_bootstrap"])
    assert "chat-gpt --session-id" in startup_text
    assert "persistent" in startup_text.lower()
    assert "chat-gpt --session-id" in checklist_text
    assert "reuse its stdin/stdout" in checklist_text


def test_v60_release_identity() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.60"
    assert PACKAGE_RELEASE_NAME == "main-entrypoint-persistent-chatgpt-convergence"
