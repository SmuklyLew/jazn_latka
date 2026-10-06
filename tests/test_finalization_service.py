from __future__ import annotations

import ast
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.finalization_service import FinalizationService


def _candidate() -> dict:
    return {
        "turn_id": "turn-finalization-service",
        "trace_id": "trace-finalization-service",
        "timestamp_header": "🕒 2026-10-06 12:00:00",
        "timezone": "Europe/Warsaw",
        "timestamp_sample_iso": "2026-10-06T10:00:00+00:00",
        "timestamp_source": "test",
        "timestamp_trusted": True,
        "author_id": "latka_runtime",
        "author_label": "Łatka",
        "author_source": "jazn_runtime",
        "state_emoticon": "🌿",
        "final_text": "Rozumiem Twoją wiadomość.",
    }


def test_finalizer_construction_does_not_create_runtime_files(tmp_path: Path) -> None:
    root = tmp_path / "unmaterialized"
    service = FinalizationService(JaznConfig(root=root))
    service.shutdown()
    assert not root.exists()
    assert not (tmp_path / "workspace_runtime").exists()


def test_finalizer_rejects_bad_binding_before_opening_ledger(tmp_path: Path) -> None:
    service = FinalizationService(JaznConfig(root=tmp_path))
    candidate = _candidate()
    candidate["trace_id"] = ""
    with pytest.raises(ValueError, match="turn_id and trace_id"):
        service.persist_final_visible_reply(**candidate)
    assert service._event_ledger is None
    assert not (tmp_path / "workspace_runtime").exists()


def test_finalizer_persists_without_constructing_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import latka_jazn.core.engine as engine_module

    def forbidden(*args, **kwargs):
        raise AssertionError("phase-2 must never construct the cognitive engine")

    monkeypatch.setattr(engine_module, "JaznEngine", forbidden)
    service = FinalizationService(JaznConfig(root=tmp_path))
    result = service.persist_final_visible_reply(**_candidate())
    assert result["turn_id"] == "turn-finalization-service"
    assert result["trace_id"] == "trace-finalization-service"
    assert result["final_visible_text"].endswith("Rozumiem Twoją wiadomość.")
    ledger = Path(result["ledger_append"]["path"])
    persisted = ledger.read_text(encoding="utf-8")
    assert "turn-finalization-service" in persisted
    assert "engine_started" not in persisted
    assert not list(tmp_path.rglob("project_startup_index_current_line.json"))


def test_phase2_has_no_direct_engine_import_or_construction() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "latka_jazn/core/chat_command_contract.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "latka_jazn.core.engine"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "JaznEngine"
