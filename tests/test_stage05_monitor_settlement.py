import json
from pathlib import Path

import pytest

from tools.jazn_monitor import telemetry
from tools.jazn_run_studio import probes


def test_effective_endpoint_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("JAZN_OLLAMA_BASE_URL", "JAZN_LOCAL_LLM_BASE_URL", "JAZN_LOCAL_LLM_API_BASE",
                "JAZN_LOCAL_MODEL_API_BASE", "OLLAMA_HOST"):
        monkeypatch.delenv(key, raising=False)
    assert probes.ollama_api_base() == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11435")
    assert probes.ollama_api_base() == "http://127.0.0.1:11435"
    monkeypatch.setenv("JAZN_OLLAMA_BASE_URL", "http://127.0.0.1:12420")
    assert probes.ollama_api_base() == "http://127.0.0.1:12420"
    assert probes.ollama_api_base("http://127.0.0.1:13000").endswith(":13000")
    monkeypatch.setenv("JAZN_OLLAMA_BASE_URL", "https://outside.invalid")
    with pytest.raises(ValueError):
        probes.ollama_api_base()


def test_unordered_terminal_history_and_counts(tmp_path: Path) -> None:
    workspace = telemetry.monitor_workspace(tmp_path)
    workspace.mkdir(parents=True, exist_ok=True)
    when = "2026-11-27T12:00:00Z"
    jobs = [
        {"request_id": "new", "status": "host_finalization_rejected", "completed_at_utc": when,
         "host_finalization_reason": "contract_missing", "result_error_code": "contract_missing"},
        {"request_id": "queued", "status": "queued", "created_at_utc": "2026-11-28T13:00:00Z"},
        {"request_id": "old", "status": "host_finalization_expired", "completed_at_utc": "2026-11-26T11:00:00Z"},
        {"request_id": "undated", "status": "completed"},
    ]
    (workspace / "daemon_chat_jobs.json").write_text(json.dumps({"jobs": jobs}), encoding="utf8")
    value = telemetry.jobs_snapshot(tmp_path, {"daemon_chat_jobs": {"submitted_total": 2}})
    newest = value["finalization"]
    assert (newest["state"], newest["reason_code"], newest["request_id"]) == (
        "host_finalization_rejected", "contract_missing", "new")
    assert newest["accepted_finalization"] is None
    assert value["counts"]["submitted_total"] == 2
    assert value["history_counts"]["host_finalization_expired"] == 1
    assert value["history_counts"]["completed"] == 1
    assert value["last_admitted_job"]["request_id"] == "queued"
