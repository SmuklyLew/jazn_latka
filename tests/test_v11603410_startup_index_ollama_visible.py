from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    write_chat_bridge_payload,
    write_local_ollama_visible_reply,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.core.project_index import ProjectStartupIndexer


FINAL = "🕒 2026-10-19 17:27:50\n🌿 Łatka\n\nGotowe."


def _accepted_final() -> dict:
    return {
        "ok": True,
        "answer_ok": True,
        "execution_state": "final_visible_answer",
        "host_finalization_pending": False,
        "final_visible_text": FINAL,
        "final_visible_integrity": {
            "valid": True,
            "consensus": True,
            "text_sha256": sha256_host_visible_text(FINAL),
        },
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": True},
        "final_response_contract": {"author_source": "jazn_runtime"},
    }


@pytest.mark.windows
def test_local_renderer_preserves_polish_emoji_and_exact_bytes() -> None:
    out = io.StringIO()
    assert write_local_ollama_visible_reply(out, _accepted_final()) is True
    assert out.getvalue() == FINAL
    assert out.getvalue().encode("utf-8") == FINAL.encode("utf-8")


@pytest.mark.parametrize("changed", [
    {"answer_ok": False},
    {"execution_state": "awaiting_host_finalization"},
    {"host_finalization_pending": True},
    {"final_visible_text": FINAL + "tampered"},
    {"final_visible_integrity": {"valid": False, "consensus": False, "text_sha256": ""}},
    {"runtime_truth_gate": {"ok": False, "normal_response_allowed": False}},
    {"final_response_contract": {"author_source": "untrusted_client"}},
])
def test_local_renderer_rejects_unverified_or_tampered_final(changed: dict) -> None:
    payload = _accepted_final()
    payload.update(changed)
    out = io.StringIO()
    assert write_local_ollama_visible_reply(out, payload) is False
    report = json.loads(out.getvalue())
    assert report["error_code"] == "local_runtime_final_not_accepted"
    assert "🌿 Łatka" not in out.getvalue()
    assert FINAL not in out.getvalue()


def test_host_writer_does_not_inherit_local_authority() -> None:
    out = io.StringIO()
    write_chat_bridge_payload(out, _accepted_final(), output_mode="final_visible_text")
    packet = json.loads(out.getvalue())
    assert packet["action"] == "host_diagnostic"
    assert packet["accepted_visible_turn_ready"] is False
    assert packet["final_visible_text"] == ""


def test_explicit_index_prunes_private_and_volatile_trees(tmp_path: Path) -> None:
    allowed = tmp_path / "latka_jazn" / "core"
    allowed.mkdir(parents=True)
    (allowed / "sample.py").write_text("def hello():\n    return 'ok'\n", encoding="utf-8")
    for excluded in (".git", ".archives", "workspace_runtime", "memory",
                     ".venv", "node_modules", "tests/archive", "__pycache__"):
        target = tmp_path / excluded / "private.sqlite3"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"SECRET-PROJECT-INDEX-EXCLUDE")
    idx = ProjectStartupIndexer(tmp_path)
    data = idx.build(write=True)
    assert data["file_count"] == 1
    assert sorted(data["file_index"]) == ["latka_jazn/core/sample.py"]
    assert idx.output_path.is_file()
    assert data["index_sha256"]
    assert not list(idx.output_path.parent.glob(".project_startup_index_*.tmp"))


def test_explicit_index_readonly_never_creates_cache(tmp_path: Path) -> None:
    (tmp_path / "sample.py").write_text("x = 1\n", encoding="utf-8")
    index = ProjectStartupIndexer(tmp_path)
    data = index.build(write=False)
    assert data["file_count"] == 1
    assert not index.output_path.exists()


def test_cli_one_shot_uses_local_renderer_not_chatgpt_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _accepted_final()
    calls = []

    class FakeDaemonSession:
        def __init__(self, *args: object, **kwargs: object) -> None:
            calls.append(("init", kwargs.get("session_id")))

        def process_user_text(self, text: str, **kwargs: object) -> dict:
            calls.append(("turn", text))
            return dict(payload)

        def close(self) -> None:
            calls.append(("close", None))

    output = io.StringIO()
    monkeypatch.setattr(main_module, "DaemonConversationSession", FakeDaemonSession)
    monkeypatch.setattr(main_module.sys, "stdout", output)
    code = main_module._run_chat_command_one_shot(
        cfg=JaznConfig(root=tmp_path),
        text="Odpowiedz jednym slowem: GOTOWE.",
        session_id="index-smoke",
        no_carryover=False,
        source_client="ollama_terminal_one_shot",
        lifecycle="ollama_terminal_one_shot",
        command="--chat-ollama",
    )
    assert code == 0
    assert output.getvalue() == FINAL
    assert calls == [("init", "index-smoke"),
                     ("turn", "Odpowiedz jednym slowem: GOTOWE."),
                     ("close", None)]


def test_index_cache_requires_same_release_scope_and_hash(tmp_path: Path) -> None:
    (tmp_path / "sample.py").write_text("x = 1\n", encoding="utf-8")
    index = ProjectStartupIndexer(tmp_path)
    built = index.build(write=True)
    assert index.compatible_cache(built) is True
    assert index.status()["compatible"] is True

    old_release = dict(built)
    old_release.pop("runtime_version")
    assert index.compatible_cache(old_release) is False

    old_scope = dict(built)
    old_scope["excluded_dynamic_parts"] = ["__pycache__"]
    assert index.compatible_cache(old_scope) is False

    modified = dict(built)
    modified["file_count"] += 1
    assert index.compatible_cache(modified) is False


def test_engine_ignores_old_index_without_full_rescan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from latka_jazn.core.engine_construction import EngineRuntimeServices

    path = ProjectStartupIndexer(tmp_path).output_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "project_startup_index/v1",
        "active_root": str(tmp_path.resolve()),
        "file_count": 11081,
        "excluded_dynamic_parts": ["__pycache__"],
    }), encoding="utf-8")

    def no_full_scan(*args: object, **kwargs: object) -> None:
        raise AssertionError("full project scan entered runtime startup")

    monkeypatch.setattr(ProjectStartupIndexer, "build", no_full_scan)
    services = EngineRuntimeServices(JaznConfig(root=tmp_path))
    services.build_dependencies()
    try:
        services.hydrate()
        services.start()
        assert services.project_index_startup_report["ready"] is False
        assert services.project_index_startup_report["reason"] == "cache_incompatible_or_stale_deferred"
        assert services.project_startup_index == {}
    finally:
        services.close()
