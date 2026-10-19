from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_chatgpt_runbook_prefers_actual_jazn_status_connector_probe() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "Preferowany probe przez rzeczywistą akcję Jaźni" in text
    assert "jedno read-only wywołanie `jazn_status`" in text
    assert "`host_connector_invocation_observed=true`" in text
    assert "Wklejony JSON" in text
    assert "nie wolno ich mieszać" in text
    assert "`classify_public_connector_status_failover()`" in text


def test_plugin_runbook_documents_no_executor_success_state() -> None:
    text = _read("docs/runtime/CHATGPT_PLUGIN_RUNTIME.md")

    assert "jazn_public_mcp_status/v1" in text
    assert "executor_available=false" in text
    assert "remote_runtime_available=true" in text
    assert "execution_route=remote_runtime" in text
    assert "must never be reconstructed from saved JSON" in text


def test_persistent_runtime_runbook_keeps_direct_and_connector_probes_separate() -> None:
    text = _read("docs/runtime/PERSISTENT_REMOTE_MCP_RUNTIME.md")

    assert "Deployment/HTTP probe" in text
    assert "Connector-observed probe" in text
    assert "connector_status" in text
    assert "host_connector_invocation_observed=true" in text
    assert "wzajemnie wykluczające" in text
