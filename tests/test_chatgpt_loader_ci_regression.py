from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.version import PACKAGE_VERSION, PACKAGE_VERSION_FULL

ROOT = Path(__file__).resolve().parents[1]
TOOLS = (
    "jazn_status",
    "jazn_generate_visible_reply",
    "jazn_resume_visible_reply",
    "jazn_finalize_reply",
)


def test_loader_host_failure_and_library_discovery_remain_fail_closed() -> None:
    loader = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")
    assert len(loader) <= 5000
    assert all(tool in loader for tool in TOOLS)
    assert "bieżącej generacji powierzchni wykonawczej" in loader
    assert "nie traktuj tego jako dowodu braku `/mnt/data`" in loader
    assert "Sprzeczne kopie/metadane kończ fail-closed" in loader
    assert "nie cache'uj go jako trwałego stanu rozmowy" in loader
    assert "nie dopisuj nagłówka ręcznie" in loader
    assert "Loader nie rozszerza uprawnień" in loader


def test_distribution_startup_and_public_mcp_contract_share_version() -> None:
    startup = json.loads((ROOT / "latka_jazn/resources/startup_contract.json").read_text(encoding="utf-8"))
    public = json.loads((ROOT / "deploy/chatgpt_mcp/deployment.contract.json").read_text(encoding="utf-8"))
    assert startup["version"] == PACKAGE_VERSION
    assert public["runtime_version"] == PACKAGE_VERSION_FULL
    assert tuple(startup["chatgpt_required_turn_tools"]) == TOOLS
    assert startup["chatgpt_catalog_or_installed_state_sufficient"] is False
    assert startup["chatgpt_current_message_toolset_observation_required"] is True
    assert public["security"]["public_https_required"] is True
    assert public["security"]["oauth_required_for_public_non_loopback"] is True
