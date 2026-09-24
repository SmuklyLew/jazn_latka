from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_chatgpt_runbook_keeps_memory_attach_and_recovery_in_one_maintenance_window() -> None:
    text = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")
    assert "Jedno okno maintenance dla dołączanej MEMORY" in text
    assert "`memory-attach` wymaga nieaktywnego daemona" in text
    assert "`memory-recover`" in text
    assert "`JAZN_MEMORY_ROOT`" in text
    assert "nigdy przez zahardkodowane `<active_root>/memory`" in text
    assert "`start -> stop -> recover -> start`" in text
    assert "nadal jest `pending` i nigdy nie został `claimed`" in text


def test_chatgpt_runbook_preserves_turn_lineage_across_memory_maintenance() -> None:
    text = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")
    for field in ("`request_id`", "`turn_id`", "`trace_id`", "`host_request_contract_hash`"):
        assert field in text
    assert "bez replayu tekstu użytkownika" in text
    assert "Restart procesu nie tworzy nowej tury" in text
