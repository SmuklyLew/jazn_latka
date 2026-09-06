from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_chatgpt_runbook_distinguishes_host_executor_failure_from_filesystem_absence() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "host_executor_unavailable" in text
    assert "filesystem_state = unknown" in text
    assert "package_state = unknown" in text
    assert "przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu" in text
    assert "nie twierdź, że `/mnt/data` nie istnieje" in text
    assert "dokładnie jedna niezależna alternatywna lokalna powierzchnia wykonawcza" in text
    assert "nie zapętlaj retry między narzędziami" in text


def test_chatgpt_runbook_resumes_only_through_canonical_runtime_lifecycle() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "po odzyskaniu executora wróć do zwykłego discovery/bootstrapu" in text
    assert "kanonicznego lifecycle `run.py`" in text
    assert "nie twórz równoległej ścieżki uruchamiania" in text
    assert "One-shot dowodzi wyłącznie wykonania danej tury" in text


def test_project_loader_preserves_unknown_local_state_on_pre_process_host_failure() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")

    assert "host_executor_unavailable" in text
    assert "filesystemu i paczki pozostaje wtedy `unknown`" in text
    assert "nie traktuj tego jako dowodu braku `/mnt/data`" in text
    assert "przed wykonaniem jakiejkolwiek komendy lub utworzeniem procesu" in text
