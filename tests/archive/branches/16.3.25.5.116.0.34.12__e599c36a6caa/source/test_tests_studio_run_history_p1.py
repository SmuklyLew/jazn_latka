from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jazn_tests_studio.history import (
    HISTORY_LIMIT, HISTORY_SCHEMA, HistoryFormatError, export_run_history,
    load_run_history, record_run_summary,
)


def root_with_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    (root / "main.py").write_text("", encoding="utf-8")
    (root / "latka_jazn").mkdir()
    (root / "latka_jazn" / "version.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    return root


def result_payload() -> dict[str, object]:
    return {
        "ok": False, "outcome": "failed", "duration_seconds": 2.75,
        "total": 3, "completed": 3,
        "counts": {"PASSED": 2, "FAILED": 1, "ERROR": 0, "SKIPPED": 0, "XFAIL": 0, "XPASS": 0},
        "output": "PRIVATE_OUTPUT_NEVER_PERSIST",
        "command": ["pytest", "/private/system/tests/test_secret.py"],
        "nodeid": "PRIVATE_NODEID_NEVER_PERSIST",
    }


def test_history_discovery_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = root_with_operator(tmp_path, monkeypatch)
    assert load_run_history(root) == {"schema": HISTORY_SCHEMA, "runs": []}
    assert not (tmp_path / "operator").exists()


def test_summary_is_redacted_and_isolated_from_system_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = root_with_operator(tmp_path, monkeypatch)
    entry = record_run_summary(root, result_payload(), scope="selected")
    assert entry["scope"] == "selected"
    assert entry["outcome"] == "failed"
    assert entry["counts"]["FAILED"] == 1
    history = load_run_history(root)
    assert len(history["runs"]) == 1
    raw = json.dumps(history)
    assert "PRIVATE_OUTPUT" not in raw
    assert "PRIVATE_NODEID" not in raw
    assert "/private/system" not in raw
    assert "command" not in raw
    assert not (root / "run_history.json").exists()
    assert not (root / "memory").exists()


def test_history_retains_only_last_hundred(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = root_with_operator(tmp_path, monkeypatch)
    for _ in range(HISTORY_LIMIT + 3):
        record_run_summary(root, result_payload(), scope="all")
    assert len(load_run_history(root)["runs"]) == HISTORY_LIMIT
    assert load_run_history(root, limit=0)["runs"] == []
    assert len(load_run_history(root, limit=5)["runs"]) == 5


def test_invalid_history_fails_closed_without_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = root_with_operator(tmp_path, monkeypatch)
    record_run_summary(root, result_payload(), scope="all")
    from tools.jazn_tests_studio.history import _history_path
    path = _history_path(root)
    path.write_text('{"schema":"unexpected","runs":[]}', encoding="utf-8")
    with pytest.raises(HistoryFormatError):
        record_run_summary(root, result_payload(), scope="all")
    assert path.read_text(encoding="utf-8") == '{"schema":"unexpected","runs":[]}'


def test_export_requires_external_new_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = root_with_operator(tmp_path, monkeypatch)
    record_run_summary(root, result_payload(), scope="all")
    target = tmp_path / "report.json"
    assert export_run_history(root, target) == target.resolve()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["schema"] == HISTORY_SCHEMA
    assert "PRIVATE_OUTPUT" not in target.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_run_history(root, target)
    with pytest.raises(ValueError):
        export_run_history(root, Path("relative.json"))
    with pytest.raises(ValueError):
        export_run_history(root, root / "wrong-system-report.json")


def test_history_rejects_symlink_leaf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = root_with_operator(tmp_path, monkeypatch)
    from tools.jazn_tests_studio.history import _history_path
    path = _history_path(root)
    path.parent.mkdir(parents=True)
    target = tmp_path / "sensitive.json"
    target.write_text("protected", encoding="utf-8")
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(HistoryFormatError):
        load_run_history(root)
    assert target.read_text(encoding="utf-8") == "protected"


def test_invalid_scope_or_duration_does_not_create_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = root_with_operator(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        record_run_summary(root, result_payload(), scope="invalid")
    result = result_payload()
    result["duration_seconds"] = float("nan")
    with pytest.raises(ValueError):
        record_run_summary(root, result, scope="all")
    assert not (tmp_path / "operator").exists()
