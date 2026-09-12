from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.core.turn_response_policy import TurnResponsePolicy
from main import _prepare_chatgpt_daemon_presentation


def test_memory_experience_policy_allows_grounded_memory_content() -> None:
    policy = TurnResponsePolicy.build(
        intent="memory_experience_question",
        route="free_memory_dialogue_no_source",
    )
    assert policy.allow_memory_content is True
    assert policy.source_boundary_required is True
    assert "memory_content" in policy.required_components
    assert "no_current_turn_echo" in policy.required_components


def test_memory_search_planner_rejects_conversational_filler_for_experience_question(tmp_path: Path) -> None:
    plan = MemorySearchPlanner(tmp_path).plan(
        "Hej! Jak się masz? Co wspominasz teraz najbardziej?",
        fallback_terms=["Hej", "się", "masz", "najbardziej"],
    )
    assert plan.focus_terms == []
    assert plan.search_terms == []
    assert {"Hej", "się", "masz", "najbardziej"}.issubset(set(plan.rejected_terms))


def test_daemon_execution_timeout_remains_explicit_host_diagnostic(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    payload = {
        "ok": False,
        "error_code": "execution_timeout",
        "request_id": "timeout-1",
        "execution_timeout_seconds": 180.0,
        "timeout_owner": "runtime_session_worker",
        "daemon_job": {
            "request_id": "timeout-1",
            "job_status": "execution_timeout",
            "execution_timeout_seconds": 180.0,
            "turn_telemetry": {"stages": {"memory_reads": {"status": "running"}}},
            "result": {
                "error_code": "execution_timeout",
                "execution_timeout_seconds": 180.0,
                "timeout_owner": "runtime_session_worker",
            },
        },
    }
    presented = _prepare_chatgpt_daemon_presentation(
        cfg=cfg,
        payload=payload,
        request_id="timeout-1",
        user_text="Hej",
    )
    bridge = presented["chatgpt_host_bridge"]
    assert bridge["phase"] == "host_diagnostic_required"
    assert bridge["status"] == "daemon_turn_execution_timeout"
    assert bridge["diagnostic_reason"] == "execution_timeout"
    assert bridge["execution_timeout_seconds"] == 180.0
    assert bridge["timeout_owner"] == "runtime_session_worker"


def test_terminal_job_diagnostic_keeps_failure_metadata_without_user_text() -> None:
    from latka_jazn.core.runtime_daemon import DaemonChatJob, JaznDaemonServer

    job = DaemonChatJob(
        request_id="timeout-2",
        user_text="prywatna wiadomość",
        input_field="test",
        session_id="session",
        no_carryover=False,
        client="test",
        status="execution_timeout",
        completed_at_utc="2026-08-22T21:00:00+00:00",
        execution_timeout_seconds=180.0,
        result={"error_code": "execution_timeout", "timeout_owner": "runtime_session_worker"},
    )
    diagnostic = JaznDaemonServer._terminal_job_diagnostic(job)
    assert diagnostic["job_status"] == "execution_timeout"
    assert diagnostic["error_code"] == "execution_timeout"
    assert diagnostic["timeout_owner"] == "runtime_session_worker"
    assert diagnostic["contains_user_text"] is False
    assert "user_text" not in diagnostic
    assert diagnostic["user_text_sha256"]
