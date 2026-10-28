"""Qt separation of local LLM conversation and ChatGPT ingress evidence."""
from __future__ import annotations

import pytest
pytest.importorskip("PySide6")

from tests.test_jazn_run_studio_layout import window


def test_separate_navigation_and_host_truth_boundary(window) -> None:
    titles = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert "Czat lokalny" in titles
    assert "Połączenie z ChatGPT" in titles
    assert titles.index("Czat lokalny") != titles.index("Połączenie z ChatGPT")
    assert set(window.connection_checks) == {
        "runtime", "gateway", "cloudflare", "auth", "toolset", "turn",
    }
    window.navigate("MCP i ChatGPT")  # legacy navigation alias
    assert window.nav.currentItem().text() == "Połączenie z ChatGPT"
    window.refresh_connection_checks()
    assert "wymaga" in window.connection_checks["toolset"].text()
    assert "brak dowodu" in window.connection_checks["turn"].text()


def test_runtime_evidence_updates_header_and_sidebar_together(window) -> None:
    window.core.emit("status", "evidence", {
        "endpoint_reachable": True, "process_identity_confirmed": True,
        "endpoint_identity_matches": True, "heartbeat_fresh": True,
        "conversation_ready": True, "active_state": "active_trusted",
    })
    window.poll()
    assert "runtime zweryfikowany" in window.workbench_status.text()
    assert "zweryfikowany" in window.sidebar_footnote.text()
    assert "odpowiedź wymaga akceptacji" in window.sidebar_footnote.text()
    window.core.emit("status", "evidence", {})
    window.poll()
    assert "status niezweryfikowany" in window.workbench_status.text()
    assert "gotowość niezweryfikowana" in window.sidebar_footnote.text()


def test_empty_ollama_model_list_does_not_invent_generation(window) -> None:
    window.core.emit("probe:ollama", "probe", {
        "service": "ollama", "endpoint_reachable": True, "models": [],
        "selected_model_present": False, "generation_verified": False,
    })
    window.poll()
    assert window.chat_model_selector.count() == 1
    assert "nie widzi żadnego modelu" in window.chat_state.text()
