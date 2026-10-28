"""Diagnostics regressions for incident 2026-10-28: keep cause and remedy distinct."""
from __future__ import annotations

from urllib.error import URLError

from tools.jazn_run_studio.problem_guidance import (
    explain_failure, probe_failure_code,
)


def test_connection_refused_and_timeout_are_not_generic_urlerror() -> None:
    assert probe_failure_code(URLError(ConnectionRefusedError(10061, "refused"))) == "connection_refused"
    assert probe_failure_code(URLError(TimeoutError("timed out"))) == "connection_timeout"
    assert probe_failure_code(URLError("proxy failure")) == "transport_unreachable"


def test_ollama_failure_has_actionable_local_loopback_guidance() -> None:
    guide = explain_failure("probe:ollama", "connection_refused")
    assert "Ollama" in guide.title
    assert "127.0.0.1:11434/api/tags" in guide.remedy
    assert "pobieraj modelu automatycznie" in guide.remedy
    assert "secret" not in guide.remedy.lower()


def test_runtime_failure_must_warn_about_different_master_daemon() -> None:
    guide = explain_failure("status", "process_exit:1")
    assert "Worktree" in guide.remedy
    assert "Nie zatrzymuj" in guide.remedy


def test_mcp_guidance_does_not_publish_dev_gateway() -> None:
    guide = explain_failure("probe:gateway", "transport_unreachable")
    assert "--loopback-dev" in guide.remedy
    assert "publiczny tunel" in guide.remedy


def test_unknown_job_remains_honest_not_false_success() -> None:
    guide = explain_failure("helper:custom", "unknown")
    assert "nie została ukończona" in guide.title
