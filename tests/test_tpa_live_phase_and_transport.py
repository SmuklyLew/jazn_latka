"""Synthetic regression tests for crash-resilient TPA live evidence and chat failures.

No daemon, Ollama request, production MEMORY or filesystem outside tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from tools.jazn_run_studio.tpa_live import append_phase_event, generation_failure, generation_warning


@pytest.mark.parametrize(
    "source,kind,value,expected",
    [
        ("chat", "state", {"state": "failed", "error": "private-error"}, "chat_transport_failed"),
        ("chat", "chat_state", "Potwierdzona nieudana tura: private-error", "daemon_turn_failed"),
        ("chat", "chat_state", "Transport zamknięty z błędem", "chat_transport_closed"),
        ("chat", "chat_state", "Runtime zgłosił błąd: private-error", None),
        ("chat", "chat_state", "Brak zaakceptowanej wypowiedzi. Zachowano request_id", None),
        ("chat", "state", {"state": "running"}, None),
        ("chat", "chat_state", "Oczekiwanie na odpowiedź", None),
        ("chat:resume", "state", {"state": "failed"}, None),
        ("chat", "chat_final", {"accepted": True}, None),
        ("other", "chat_state", "Runtime zgłosił błąd: private-error", None),
    ],
)
def test_terminal_generation_classification_exposes_only_public_reason(
    source: str, kind: str, value: object, expected: str | None,
) -> None:
    observed = generation_failure(source, kind, value)
    assert observed == expected
    assert "private-error" not in str(observed)


def test_fsynced_phase_journal_survives_without_a_final_report(tmp_path: Path) -> None:
    """An interrupted host may never call finish_live; phases stay on disk."""
    append_phase_event(tmp_path, "start", 100.0)
    append_phase_event(tmp_path, "heartbeat", 110.0)
    append_phase_event(tmp_path, "generation", 120.0)
    path = tmp_path / "phase-events.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["phase"] for row in rows] == ["start", "heartbeat", "generation"]
    assert all(row["event"] == "phase" for row in rows)
    assert rows[-1]["monotonic"] == 120.0
    assert not (tmp_path / "report.json").exists()
    assert "request_id" not in path.read_text(encoding="utf-8")
    assert "token" not in path.read_text(encoding="utf-8")


def test_unknown_phase_is_refused_before_any_write(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Nieznana faza"):
        append_phase_event(tmp_path, "private-token", 10.0)
    assert not (tmp_path / "phase-events.jsonl").exists()

@pytest.mark.parametrize(
    "message,expected",
    [
        ("Runtime zgłosił błąd: private-error", "runtime_error_unconfirmed"),
        ("Brak zaakceptowanej wypowiedzi. Zachowano request_id", "unaccepted_candidate"),
    ],
)
def test_unconfirmed_chat_diagnostics_remain_nonterminal(message: str, expected: str) -> None:
    assert generation_failure("chat", "chat_state", message) is None
    assert generation_warning("chat", "chat_state", message) == expected
    assert "private-error" not in expected
