from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
import json
from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_v66_jazn_config_generated_constructor_and_replace_contract(tmp_path: Path) -> None:
    cfg = JaznConfig(
        root=tmp_path,
        allow_network=False,
        network_time_first=False,
        dictionary_allow_network=False,
        model_adapter="null",
        local_model_name="",
        local_model_api_base="http://127.0.0.1:11434",
        llm_route_mode="auto",
        allow_paid_openai_api=False,
        rest_cycle_enabled=False,
        rest_shadow_mode=True,
        rest_idle_start_seconds=1.0,
        rest_cycle_interval_seconds=2.0,
        rest_poll_seconds=0.5,
        rest_max_cycles_per_episode=2,
        rest_replay_limit=1,
        rest_local_model_enabled=False,
        hard_worker_process_isolation=True,
        worker_process_cancel_grace_seconds=0.25,
        worker_process_startup_timeout_seconds=5.0,
    )

    expected_fields = {
        "root",
        "allow_network",
        "network_time_first",
        "dictionary_allow_network",
        "model_adapter",
        "local_model_name",
        "local_model_api_base",
        "llm_route_mode",
        "allow_paid_openai_api",
        "rest_cycle_enabled",
        "rest_shadow_mode",
        "rest_idle_start_seconds",
        "rest_cycle_interval_seconds",
        "rest_poll_seconds",
        "rest_max_cycles_per_episode",
        "rest_replay_limit",
        "rest_local_model_enabled",
        "hard_worker_process_isolation",
        "worker_process_cancel_grace_seconds",
        "worker_process_startup_timeout_seconds",
    }

    assert is_dataclass(JaznConfig)
    assert expected_fields.issubset({item.name for item in fields(cfg)})

    replacement_root = tmp_path / "replacement"
    cloned = replace(
        cfg,
        root=replacement_root,
        allow_network=True,
        rest_poll_seconds=1.5,
    )
    assert cloned.root == replacement_root.resolve()
    assert cloned.allow_network is True
    assert cloned.rest_poll_seconds == 1.5


def test_v66_project_loader_requires_runtime_binding_before_visible_or_tool_action() -> None:
    text = (ROOT / "docs" / "runtime" / "CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(
        encoding="utf-8"
    )

    assert len(text) <= 5000
    assert "Przed pierwszą zwykłą odpowiedzią lub akcją narzędziową" in text
    assert "każdą zwykłą wiadomość użytkownika najpierw przekaż do runtime" in text
    assert "także gdy wymaga Web/GitHub/image/file" in text
    assert "Przed tym związaniem tury nie wykonuj zwykłej odpowiedzi hosta ani narzędzia" in text
    assert "--daemon-request-id <request-id>" in text
    assert "bez replayu" in text
    assert "action=display_exact" in text
    assert "nie dopisuj nagłówka ręcznie" in text


def test_v66_vscode_pylance_diagnostics_match_canonical_ci_pyright() -> None:
    settings = json.loads((ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    pyright_config = json.loads((ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))
    workflow = (ROOT / ".github" / "workflows" / "pyright-active-tree-audit.yml").read_text(
        encoding="utf-8"
    )

    assert settings["python.analysis.diagnosticsSource"] == "Pylance + Pyright"
    assert settings["python.analysis.pyrightVersion"] == "1.1.411"
    assert pyright_config["typeCheckingMode"] == "standard"
    assert pyright_config["pythonVersion"] == "3.12"
    assert "pyright --project pyrightconfig.json --outputjson" in workflow
    assert '      - "fix/**"' in workflow
    assert "  pull_request:" in workflow


def test_v66_release_identity() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.66"
    assert PACKAGE_RELEASE_NAME == "chatgpt-loader-pylance-static-gate-convergence"
