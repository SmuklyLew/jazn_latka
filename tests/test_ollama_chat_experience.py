from __future__ import annotations

import io
import json
from types import SimpleNamespace

import main
from latka_jazn.core.runtime_chat import LatkaRuntimeShell
from latka_jazn.core.runtime_session_state import RuntimeSessionState
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter, _compact_model_context


class _TtyInput(io.StringIO):
    def isatty(self) -> bool:
        return True


class _JsonResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_chat_ollama_numbered_model_picker_uses_selected_number() -> None:
    output = io.StringIO()
    selected = main._select_ollama_model_for_tty(
        {
            "running_models": ["gemma3:latest"],
            "installed_models": ["gemma3:latest", "qwen3:latest"],
            "model": "gemma3:latest",
        },
        stdin=_TtyInput("2\n"),
        stdout=output,
    )
    assert selected == "qwen3:latest"
    assert "1. gemma3:latest (uruchomiony)" in output.getvalue()
    assert "2. qwen3:latest" in output.getvalue()


def test_runtime_shell_uses_user_prompt_generated_session_and_live_pair() -> None:
    calls: list[dict] = []

    class Runtime:
        runtime_turn_timeout_managed = True
        state = SimpleNamespace(session_id="generated-session-123")
        engine = SimpleNamespace()

        def process_user_text(self, text: str, **kwargs):
            calls.append({"text": text, **kwargs})
            return {"final_visible_text": f"odpowiedź-{len(calls)}"}

    shell = LatkaRuntimeShell(Runtime(), stdin=io.StringIO(), stdout=io.StringIO(), no_carryover=True)
    assert shell.prompt == "Ty> "
    assert shell.session_id == "generated-session-123"
    assert shell.lifecycle.session_id == "generated-session-123"

    assert shell.default("Pierwsza wiadomość") is False
    assert shell.default("Co z poprzednią turą?") is False
    assert calls[1]["previous_user_text"] == "Pierwsza wiadomość"
    assert calls[1]["previous_visible_text"] == "odpowiedź-1"


def test_runtime_session_state_keeps_last_visible_reply() -> None:
    state = RuntimeSessionState.create(session_id="session-1")
    state.update(
        user_text="Co się stało?",
        visible_text="Poprzednia odpowiedź została odrzucona.",
        intent="short_free_dialogue",
        route="ordinary_dialogue",
    )
    assert state.last_visible_text == "Poprzednia odpowiedź została odrzucona."
    state.clear_carryover()
    assert state.last_visible_text is None


def test_local_ollama_payload_is_compact_and_contains_chat_history(monkeypatch) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout: float):
        captured.update(json.loads(request.data.decode("utf-8")))
        return _JsonResponse(
            {
                "model": "gemma3:latest",
                "message": {"content": "Na nowej wersji działam już spójniej."},
                "done": True,
                "done_reason": "stop",
            }
        )

    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", fake_urlopen)
    context = {
        "user_message": "Jak się czujesz na nowej wersji?",
        "detected_intent": "self_state_question",
        "route": "self_state",
        "operational_thought_frame": {"huge": "x" * 500_000},
        "dialogue_context": {
            "previous_user_text": "Witaj...",
            "previous_assistant_text": "Witaj, Krzysztofie.",
        },
        "output_instructions": ["Odpowiedz po polsku."],
    }
    compact, diagnostics = _compact_model_context(context)
    assert diagnostics["compacted_context_chars"] <= diagnostics["context_max_chars"]
    assert "dialogue_context" in compact

    adapter = LocalLlmAdapter(model="gemma3:latest", timeout_seconds=5, max_output_tokens=100)
    text, metadata, error = adapter._chat_once(
        ModelAdapterRequest(prompt="Jak się czujesz na nowej wersji?", system_context=context),
        strict_retry=False,
    )
    assert error is None
    assert text
    assert [message["role"] for message in captured["messages"]] == ["system", "user", "assistant", "user"]
    assert captured["messages"][-1]["content"] == "Jak się czujesz na nowej wersji?"
    assert metadata["context_compacted"] is True
    assert metadata["message_count"] == 4
    assert metadata["compacted_context_chars"] <= metadata["context_max_chars"]
